# SPDX-License-Identifier: Apache-2.0
"""SelfAdaptiveGaussianMutation (v0.D Phase 1, SR-01) — unit tests.

Schwefel-style σSA-ES の挙動を verify する:

1. Shape / bounds validation
2. σ が log-normal で動く (期待値 ≈ σ_old)
3. 探索初期は σ 高め, 収束期は σ 低めに自動調整される
4. EvolutionLoop と統合して回る
5. sphere fitness で baseline (固定 σ) と比較
"""

from __future__ import annotations

import numpy as np
import pytest

from llive.perf.evolutionary import (
    ChainedMutation,
    ElitismSelection,
    EvolutionConfig,
    EvolutionLoop,
    Fitness,
    FitnessReport,
    GaussianMutation,
    Genome,
    GenomeBounds,
    Individual,
    Population,
    SelfAdaptiveGaussianMutation,
    TournamentSelection,
    UniformCrossover,
    initial_sigma_values,
    pack_self_adaptive_bounds,
)


# ---------------------------------------------------------------------------
# 1. construction / validation
# ---------------------------------------------------------------------------


def test_init_rejects_zero_object_dims() -> None:
    with pytest.raises(ValueError, match="n_object_dims"):
        SelfAdaptiveGaussianMutation(n_object_dims=0)


def test_init_rejects_invalid_p() -> None:
    with pytest.raises(ValueError, match="p"):
        SelfAdaptiveGaussianMutation(n_object_dims=3, p=0.0)
    with pytest.raises(ValueError, match="p"):
        SelfAdaptiveGaussianMutation(n_object_dims=3, p=1.1)


def test_call_rejects_wrong_genome_dim() -> None:
    bounds = GenomeBounds(lower=(0.0, 0.0, 0.0), upper=(1.0, 1.0, 1.0))
    genome = Genome.from_values((0.5, 0.5, 0.5), bounds=bounds)
    mut = SelfAdaptiveGaussianMutation(n_object_dims=3)  # 期待 6 dim
    with pytest.raises(ValueError, match="2 \\* n_object_dims"):
        mut(genome, np.random.default_rng(0))


# ---------------------------------------------------------------------------
# 2. helpers — bounds packing
# ---------------------------------------------------------------------------


def test_pack_self_adaptive_bounds_doubles_dim() -> None:
    obj = GenomeBounds(lower=(0.0, -1.0), upper=(1.0, 1.0))
    aug, labels = pack_self_adaptive_bounds(
        obj, sigma_lower=0.01, sigma_upper=0.5, object_labels=("x", "y")
    )
    assert aug.n_dims == 4
    assert aug.lower == (0.0, -1.0, 0.01, 0.01)
    assert aug.upper == (1.0, 1.0, 0.5, 0.5)
    assert labels == ("x", "y", "sigma_x", "sigma_y")


def test_pack_self_adaptive_bounds_default_labels() -> None:
    obj = GenomeBounds(lower=(0.0, 0.0), upper=(1.0, 1.0))
    aug, labels = pack_self_adaptive_bounds(obj)
    assert labels == ("dim_0", "dim_1", "sigma_dim_0", "sigma_dim_1")


def test_initial_sigma_values_shape() -> None:
    s = initial_sigma_values(5, sigma_init=0.1)
    assert s.shape == (5,)
    assert np.allclose(s, 0.1)


def test_initial_sigma_values_rejects_invalid() -> None:
    with pytest.raises(ValueError, match="sigma_init"):
        initial_sigma_values(3, sigma_init=0.0)


# ---------------------------------------------------------------------------
# 3. mutation produces valid genome within bounds
# ---------------------------------------------------------------------------


def test_call_preserves_bounds() -> None:
    obj = GenomeBounds(lower=(0.0, 0.0), upper=(1.0, 1.0))
    aug, labels = pack_self_adaptive_bounds(obj, sigma_lower=1e-4, sigma_upper=2.0)
    values = np.concatenate([np.array([0.5, 0.5]), initial_sigma_values(2)])
    genome = Genome.from_values(values, bounds=aug, labels=labels)
    mut = SelfAdaptiveGaussianMutation(n_object_dims=2)
    rng = np.random.default_rng(0)
    for _ in range(20):
        genome = mut(genome, rng)
        arr = genome.as_array()
        # object var within [0,1], sigma within [1e-4, 2.0]
        assert 0.0 <= arr[0] <= 1.0
        assert 0.0 <= arr[1] <= 1.0
        assert 1e-4 <= arr[2] <= 2.0
        assert 1e-4 <= arr[3] <= 2.0


def test_call_returns_new_genome_each_time() -> None:
    """deterministic seed で 2 回呼ぶと同じ結果 (immutable input)."""
    obj = GenomeBounds(lower=(0.0,), upper=(1.0,))
    aug, _ = pack_self_adaptive_bounds(obj)
    genome = Genome.from_values((0.5, 0.1), bounds=aug)
    mut = SelfAdaptiveGaussianMutation(n_object_dims=1)
    rng1 = np.random.default_rng(42)
    rng2 = np.random.default_rng(42)
    g1 = mut(genome, rng1)
    g2 = mut(genome, rng2)
    assert g1.values == g2.values
    # 元 genome は不変
    assert genome.values == (0.5, 0.1)


# ---------------------------------------------------------------------------
# 4. statistical behavior — σ log-normal update expectation
# ---------------------------------------------------------------------------


def test_sigma_geometric_mean_close_to_original() -> None:
    """log-normal update なので幾何平均は σ_old に近いはず.

    σ_new = σ_old * exp(τ' * N_global + τ * N_local). 多数 sample すると
    log(σ_new) - log(σ_old) の平均は 0 に近い (両 N(0,1) の期待値 0).
    """
    n = 5
    obj_b = GenomeBounds(lower=(0.0,) * n, upper=(1.0,) * n)
    aug, _ = pack_self_adaptive_bounds(obj_b, sigma_lower=1e-4, sigma_upper=10.0)
    mut = SelfAdaptiveGaussianMutation(n_object_dims=n)
    rng = np.random.default_rng(123)
    sigma0 = 0.1
    initial = np.concatenate([np.full(n, 0.5), np.full(n, sigma0)])
    genome = Genome.from_values(initial, bounds=aug)
    log_ratios = []
    for _ in range(500):
        g_new = mut(genome, rng)
        sigma_new = np.asarray(g_new.values[n:])
        log_ratios.append(np.log(sigma_new / sigma0))
    log_arr = np.asarray(log_ratios)
    # mean log(σ_new/σ_old) は 0 付近 (両 N(0,1) の sum なので)
    assert abs(float(log_arr.mean())) < 0.1


def test_sigma_evolves_under_population_selection() -> None:
    """sphere fitness で集団進化を回すと σ が小さくなる傾向 (収束圧力)."""
    n = 3
    obj_b = GenomeBounds(lower=(-1.0,) * n, upper=(1.0,) * n)
    aug, labels = pack_self_adaptive_bounds(
        obj_b, sigma_lower=1e-4, sigma_upper=2.0
    )
    # 初期 σ は 0.5 (大きめ)
    rng = np.random.default_rng(7)
    individuals = []
    for _ in range(20):
        x = rng.uniform(-1.0, 1.0, size=n)
        sigma = np.full(n, 0.5)
        vals = np.concatenate([x, sigma])
        individuals.append(Individual.from_genome(
            Genome.from_values(vals, bounds=aug, labels=labels)
        ))
    pop = Population(individuals=individuals, bounds=aug, seed=7)

    def sphere_neg(genome: Genome) -> FitnessReport:
        # 前半 n のみ評価. -sum(x^2) なら原点が optimum.
        x = np.asarray(genome.values[:n])
        return FitnessReport(score=float(-np.sum(x * x)))

    mut = SelfAdaptiveGaussianMutation(n_object_dims=n)
    loop = EvolutionLoop(
        fitness_fn=sphere_neg,
        selection=TournamentSelection(k=3),
        crossover=UniformCrossover(p=0.5),
        mutation=mut,
        elitism=ElitismSelection(top_n=2),
    )
    config = EvolutionConfig(max_generations=15, patience=99, log_progress=False)
    result = loop.run(pop, config)
    # 収束した最終個体の σ は初期 0.5 より下がっているはず (収束圧力)
    final_pop = result.final_population
    final_sigmas = np.array([
        ind.genome.values[n:] for ind in final_pop.individuals
    ])
    mean_sigma_final = float(final_sigmas.mean())
    assert mean_sigma_final < 0.5  # 初期より小さい
    # best も原点に近づく
    assert result.best_score > -0.5  # sphere は最大化 (符号反転後), 改善方向


# ---------------------------------------------------------------------------
# 5. EvolutionLoop 統合 — chained with ResetMutation
# ---------------------------------------------------------------------------


def test_chained_with_reset_mutation() -> None:
    """ChainedMutation で SelfAdaptive + 何か追加 mutation を併用できる."""
    from llive.perf.evolutionary.mutation import ResetMutation

    n = 2
    obj_b = GenomeBounds(lower=(0.0, 0.0), upper=(1.0, 1.0))
    aug, _ = pack_self_adaptive_bounds(obj_b)
    sa = SelfAdaptiveGaussianMutation(n_object_dims=n)
    reset = ResetMutation(p=0.01)
    chained = ChainedMutation(mutations=(sa, reset))
    values = np.concatenate([np.array([0.5, 0.5]), initial_sigma_values(2)])
    genome = Genome.from_values(values, bounds=aug)
    rng = np.random.default_rng(0)
    g = chained(genome, rng)
    assert g.n_dims == 4
    # bounds 内
    arr = g.as_array()
    assert (arr[:2] >= 0.0).all() and (arr[:2] <= 1.0).all()
    assert (arr[2:] >= 1e-4).all() and (arr[2:] <= 2.0).all()


def test_p_less_than_1_allows_partial_update() -> None:
    """p<1.0 だと一部 dim が変化しない可能性がある (mask)."""
    n = 10
    obj_b = GenomeBounds(lower=(0.0,) * n, upper=(1.0,) * n)
    aug, _ = pack_self_adaptive_bounds(aug if False else obj_b)
    mut = SelfAdaptiveGaussianMutation(n_object_dims=n, p=0.1)
    rng = np.random.default_rng(0)
    values = np.concatenate([np.full(n, 0.5), np.full(n, 0.1)])
    genome = Genome.from_values(values, bounds=aug)
    g_new = mut(genome, rng)
    # 一部 dim が元のまま (mask による)
    arr_old = genome.as_array()[:n]
    arr_new = g_new.as_array()[:n]
    diffs = np.abs(arr_old - arr_new)
    unchanged = (diffs < 1e-9).sum()
    assert unchanged > 0  # 少なくとも 1 dim は変化していない


def test_relative_to_width_false_smaller_noise() -> None:
    """relative_to_width=False だと bounds width で scale しない (小さな noise)."""
    n = 1
    obj_b = GenomeBounds(lower=(0.0,), upper=(100.0,))  # width=100
    aug, _ = pack_self_adaptive_bounds(obj_b)
    sa_rel = SelfAdaptiveGaussianMutation(n_object_dims=n, relative_to_width=True)
    sa_abs = SelfAdaptiveGaussianMutation(n_object_dims=n, relative_to_width=False)
    values = np.concatenate([np.array([50.0]), np.array([0.1])])
    genome = Genome.from_values(values, bounds=aug)
    rng = np.random.default_rng(0)
    g_rel = sa_rel(genome, rng)
    # 同じ rng で再評価 (絶対 noise)
    rng = np.random.default_rng(0)
    g_abs = sa_abs(genome, rng)
    delta_rel = abs(g_rel.values[0] - 50.0)
    delta_abs = abs(g_abs.values[0] - 50.0)
    # relative は width*σ = 100*~0.1, absolute は σ = ~0.1. relative >> absolute
    assert delta_rel > delta_abs * 10.0
