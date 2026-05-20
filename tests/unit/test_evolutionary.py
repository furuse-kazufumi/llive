# SPDX-License-Identifier: Apache-2.0
"""llive v0.B 進化型最適化 — 単体テスト."""

from __future__ import annotations

import numpy as np
import pytest

from llive.perf.evolutionary import (
    BlendCrossover,
    ElitismSelection,
    EvolutionConfig,
    EvolutionLoop,
    FitnessReport,
    GaussianMutation,
    Genome,
    GenomeBounds,
    Individual,
    Population,
    ResetMutation,
    RouletteSelection,
    TournamentSelection,
    UniformCrossover,
    rosenbrock_fitness,
    sphere_fitness,
)


# ---------------------------------------------------------------------------
# Genome / Bounds
# ---------------------------------------------------------------------------


def test_genome_bounds_validates_order() -> None:
    with pytest.raises(ValueError):
        GenomeBounds(lower=(0.0, 0.0), upper=(0.0, 1.0))  # lower==upper invalid


def test_genome_bounds_clip_to_range() -> None:
    bounds = GenomeBounds(lower=(0.0, 0.0), upper=(1.0, 1.0))
    clipped = bounds.clip(np.array([-2.0, 5.0]))
    assert clipped.tolist() == [0.0, 1.0]


def test_genome_from_values_clips() -> None:
    bounds = GenomeBounds(lower=(0.0,), upper=(1.0,))
    g = Genome.from_values([2.5], bounds=bounds)
    assert g.values == (1.0,)


def test_genome_random_in_bounds() -> None:
    bounds = GenomeBounds(lower=(-1.0, -1.0, -1.0), upper=(1.0, 1.0, 1.0))
    rng = np.random.default_rng(0)
    g = Genome.random(bounds, rng)
    arr = g.as_array()
    assert (arr >= -1.0).all() and (arr <= 1.0).all()


def test_genome_serialize_roundtrip() -> None:
    bounds = GenomeBounds(lower=(0.0, 0.0), upper=(1.0, 1.0))
    g = Genome.from_values([0.3, 0.7], bounds=bounds, labels=("a", "b"))
    g2 = Genome.from_dict(g.to_dict())
    assert g2.values == g.values
    assert g2.labels == g.labels
    assert g2.bounds == g.bounds


# ---------------------------------------------------------------------------
# Individual / Fitness
# ---------------------------------------------------------------------------


def test_individual_score_inf_before_eval() -> None:
    bounds = GenomeBounds(lower=(0.0,), upper=(1.0,))
    ind = Individual.from_genome(Genome.from_values([0.5], bounds=bounds))
    assert ind.score == float("-inf")


def test_individual_record_fitness_updates_history() -> None:
    bounds = GenomeBounds(lower=(0.0,), upper=(1.0,))
    ind = Individual.from_genome(Genome.from_values([0.5], bounds=bounds))
    ind.record_fitness(FitnessReport(score=1.0))
    ind.record_fitness(FitnessReport(score=2.0))
    assert ind.score == 2.0
    assert len(ind.history) == 2


# ---------------------------------------------------------------------------
# Population
# ---------------------------------------------------------------------------


def test_population_random_in_bounds() -> None:
    bounds = GenomeBounds(lower=(-1.0, -1.0), upper=(1.0, 1.0))
    pop = Population.random(bounds=bounds, size=10, seed=42)
    assert pop.size == 10
    for ind in pop.individuals:
        arr = ind.genome.as_array()
        assert (arr >= -1.0).all() and (arr <= 1.0).all()


def test_population_stats_reasonable() -> None:
    bounds = GenomeBounds(lower=(-1.0, -1.0), upper=(1.0, 1.0))
    pop = Population.random(bounds=bounds, size=5, seed=7)
    for i, ind in enumerate(pop.individuals):
        ind.record_fitness(FitnessReport(score=float(i)))
    stats = pop.compute_stats()
    assert stats.best_score == 4.0
    assert stats.mean_score == 2.0
    assert stats.diversity_l2 > 0.0


def test_population_replace_increments_generation() -> None:
    bounds = GenomeBounds(lower=(0.0,), upper=(1.0,))
    pop = Population.random(bounds=bounds, size=3, seed=0)
    new_ind = Individual.from_genome(Genome.from_values([0.5], bounds=bounds))
    pop.replace([new_ind] * 3, new_seed=99)
    assert pop.generation == 1
    assert pop.seed == 99


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def test_tournament_picks_best() -> None:
    bounds = GenomeBounds(lower=(0.0,), upper=(1.0,))
    pop = Population.random(bounds=bounds, size=10, seed=1)
    for i, ind in enumerate(pop.individuals):
        ind.record_fitness(FitnessReport(score=float(i)))
    rng = np.random.default_rng(0)
    selection = TournamentSelection(k=10)  # k = pop.size → 必ず全体の best
    picked = selection(pop, rng)
    assert picked.score == 9.0


def test_roulette_temperature_valid() -> None:
    with pytest.raises(ValueError):
        RouletteSelection(temperature=0.0)


def test_elitism_returns_top_n() -> None:
    bounds = GenomeBounds(lower=(0.0,), upper=(1.0,))
    pop = Population.random(bounds=bounds, size=5, seed=1)
    for i, ind in enumerate(pop.individuals):
        ind.record_fitness(FitnessReport(score=float(i)))
    elites = ElitismSelection(top_n=2).select(pop)
    assert len(elites) == 2
    assert all(e.score >= 3.0 for e in elites)


# ---------------------------------------------------------------------------
# Crossover / Mutation
# ---------------------------------------------------------------------------


def test_uniform_crossover_child_in_parents_value_set() -> None:
    bounds = GenomeBounds(lower=(0.0, 0.0), upper=(1.0, 1.0))
    a = Genome.from_values([0.1, 0.2], bounds=bounds)
    b = Genome.from_values([0.9, 0.8], bounds=bounds)
    rng = np.random.default_rng(0)
    child = UniformCrossover(p=0.5)(a, b, rng)
    for v, va, vb in zip(child.values, a.values, b.values, strict=True):
        assert v in (va, vb)


def test_blend_crossover_in_bounds() -> None:
    bounds = GenomeBounds(lower=(0.0, 0.0), upper=(1.0, 1.0))
    a = Genome.from_values([0.1, 0.2], bounds=bounds)
    b = Genome.from_values([0.9, 0.8], bounds=bounds)
    rng = np.random.default_rng(0)
    child = BlendCrossover(alpha=0.5)(a, b, rng)
    arr = child.as_array()
    assert (arr >= 0.0).all() and (arr <= 1.0).all()


def test_gaussian_mutation_in_bounds() -> None:
    bounds = GenomeBounds(lower=(-1.0,), upper=(1.0,))
    g = Genome.from_values([0.0], bounds=bounds)
    rng = np.random.default_rng(0)
    mutated = GaussianMutation(sigma=5.0, p=1.0)(g, rng)
    assert -1.0 <= mutated.values[0] <= 1.0


def test_reset_mutation_eventually_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    bounds = GenomeBounds(lower=(0.0,), upper=(1.0,))
    g = Genome.from_values([0.5], bounds=bounds)
    rng = np.random.default_rng(0)
    mutated = ResetMutation(p=1.0)(g, rng)  # p=1 で必ず reset
    assert 0.0 <= mutated.values[0] <= 1.0


# ---------------------------------------------------------------------------
# Fitness (toy)
# ---------------------------------------------------------------------------


def test_sphere_fitness_maximum_at_zero() -> None:
    bounds = GenomeBounds(lower=(-1.0, -1.0), upper=(1.0, 1.0))
    g0 = Genome.from_values([0.0, 0.0], bounds=bounds)
    g1 = Genome.from_values([1.0, 1.0], bounds=bounds)
    r0 = sphere_fitness(g0)
    r1 = sphere_fitness(g1)
    assert r0.score == 0.0
    assert r1.score == -2.0
    # runtime metadata 必須
    assert "llama_cpp_sha" in r0.runtime_metadata


def test_rosenbrock_fitness_max_at_ones() -> None:
    bounds = GenomeBounds(lower=(-2.0, -2.0), upper=(2.0, 2.0))
    g_opt = Genome.from_values([1.0, 1.0], bounds=bounds)
    g_bad = Genome.from_values([-2.0, -2.0], bounds=bounds)
    r_opt = rosenbrock_fitness(g_opt)
    r_bad = rosenbrock_fitness(g_bad)
    assert r_opt.score > r_bad.score


# ---------------------------------------------------------------------------
# EvolutionLoop on sphere (best fitness 単調増加 を要求)
# ---------------------------------------------------------------------------


def test_evolution_loop_improves_sphere() -> None:
    bounds = GenomeBounds(lower=(-5.0, -5.0, -5.0), upper=(5.0, 5.0, 5.0))
    pop = Population.random(bounds=bounds, size=20, seed=42)

    loop = EvolutionLoop(
        fitness_fn=sphere_fitness,
        selection=TournamentSelection(k=3),
        crossover=UniformCrossover(p=0.5),
        mutation=GaussianMutation(sigma=0.15, p=0.2),
        elitism=ElitismSelection(top_n=2),
    )
    config = EvolutionConfig(max_generations=30, patience=30, log_progress=False)
    result = loop.run(pop, config)

    # 最初の世代と最後の世代を比較. sphere は score が大きいほど 0 に近く良い.
    first_best = result.stats_history[0].best_score
    last_best = result.stats_history[-1].best_score
    assert last_best > first_best, "best fitness が改善していない"
    # 真の最適 0.0 にある程度近いはず (3 dim sphere は易しい)
    assert last_best > -0.5


def test_evolution_loop_records_history_and_seeds() -> None:
    bounds = GenomeBounds(lower=(-1.0,), upper=(1.0,))
    pop = Population.random(bounds=bounds, size=10, seed=7)
    loop = EvolutionLoop(fitness_fn=sphere_fitness)
    config = EvolutionConfig(max_generations=5, patience=5, log_progress=False)
    result = loop.run(pop, config)
    assert len(result.stats_history) >= 2
    assert len(pop.generation_seeds) >= 2  # 初期 + 各世代


def test_evolution_loop_stops_on_patience() -> None:
    """初期集団を全部 best にして, 改善余地が無い場合に patience で停止することを確認."""
    bounds = GenomeBounds(lower=(0.0,), upper=(0.001,))  # 非常に狭い -> 改善余地ほぼ無
    pop = Population.random(bounds=bounds, size=8, seed=1)
    loop = EvolutionLoop(fitness_fn=sphere_fitness)
    config = EvolutionConfig(max_generations=50, patience=3, log_progress=False)
    result = loop.run(pop, config)
    assert "patience" in result.stopped_reason or "diversity" in result.stopped_reason
