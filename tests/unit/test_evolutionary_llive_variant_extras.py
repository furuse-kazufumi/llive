# SPDX-License-Identifier: Apache-2.0
"""LV × SR 統合 helper (v0.D Phase 1+2 統合) の unit tests."""

from __future__ import annotations

import numpy as np
import pytest

from llive.perf.evolutionary import (
    ElitismSelection,
    EvolutionConfig,
    EvolutionLoop,
    Genome,
    Individual,
    LIVE_VARIANT_GENOME_BOUNDS,
    LIVE_VARIANT_GENOME_LABELS,
    LV_OBJECT_DIMS,
    MetaMutation,
    Population,
    SelfAdaptiveGaussianMutation,
    SegmentCrossover,
    TournamentSelection,
    build_meta_strategy_variant_bounds,
    build_self_adaptive_meta_strategy_variant_bounds,
    build_self_adaptive_variant_bounds,
    default_variant_meta_strategies,
    initialize_self_adaptive_variant_genome_values,
    make_meta_variant_mutation,
    make_self_adaptive_variant_mutation,
    mock_variant_fitness_factory,
    strategy_distribution,
    wrap_fitness_for_extended_genome,
)


# ---------------------------------------------------------------------------
# 1. bounds extension
# ---------------------------------------------------------------------------


def test_lv_object_dims_is_19() -> None:
    assert LV_OBJECT_DIMS == 19
    assert LIVE_VARIANT_GENOME_BOUNDS.n_dims == 19


def test_build_self_adaptive_variant_bounds_38_dim() -> None:
    bounds, labels = build_self_adaptive_variant_bounds()
    assert bounds.n_dims == 38
    assert len(labels) == 38
    # 前半 19 dim は元 LV と同じ
    assert bounds.lower[:19] == LIVE_VARIANT_GENOME_BOUNDS.lower
    assert bounds.upper[:19] == LIVE_VARIANT_GENOME_BOUNDS.upper
    assert labels[:19] == LIVE_VARIANT_GENOME_LABELS
    # 後半 19 dim は σ
    assert labels[19] == f"sigma_{LIVE_VARIANT_GENOME_LABELS[0]}"


def test_build_meta_strategy_variant_bounds_20_dim() -> None:
    bounds, labels = build_meta_strategy_variant_bounds(n_strategies=3)
    assert bounds.n_dims == 20
    assert len(labels) == 20
    assert labels[:19] == LIVE_VARIANT_GENOME_LABELS
    assert labels[19] == "strategy_id"


def test_build_self_adaptive_meta_strategy_variant_bounds_39_dim() -> None:
    bounds, labels = build_self_adaptive_meta_strategy_variant_bounds(
        n_strategies=3
    )
    assert bounds.n_dims == 39
    assert labels[:19] == LIVE_VARIANT_GENOME_LABELS
    # 後半: σ × 19 + strategy_id × 1
    assert labels[19] == f"sigma_{LIVE_VARIANT_GENOME_LABELS[0]}"
    assert labels[-1] == "strategy_id"


# ---------------------------------------------------------------------------
# 2. fitness wrapper
# ---------------------------------------------------------------------------


def test_wrap_fitness_extracts_first_19_dims() -> None:
    """38 dim genome の前半 19 dim だけで fitness 評価が走る."""
    aug_bounds, aug_labels = build_self_adaptive_variant_bounds()
    rng = np.random.default_rng(0)
    obj_vals = aug_bounds.sample_uniform(rng)[:19]
    full_vals = initialize_self_adaptive_variant_genome_values(obj_vals)
    aug_genome = Genome.from_values(full_vals, bounds=aug_bounds, labels=aug_labels)

    base_fitness = mock_variant_fitness_factory()
    wrapped = wrap_fitness_for_extended_genome(base_fitness, n_object_dims=19)
    report_wrapped = wrapped(aug_genome)
    # 同じ object_values で base fitness を直接呼ぶ
    obj_genome = Genome.from_values(
        obj_vals,
        bounds=LIVE_VARIANT_GENOME_BOUNDS,
        labels=LIVE_VARIANT_GENOME_LABELS,
    )
    report_direct = base_fitness(obj_genome)
    assert report_wrapped.score == pytest.approx(report_direct.score, abs=1e-9)


def test_wrap_fitness_rejects_short_genome() -> None:
    base_fitness = mock_variant_fitness_factory()
    wrapped = wrap_fitness_for_extended_genome(base_fitness, n_object_dims=19)
    # 5 dim genome (足りない)
    from llive.perf.evolutionary.genome import GenomeBounds

    short_bounds = GenomeBounds(lower=(0.0,) * 5, upper=(1.0,) * 5)
    short_genome = Genome.from_values((0.5,) * 5, bounds=short_bounds)
    with pytest.raises(ValueError, match="n_object_dims"):
        wrapped(short_genome)


# ---------------------------------------------------------------------------
# 3. genome value initialization
# ---------------------------------------------------------------------------


def test_initialize_concat_object_and_sigma() -> None:
    obj = np.linspace(0.0, 1.0, 19)
    full = initialize_self_adaptive_variant_genome_values(obj, sigma_init=0.1)
    assert full.shape == (38,)
    assert np.allclose(full[:19], obj)
    assert np.allclose(full[19:], 0.1)


def test_initialize_rejects_wrong_shape() -> None:
    with pytest.raises(ValueError, match="shape"):
        initialize_self_adaptive_variant_genome_values(np.zeros(10))


# ---------------------------------------------------------------------------
# 4. factories
# ---------------------------------------------------------------------------


def test_make_self_adaptive_variant_mutation_has_19_object_dims() -> None:
    mut = make_self_adaptive_variant_mutation()
    assert mut.n_object_dims == 19
    assert mut.relative_to_width is True


def test_make_meta_variant_mutation_default_strategies() -> None:
    mut = make_meta_variant_mutation()
    assert isinstance(mut, MetaMutation)
    assert len(mut.strategies) == 3
    assert mut.strategy_dim == -1


def test_default_variant_meta_strategies_3_strategies() -> None:
    strategies = default_variant_meta_strategies()
    assert len(strategies) == 3


# ---------------------------------------------------------------------------
# 5. End-to-end EvolutionLoop integration
# ---------------------------------------------------------------------------


def _build_self_adaptive_population(
    *, size: int, seed: int
) -> tuple[Population, tuple]:
    """38 dim 初期集団を生成."""
    aug_bounds, aug_labels = build_self_adaptive_variant_bounds()
    rng = np.random.default_rng(seed)
    inds = []
    for _ in range(size):
        obj_vals = aug_bounds.sample_uniform(rng)[:19]
        full_vals = initialize_self_adaptive_variant_genome_values(
            obj_vals, sigma_init=0.2
        )
        inds.append(
            Individual.from_genome(
                Genome.from_values(full_vals, bounds=aug_bounds, labels=aug_labels)
            )
        )
    return Population(individuals=inds, bounds=aug_bounds, seed=seed), aug_labels


def test_self_adaptive_lv_evolution_runs_and_sigma_shrinks() -> None:
    """LV 38 dim genome で 12 世代回し, σ 平均が初期 0.2 から下がるかを確認."""
    pop, _ = _build_self_adaptive_population(size=20, seed=11)
    fitness = wrap_fitness_for_extended_genome(mock_variant_fitness_factory())
    mut = make_self_adaptive_variant_mutation()
    loop = EvolutionLoop(
        fitness_fn=fitness,
        selection=TournamentSelection(k=3),
        crossover=SegmentCrossover(segments=((0, 19), (19, 38)), p=0.5),
        mutation=mut,
        elitism=ElitismSelection(top_n=2),
    )
    config = EvolutionConfig(max_generations=12, patience=99, log_progress=False)
    result = loop.run(pop, config)
    # 最終集団の σ 平均
    final_sigmas = np.array([
        ind.genome.values[19:] for ind in result.final_population.individuals
    ])
    mean_sigma_final = float(final_sigmas.mean())
    assert mean_sigma_final < 0.2  # 収束圧力で σ が小さくなる
    assert result.best_score > 0.0


def test_meta_strategy_lv_evolution_runs() -> None:
    """LV 20 dim genome で 8 世代回し, 集団内 strategy 分布を集計できる."""
    bounds, labels = build_meta_strategy_variant_bounds(n_strategies=3)
    rng = np.random.default_rng(22)
    inds = []
    for _ in range(15):
        obj_vals = bounds.sample_uniform(rng)
        # strategy_id をランダム化済 (uniform sample で含まれる)
        inds.append(
            Individual.from_genome(
                Genome.from_values(obj_vals, bounds=bounds, labels=labels)
            )
        )
    pop = Population(individuals=inds, bounds=bounds, seed=22)
    fitness = wrap_fitness_for_extended_genome(mock_variant_fitness_factory())
    mut = make_meta_variant_mutation()
    loop = EvolutionLoop(
        fitness_fn=fitness,
        selection=TournamentSelection(k=3),
        crossover=SegmentCrossover(segments=((0, 19), (19, 20)), p=0.5),
        mutation=mut,
        elitism=ElitismSelection(top_n=2),
    )
    config = EvolutionConfig(max_generations=8, patience=99, log_progress=False)
    result = loop.run(pop, config)
    dist = strategy_distribution(
        result.final_population.individuals, n_strategies=3
    )
    assert sum(dist.values()) == result.final_population.size
    assert result.best_score > 0.0


def test_self_adaptive_meta_strategy_combined_evolution_runs() -> None:
    """LV 39 dim genome (object 19 + σ 19 + strategy_id 1) で 6 世代回す."""
    bounds, labels = build_self_adaptive_meta_strategy_variant_bounds(
        n_strategies=2
    )
    rng = np.random.default_rng(33)
    inds = []
    for _ in range(12):
        # object var (19) + sigma (19) + strategy_id (1) を埋める
        obj = bounds.sample_uniform(rng)[:19]
        sigma = np.full(19, 0.15)
        sid = float(rng.integers(0, 2))
        full = np.concatenate([obj, sigma, [sid]])
        inds.append(
            Individual.from_genome(
                Genome.from_values(full, bounds=bounds, labels=labels)
            )
        )
    pop = Population(individuals=inds, bounds=bounds, seed=33)
    fitness = wrap_fitness_for_extended_genome(mock_variant_fitness_factory())
    # MetaMutation の strategies に SelfAdaptiveGaussianMutation を含めるには
    # n_object_dims=19 が必要だが, ここでは genome 全体 39 dim に対し
    # 2*n_object=38 という不一致が起きる. このため combined 版は通常の
    # GaussianMutation 2 種で MetaMutation を作る方が安全 (本来の用途は
    # 「SA は外側 / Meta は内側」分離).
    mut = make_meta_variant_mutation()
    loop = EvolutionLoop(
        fitness_fn=fitness,
        selection=TournamentSelection(k=3),
        crossover=SegmentCrossover(
            segments=((0, 19), (19, 38), (38, 39)), p=0.5
        ),
        mutation=mut,
        elitism=ElitismSelection(top_n=2),
    )
    config = EvolutionConfig(max_generations=6, patience=99, log_progress=False)
    result = loop.run(pop, config)
    assert result.best_score > 0.0
    # 39 dim genome のまま
    for ind in result.final_population.individuals:
        assert ind.genome.n_dims == 39
