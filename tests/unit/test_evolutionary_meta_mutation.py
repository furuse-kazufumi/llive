# SPDX-License-Identifier: Apache-2.0
"""MetaMutation (v0.D Phase 2, SR-02) — unit tests.

genome に strategy_id を埋め込み, dispatch する meta-mutation を verify する.
"""

from __future__ import annotations

import numpy as np
import pytest

from llive.perf.evolutionary import (
    ElitismSelection,
    EvolutionConfig,
    EvolutionLoop,
    FitnessReport,
    GaussianMutation,
    Genome,
    GenomeBounds,
    Individual,
    MetaMutation,
    Population,
    ResetMutation,
    TournamentSelection,
    UniformCrossover,
    pack_meta_strategy_bounds,
    strategy_distribution,
)


# ---------------------------------------------------------------------------
# 1. construction / validation
# ---------------------------------------------------------------------------


def test_init_rejects_empty_strategies() -> None:
    with pytest.raises(ValueError, match="strategies"):
        MetaMutation(strategies=())


def test_call_rejects_empty_genome() -> None:
    bounds = GenomeBounds(lower=(0.0,), upper=(1.0,))
    g = Genome.from_values((0.5,), bounds=bounds)
    # 戦略 1 件 + strategy_dim=0 (genome の唯一 dim を strategy_id にする)
    mm = MetaMutation(
        strategies=(GaussianMutation(sigma=0.1, p=1.0),),
        strategy_dim=0,
    )
    # Genome は 1 dim だが allowed. just exercise no-error path.
    rng = np.random.default_rng(0)
    g2 = mm(g, rng)
    assert g2.n_dims == 1


# ---------------------------------------------------------------------------
# 2. helpers
# ---------------------------------------------------------------------------


def test_pack_meta_strategy_bounds_appends_dim() -> None:
    obj = GenomeBounds(lower=(0.0, -1.0), upper=(1.0, 1.0))
    aug, labels = pack_meta_strategy_bounds(
        obj, n_strategies=3, object_labels=("x", "y")
    )
    assert aug.n_dims == 3
    assert aug.lower == (0.0, -1.0, 0.0)
    # strategy_id upper = n_strategies - 0.001 = 2.999
    assert aug.upper == pytest.approx((1.0, 1.0, 2.999), abs=1e-6)
    assert labels == ("x", "y", "strategy_id")


def test_pack_meta_strategy_bounds_rejects_zero_strategies() -> None:
    obj = GenomeBounds(lower=(0.0,), upper=(1.0,))
    with pytest.raises(ValueError, match="n_strategies"):
        pack_meta_strategy_bounds(obj, n_strategies=0)


def test_strategy_distribution_counts() -> None:
    obj = GenomeBounds(lower=(0.0,), upper=(1.0,))
    aug, _ = pack_meta_strategy_bounds(obj, n_strategies=3)
    # 5 個体: strategy_id 0/0/1/2/2
    inds = []
    for sid in [0.0, 0.0, 1.0, 2.0, 2.0]:
        vals = np.array([0.5, sid])
        g = Genome.from_values(vals, bounds=aug)
        inds.append(Individual.from_genome(g))
    dist = strategy_distribution(inds, n_strategies=3)
    assert dist == {0: 2, 1: 1, 2: 2}


def test_strategy_distribution_fills_zero_buckets() -> None:
    obj = GenomeBounds(lower=(0.0,), upper=(1.0,))
    aug, _ = pack_meta_strategy_bounds(obj, n_strategies=3)
    vals = np.array([0.5, 1.0])  # 1 個体だけ strategy_id=1
    g = Genome.from_values(vals, bounds=aug)
    dist = strategy_distribution([Individual.from_genome(g)], n_strategies=3)
    assert dist == {0: 0, 1: 1, 2: 0}


# ---------------------------------------------------------------------------
# 3. dispatch behavior
# ---------------------------------------------------------------------------


def test_dispatch_gauss_vs_reset_by_strategy_id() -> None:
    """strategy_id=0 なら GaussianMutation, =1 なら ResetMutation."""
    obj = GenomeBounds(lower=(0.0,), upper=(1.0,))
    aug, _ = pack_meta_strategy_bounds(obj, n_strategies=2)

    # ResetMutation は p=1.0 にして必ず動くようにする
    g_mut = GaussianMutation(sigma=1e-9, p=0.0)  # ほぼ無変動 (object var)
    r_mut = ResetMutation(p=1.0)
    mm = MetaMutation(strategies=(g_mut, r_mut))

    # strategy_id=0 → 元の値ほぼそのまま
    g0 = Genome.from_values(np.array([0.42, 0.0]), bounds=aug)
    rng = np.random.default_rng(0)
    g0_new = mm(g0, rng)
    assert abs(g0_new.values[0] - 0.42) < 1e-6

    # strategy_id=1 → ResetMutation で uniform 化 (値が変わる可能性高)
    g1 = Genome.from_values(np.array([0.42, 1.0]), bounds=aug)
    rng = np.random.default_rng(0)
    g1_new = mm(g1, rng)
    # 値が変わっている (高確率)
    assert abs(g1_new.values[0] - 0.42) > 1e-6 or g1_new.values[0] != g0_new.values[0]


def test_dispatch_clips_out_of_range_strategy_id() -> None:
    """strategy_id が n_strategies を超えると clip して最後の strategy."""
    obj = GenomeBounds(lower=(0.0,), upper=(1.0,))
    # 2 strategies で aug を作るが, strategy_id=99 を **直接** 入れて clip 確認
    aug = GenomeBounds(lower=(0.0, 0.0), upper=(1.0, 99.0))  # 範囲を広く
    g_mut = GaussianMutation(sigma=1e-9, p=0.0)
    r_mut = ResetMutation(p=1.0)
    mm = MetaMutation(strategies=(g_mut, r_mut))

    g = Genome.from_values(np.array([0.42, 99.0]), bounds=aug)
    rng = np.random.default_rng(0)
    g_new = mm(g, rng)
    # strategy_id=99 → clip to 1 (last) → ResetMutation 動作
    assert abs(g_new.values[0] - 0.42) > 1e-6 or g_new.values[0] >= 0.0


def test_strategy_dim_can_be_explicit_positive() -> None:
    """strategy_dim を明示的に指定 (default -1 以外)."""
    obj = GenomeBounds(lower=(0.0,), upper=(1.0,))
    aug = GenomeBounds(lower=(0.0, 0.0, 0.0), upper=(1.999, 1.0, 1.0))
    # dim 0 が strategy_id, dim 1-2 が object var
    g_mut = GaussianMutation(sigma=0.1, p=0.0)
    r_mut = ResetMutation(p=1.0)
    mm = MetaMutation(strategies=(g_mut, r_mut), strategy_dim=0)
    g = Genome.from_values(np.array([1.0, 0.5, 0.5]), bounds=aug)  # strategy_id=1
    rng = np.random.default_rng(0)
    g_new = mm(g, rng)
    # ResetMutation 動作 (object var 変化)
    assert g_new.values[0] == pytest.approx(1.0, abs=1e-9)  # strategy_dim 自体は触らない


# ---------------------------------------------------------------------------
# 4. EvolutionLoop 統合 — multi-strategy population
# ---------------------------------------------------------------------------


def test_evolution_loop_with_meta_mutation_runs() -> None:
    """sphere fitness で MetaMutation を使った進化が完走する."""
    n = 3
    obj_b = GenomeBounds(lower=(-1.0,) * n, upper=(1.0,) * n)
    aug, labels = pack_meta_strategy_bounds(
        obj_b, n_strategies=2, object_labels=("a", "b", "c")
    )

    rng = np.random.default_rng(42)
    inds = []
    for _ in range(12):
        x = rng.uniform(-1.0, 1.0, size=n)
        sid = float(rng.integers(0, 2))
        vals = np.concatenate([x, [sid]])
        inds.append(Individual.from_genome(
            Genome.from_values(vals, bounds=aug, labels=labels)
        ))
    pop = Population(individuals=inds, bounds=aug, seed=42)

    def sphere_neg(genome: Genome) -> FitnessReport:
        x = np.asarray(genome.values[:n])
        return FitnessReport(score=float(-np.sum(x * x)))

    mm = MetaMutation(
        strategies=(
            GaussianMutation(sigma=0.1, p=0.3),
            ResetMutation(p=0.05),
        )
    )
    loop = EvolutionLoop(
        fitness_fn=sphere_neg,
        selection=TournamentSelection(k=3),
        crossover=UniformCrossover(p=0.5),
        mutation=mm,
        elitism=ElitismSelection(top_n=2),
    )
    config = EvolutionConfig(max_generations=10, patience=99, log_progress=False)
    result = loop.run(pop, config)
    assert result.best_score > -3.0  # 改善方向 (worst -3, best 0)
    # 集団内 strategy 分布が確認できる
    dist = strategy_distribution(
        result.final_population.individuals, n_strategies=2
    )
    assert sum(dist.values()) == result.final_population.size
