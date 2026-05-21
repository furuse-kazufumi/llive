# SPDX-License-Identifier: Apache-2.0
"""NSGA-II MultiObjectiveFitness (v0.E CE-31) tests."""

from __future__ import annotations

import numpy as np
import pytest

from llive.perf.evolutionary import (
    FitnessReport,
    Genome,
    GenomeBounds,
    Individual,
    NSGA2Selection,
    Population,
    crowding_distance,
    non_dominated_sort,
)


def _make_ind(aid: str, breakdown: dict[str, float]) -> Individual:
    b = GenomeBounds(lower=(0.0,), upper=(1.0,))
    ind = Individual.from_genome(Genome.from_values((0.5,), bounds=b))
    ind.individual_id = aid
    ind.fitness = FitnessReport(
        score=sum(breakdown.values()) / max(1, len(breakdown)),
        breakdown=dict(breakdown),
    )
    return ind


# ---------------------------------------------------------------------------
# 1. non_dominated_sort
# ---------------------------------------------------------------------------


def test_sort_single_objective() -> None:
    inds = [
        _make_ind("a", {"x": 1.0}),
        _make_ind("b", {"x": 2.0}),
        _make_ind("c", {"x": 3.0}),
    ]
    fronts = non_dominated_sort(inds, objectives=("x",))
    # 単一 obj なら 3 front (c > b > a)
    assert len(fronts) == 3
    assert fronts[0][0].individual_id == "c"
    assert fronts[1][0].individual_id == "b"
    assert fronts[2][0].individual_id == "a"


def test_sort_two_objectives_pareto_optimal() -> None:
    """互いに dominate しない 2 個体は同 front."""
    inds = [
        _make_ind("trade_a", {"speed": 0.9, "quality": 0.1}),
        _make_ind("trade_b", {"speed": 0.1, "quality": 0.9}),
        _make_ind("dominated", {"speed": 0.5, "quality": 0.05}),
    ]
    fronts = non_dominated_sort(inds, objectives=("speed", "quality"))
    assert len(fronts) == 2  # rank 0 + rank 1
    front0_ids = {ind.individual_id for ind in fronts[0]}
    assert front0_ids == {"trade_a", "trade_b"}
    assert fronts[1][0].individual_id == "dominated"


def test_sort_lower_is_better_objective() -> None:
    inds = [
        _make_ind("fast", {"latency": 5.0}),
        _make_ind("slow", {"latency": 100.0}),
    ]
    fronts = non_dominated_sort(
        inds, objectives=("latency",), higher_is_better=(False,)
    )
    assert fronts[0][0].individual_id == "fast"
    assert fronts[1][0].individual_id == "slow"


def test_sort_empty() -> None:
    assert non_dominated_sort([], objectives=("x",)) == []


def test_sort_rejects_length_mismatch() -> None:
    inds = [_make_ind("a", {"x": 1.0})]
    with pytest.raises(ValueError, match="higher_is_better length"):
        non_dominated_sort(
            inds, objectives=("x", "y"), higher_is_better=(True,)
        )


def test_sort_handles_missing_breakdown_keys() -> None:
    inds = [
        _make_ind("a", {"x": 1.0}),
        _make_ind("b", {"y": 2.0}),  # x なし
    ]
    fronts = non_dominated_sort(inds, objectives=("x",))
    # x 持つ a が x なし b を dominate
    assert fronts[0][0].individual_id == "a"


# ---------------------------------------------------------------------------
# 2. crowding_distance
# ---------------------------------------------------------------------------


def test_crowding_distance_endpoints_infinity() -> None:
    inds = [
        _make_ind("a", {"x": 0.0, "y": 1.0}),
        _make_ind("b", {"x": 0.5, "y": 0.5}),
        _make_ind("c", {"x": 1.0, "y": 0.0}),
    ]
    d = crowding_distance(inds, objectives=("x", "y"))
    assert d["a"] == float("inf")
    assert d["c"] == float("inf")
    assert d["b"] != float("inf")


def test_crowding_distance_uniform_spacing() -> None:
    inds = [
        _make_ind("a", {"x": 0.0}),
        _make_ind("b", {"x": 0.5}),
        _make_ind("c", {"x": 1.0}),
    ]
    d = crowding_distance(inds, objectives=("x",))
    # 内点 b の距離 = (1.0 - 0.0) / (1.0 - 0.0) = 1.0
    assert d["b"] == pytest.approx(1.0)


def test_crowding_distance_small_front() -> None:
    inds = [_make_ind("a", {"x": 1.0}), _make_ind("b", {"x": 2.0})]
    d = crowding_distance(inds, objectives=("x",))
    assert d["a"] == float("inf")
    assert d["b"] == float("inf")


# ---------------------------------------------------------------------------
# 3. NSGA2Selection
# ---------------------------------------------------------------------------


def test_selection_prefers_lower_rank() -> None:
    inds = [
        _make_ind("front0_a", {"x": 0.9, "y": 0.1}),
        _make_ind("front0_b", {"x": 0.1, "y": 0.9}),
        _make_ind("front1", {"x": 0.5, "y": 0.05}),  # dominated
    ]
    bounds = GenomeBounds(lower=(0.0,), upper=(1.0,))
    pop = Population(individuals=inds, bounds=bounds, seed=0)
    sel = NSGA2Selection(objectives=("x", "y"))
    rng = np.random.default_rng(0)
    counts = {"front0": 0, "front1": 0}
    for _ in range(100):
        chosen = sel(pop, rng)
        if chosen.individual_id in {"front0_a", "front0_b"}:
            counts["front0"] += 1
        else:
            counts["front1"] += 1
    # rank 0 が rank 1 より圧倒的に選ばれる
    assert counts["front0"] > counts["front1"] * 2


def test_selection_validates_objectives() -> None:
    with pytest.raises(ValueError, match="objectives"):
        NSGA2Selection(objectives=())


def test_selection_single_individual() -> None:
    inds = [_make_ind("a", {"x": 1.0})]
    bounds = GenomeBounds(lower=(0.0,), upper=(1.0,))
    pop = Population(individuals=inds, bounds=bounds, seed=0)
    sel = NSGA2Selection(objectives=("x",))
    rng = np.random.default_rng(0)
    chosen = sel(pop, rng)
    assert chosen.individual_id == "a"


def test_selection_within_same_rank_prefers_high_crowding() -> None:
    """同 front で crowding distance 大の中間個体 vs 端点 → 端点が ∞ で勝つ."""
    inds = [
        _make_ind("end_a", {"x": 0.0, "y": 1.0}),
        _make_ind("middle", {"x": 0.5, "y": 0.5}),
        _make_ind("end_b", {"x": 1.0, "y": 0.0}),
    ]
    bounds = GenomeBounds(lower=(0.0,), upper=(1.0,))
    pop = Population(individuals=inds, bounds=bounds, seed=0)
    sel = NSGA2Selection(objectives=("x", "y"))
    rng = np.random.default_rng(0)
    counts = {"end": 0, "middle": 0}
    for _ in range(100):
        chosen = sel(pop, rng)
        if chosen.individual_id in {"end_a", "end_b"}:
            counts["end"] += 1
        else:
            counts["middle"] += 1
    # crowding が ∞ の端点が圧倒的に選ばれる
    assert counts["end"] > counts["middle"] * 2
