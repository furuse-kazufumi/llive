# SPDX-License-Identifier: Apache-2.0
"""SpeciationLayer + SpeciatedTournamentSelection (v0.E CE-32) tests."""

from __future__ import annotations

import numpy as np
import pytest

from llive.perf.evolutionary import (
    FitnessReport,
    Genome,
    GenomeBounds,
    Individual,
    Population,
    SpeciatedTournamentSelection,
    Speciation,
    SpeciationLayer,
    Species,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_pop(values_list: list[list[float]]) -> Population:
    n = len(values_list[0])
    bounds = GenomeBounds(lower=(0.0,) * n, upper=(10.0,) * n)
    inds = []
    for vals in values_list:
        ind = Individual.from_genome(Genome.from_values(vals, bounds=bounds))
        inds.append(ind)
    return Population(individuals=inds, bounds=bounds, seed=0)


# ---------------------------------------------------------------------------
# 1. SpeciationLayer
# ---------------------------------------------------------------------------


def test_layer_validates_epsilon() -> None:
    with pytest.raises(ValueError, match="epsilon"):
        SpeciationLayer(epsilon=0.0)


def test_layer_validates_min_size() -> None:
    with pytest.raises(ValueError, match="min_species_size"):
        SpeciationLayer(min_species_size=0)


def test_assign_creates_two_species_for_clusters() -> None:
    """近い 3 個と遠い 3 個 → 2 species."""
    pop = _make_pop([
        [0.0, 0.0], [0.1, 0.1], [0.2, 0.0],   # cluster A
        [5.0, 5.0], [5.1, 5.0], [5.0, 5.2],   # cluster B
    ])
    layer = SpeciationLayer(epsilon=1.0)
    assignments = layer.assign(pop)
    assert layer.n_species() == 2
    sizes = layer.species_sizes()
    # 各 species size は 3
    assert sorted(sizes.values()) == [3, 3]


def test_assign_single_species_for_close_cluster() -> None:
    pop = _make_pop([[i * 0.01, 0.0] for i in range(10)])
    layer = SpeciationLayer(epsilon=1.0)
    assignments = layer.assign(pop)
    assert layer.n_species() == 1
    sid = next(iter(layer.species.keys()))
    assert layer.species[sid].size() == 10


def test_assign_increments_age() -> None:
    pop = _make_pop([[0.0, 0.0], [0.1, 0.1]])
    layer = SpeciationLayer(epsilon=1.0)
    layer.assign(pop)
    sid = next(iter(layer.species.keys()))
    assert layer.species[sid].age == 1
    layer.assign(pop)
    assert layer.species[sid].age == 2


def test_update_representatives() -> None:
    pop = _make_pop([[0.0], [0.1], [0.2]])
    layer = SpeciationLayer(epsilon=1.0)
    layer.assign(pop)
    rng = np.random.default_rng(0)
    layer.update_representatives(pop, rng)
    sid = next(iter(layer.species.keys()))
    rep = layer.species[sid].representative
    # 種の member の値のいずれかと一致
    member_values = [
        ind.genome.values[0] for ind in pop.individuals
        if ind.individual_id in layer.species[sid].member_ids
    ]
    assert float(rep[0]) in pytest.approx(member_values, abs=1e-9)


# ---------------------------------------------------------------------------
# 2. shared_fitness
# ---------------------------------------------------------------------------


def test_shared_fitness_divides_by_species_size() -> None:
    pop = _make_pop([[0.0], [0.1], [5.0]])
    # 全員に score を割り当てる
    for ind, s in zip(pop.individuals, [1.0, 1.0, 1.0]):
        ind.fitness = FitnessReport(score=s)
    layer = SpeciationLayer(epsilon=1.0)
    layer.assign(pop)
    # cluster A は 2 体, B は 1 体
    shared_a = layer.shared_fitness(pop.individuals[0])
    shared_b = layer.shared_fitness(pop.individuals[2])
    # B (1 体種) のほうが大きい shared fitness
    assert shared_b > shared_a
    assert shared_a == pytest.approx(0.5, abs=1e-9)  # 1.0 / 2
    assert shared_b == pytest.approx(1.0, abs=1e-9)  # 1.0 / 1


def test_shared_fitness_returns_neg_inf_when_unevaluated() -> None:
    pop = _make_pop([[0.0]])
    layer = SpeciationLayer(epsilon=1.0)
    layer.assign(pop)
    s = layer.shared_fitness(pop.individuals[0])
    assert s == float("-inf")


# ---------------------------------------------------------------------------
# 3. SpeciatedTournamentSelection
# ---------------------------------------------------------------------------


def test_tournament_picks_within_species() -> None:
    pop = _make_pop([[0.0], [0.1], [5.0], [5.1]])
    for ind, s in zip(pop.individuals, [1.0, 5.0, 3.0, 9.0]):
        ind.fitness = FitnessReport(score=s)
    layer = SpeciationLayer(epsilon=1.0)
    layer.assign(pop)
    sel = SpeciatedTournamentSelection(layer=layer, k=2, use_shared_fitness=False)
    rng = np.random.default_rng(42)
    counts = {"A": 0, "B": 0}
    for _ in range(50):
        chosen = sel(pop, rng)
        if chosen.individual_id == pop.individuals[1].individual_id:
            counts["A"] += 1
        elif chosen.individual_id == pop.individuals[3].individual_id:
            counts["B"] += 1
    # 各 species size 2 で選ばれる確率は ~ size 比. 50% / 50% を期待
    assert counts["A"] >= 10
    assert counts["B"] >= 10


def test_tournament_fallback_when_no_species() -> None:
    pop = _make_pop([[0.0], [1.0]])
    for ind, s in zip(pop.individuals, [1.0, 5.0]):
        ind.fitness = FitnessReport(score=s)
    layer = SpeciationLayer(epsilon=0.5)  # 種未走行
    sel = SpeciatedTournamentSelection(layer=layer, k=2, use_shared_fitness=False)
    rng = np.random.default_rng(0)
    chosen = sel(pop, rng)
    assert chosen.individual_id in {p.individual_id for p in pop.individuals}


def test_tournament_validates_k() -> None:
    layer = SpeciationLayer(epsilon=1.0)
    with pytest.raises(ValueError, match="k"):
        SpeciatedTournamentSelection(layer=layer, k=0)


# ---------------------------------------------------------------------------
# 4. backward-compat alias
# ---------------------------------------------------------------------------


def test_speciation_alias() -> None:
    assert Speciation is SpeciationLayer
