# SPDX-License-Identifier: Apache-2.0
"""IslandModel (v0.E CE-33) tests."""

from __future__ import annotations

import numpy as np
import pytest

from llive.perf.evolutionary import (
    FitnessReport,
    Genome,
    GenomeBounds,
    Individual,
    IslandModel,
    Population,
)


def _make_pop(values_list: list[float], seed: int = 0) -> Population:
    b = GenomeBounds(lower=(0.0,), upper=(10.0,))
    inds = []
    for v in values_list:
        ind = Individual.from_genome(Genome.from_values((v,), bounds=b))
        ind.fitness = FitnessReport(score=v)
        inds.append(ind)
    return Population(individuals=inds, bounds=b, seed=seed)


def _make_3_islands(sizes: list[int] = [5, 5, 5]) -> IslandModel:
    islands = []
    base = 0.0
    for size in sizes:
        pop = _make_pop([base + i * 0.1 for i in range(size)])
        base += 1.0
        islands.append(pop)
    return IslandModel(islands=islands)


# ---------------------------------------------------------------------------
# 1. validation
# ---------------------------------------------------------------------------


def test_init_rejects_empty_islands() -> None:
    with pytest.raises(ValueError, match="islands"):
        IslandModel(islands=[])


def test_init_rejects_negative_migration_size() -> None:
    with pytest.raises(ValueError, match="migration_size"):
        IslandModel(islands=[_make_pop([1.0])], migration_size=-1)


def test_init_rejects_zero_interval() -> None:
    with pytest.raises(ValueError, match="migration_interval"):
        IslandModel(islands=[_make_pop([1.0])], migration_interval=0)


def test_init_rejects_unknown_topology() -> None:
    with pytest.raises(ValueError, match="topology"):
        IslandModel(islands=[_make_pop([1.0])], topology="mesh")  # type: ignore[arg-type]


def test_init_rejects_unknown_policy() -> None:
    with pytest.raises(ValueError, match="migration_policy"):
        IslandModel(
            islands=[_make_pop([1.0])], migration_policy="elite"  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# 2. topology neighbors
# ---------------------------------------------------------------------------


def test_ring_neighbors() -> None:
    model = _make_3_islands()
    model.topology = "ring"
    assert model.neighbors(0) == [1]
    assert model.neighbors(1) == [2]
    assert model.neighbors(2) == [0]  # ring closes


def test_fully_connected_neighbors() -> None:
    model = _make_3_islands()
    model.topology = "fully"
    assert set(model.neighbors(0)) == {1, 2}
    assert set(model.neighbors(1)) == {0, 2}


def test_star_neighbors() -> None:
    model = _make_3_islands()
    model.topology = "star"
    assert model.neighbors(0) == [1, 2]  # center
    assert model.neighbors(1) == [0]
    assert model.neighbors(2) == [0]


# ---------------------------------------------------------------------------
# 3. select_emigrants policy
# ---------------------------------------------------------------------------


def test_select_emigrants_best() -> None:
    model = _make_3_islands([5])
    model.migration_size = 2
    model.migration_policy = "best"
    rng = np.random.default_rng(0)
    ems = model.select_emigrants(0, rng)
    scores = sorted([e.fitness.score for e in ems], reverse=True)
    # best 2 should be the top 2 (originally 0.4, 0.3 in island 0)
    assert scores[0] == pytest.approx(0.4)
    assert scores[1] == pytest.approx(0.3)


def test_select_emigrants_worst() -> None:
    model = _make_3_islands([5])
    model.migration_size = 2
    model.migration_policy = "worst"
    rng = np.random.default_rng(0)
    ems = model.select_emigrants(0, rng)
    scores = sorted([e.fitness.score for e in ems])
    assert scores[0] == pytest.approx(0.0)
    assert scores[1] == pytest.approx(0.1)


def test_select_emigrants_random_count() -> None:
    model = _make_3_islands([5])
    model.migration_size = 3
    model.migration_policy = "random"
    rng = np.random.default_rng(0)
    ems = model.select_emigrants(0, rng)
    assert len(ems) == 3


def test_select_emigrants_zero_size() -> None:
    model = _make_3_islands([5])
    model.migration_size = 0
    rng = np.random.default_rng(0)
    assert model.select_emigrants(0, rng) == []


# ---------------------------------------------------------------------------
# 4. migrate
# ---------------------------------------------------------------------------


def test_migrate_ring_preserves_total_size() -> None:
    model = _make_3_islands([5, 5, 5])
    total_before = model.total_size()
    rng = np.random.default_rng(0)
    stats = model.migrate(rng)
    assert model.total_size() == total_before
    assert stats["total_migrants"] > 0


def test_migrate_ring_moves_best_to_next() -> None:
    model = _make_3_islands([3, 3, 3])
    model.migration_size = 1
    model.migration_policy = "best"
    rng = np.random.default_rng(0)
    sizes_before = model.island_sizes()
    model.migrate(rng)
    sizes_after = model.island_sizes()
    # 各 island で 1 体出て 1 体入る (ring なので size 不変)
    assert sizes_after == sizes_before


def test_migrate_respects_interval() -> None:
    model = _make_3_islands()
    model.migration_interval = 3
    rng = np.random.default_rng(0)
    stats1 = model.migrate(rng)
    assert stats1["total_migrants"] == 0
    stats2 = model.migrate(rng)
    assert stats2["total_migrants"] == 0
    stats3 = model.migrate(rng)
    assert stats3["total_migrants"] > 0


def test_migrate_single_island_no_op() -> None:
    model = IslandModel(islands=[_make_pop([1.0, 2.0])])
    rng = np.random.default_rng(0)
    stats = model.migrate(rng)
    assert stats["total_migrants"] == 0


def test_migrate_star_topology() -> None:
    model = _make_3_islands([4, 4, 4])
    model.topology = "star"
    model.migration_size = 2
    rng = np.random.default_rng(0)
    sizes_before = model.island_sizes()
    model.migrate(rng)
    # 中心 (idx 0) は 2 つの neighbor (1, 2) に送る = 各 1 個ずつ + 各
    # neighbor から 1 個受ける (size 2)
    # → 中心 island は 4 - 2 + 2 = 4
    assert model.island_sizes()[0] == sizes_before[0]
    assert model.total_size() == sum(sizes_before)
