# SPDX-License-Identifier: Apache-2.0
"""MutualScorePairSelector + LexicaseSelection (v0.E CE-30/34) tests."""

from __future__ import annotations

import numpy as np
import pytest

from llive.perf.evolutionary import (
    FitnessReport,
    Genome,
    GenomeBounds,
    Individual,
    LexicaseSelection,
    MutualScorePairSelector,
    PeerEvaluationMatrix,
    Population,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_population(ids: list[str]) -> Population:
    bounds = GenomeBounds(lower=(0.0,), upper=(1.0,))
    inds = []
    for aid in ids:
        ind = Individual.from_genome(Genome.from_values((0.5,), bounds=bounds))
        # individual_id を override
        ind.individual_id = aid
        inds.append(ind)
    return Population(individuals=inds, bounds=bounds, seed=0)


# ---------------------------------------------------------------------------
# 1. MutualScorePairSelector
# ---------------------------------------------------------------------------


def test_mutual_score_matrix_symmetric() -> None:
    m = PeerEvaluationMatrix.empty(["a", "b", "c"])
    m.record("a", "b", 0.8)
    m.record("b", "a", 0.6)
    sel = MutualScorePairSelector(matrix=m)
    ms = sel.mutual_score_matrix()
    assert ms.shape == (3, 3)
    assert ms[0, 1] == pytest.approx((0.8 + 0.6) / 2)
    assert ms[1, 0] == pytest.approx(ms[0, 1])


def test_select_pair_prefers_high_mutual() -> None:
    """high mutual pair (a, b) を temperature 低めで選ばせると頻出."""
    m = PeerEvaluationMatrix.empty(["a", "b", "c", "d"])
    # (a, b) は互いに 0.95 で殆ど常に好き
    m.record("a", "b", 0.95)
    m.record("b", "a", 0.95)
    # 他は低め
    for i in ("a", "b", "c", "d"):
        for j in ("a", "b", "c", "d"):
            if i != j and not (i in {"a", "b"} and j in {"a", "b"}):
                m.record(i, j, 0.1)
    pop = _make_population(["a", "b", "c", "d"])
    sel = MutualScorePairSelector(matrix=m, temperature=0.1)
    rng = np.random.default_rng(0)
    counts = {"ab_or_ba": 0, "other": 0}
    for _ in range(50):
        i, j = sel.select_pair(pop, rng)
        ids = {i.individual_id, j.individual_id}
        if ids == {"a", "b"}:
            counts["ab_or_ba"] += 1
        else:
            counts["other"] += 1
    assert counts["ab_or_ba"] > counts["other"]


def test_select_pair_no_pair_above_min_uniform_fallback() -> None:
    m = PeerEvaluationMatrix.empty(["a", "b"])
    m.record("a", "b", 0.05)
    m.record("b", "a", 0.05)
    pop = _make_population(["a", "b"])
    sel = MutualScorePairSelector(
        matrix=m, min_mutual=0.5, rng_fallback_uniform=True
    )
    rng = np.random.default_rng(0)
    i, j = sel.select_pair(pop, rng)
    assert i.individual_id != j.individual_id


def test_select_pair_no_pair_above_min_raises() -> None:
    m = PeerEvaluationMatrix.empty(["a", "b"])
    m.record("a", "b", 0.05)
    m.record("b", "a", 0.05)
    pop = _make_population(["a", "b"])
    sel = MutualScorePairSelector(
        matrix=m, min_mutual=0.9, rng_fallback_uniform=False
    )
    rng = np.random.default_rng(0)
    with pytest.raises(ValueError, match="min_mutual"):
        sel.select_pair(pop, rng)


def test_select_pair_rejects_single_individual() -> None:
    m = PeerEvaluationMatrix.empty(["a"])
    pop = _make_population(["a"])
    sel = MutualScorePairSelector(matrix=m)
    rng = np.random.default_rng(0)
    with pytest.raises(ValueError, match="at least 2"):
        sel.select_pair(pop, rng)


def test_select_pair_rejects_invalid_temperature() -> None:
    m = PeerEvaluationMatrix.empty(["a", "b"])
    with pytest.raises(ValueError, match="temperature"):
        MutualScorePairSelector(matrix=m, temperature=0.0)


def test_select_pairs_returns_n() -> None:
    m = PeerEvaluationMatrix.empty(["a", "b", "c"])
    m.record("a", "b", 0.5)
    m.record("b", "a", 0.5)
    m.record("a", "c", 0.5)
    m.record("c", "a", 0.5)
    pop = _make_population(["a", "b", "c"])
    sel = MutualScorePairSelector(matrix=m)
    rng = np.random.default_rng(0)
    pairs = sel.select_pairs(pop, rng, n_pairs=4)
    assert len(pairs) == 4
    for p1, p2 in pairs:
        assert p1.individual_id != p2.individual_id


# ---------------------------------------------------------------------------
# 2. LexicaseSelection
# ---------------------------------------------------------------------------


def _ind_with_breakdown(aid: str, breakdown: dict[str, float]) -> Individual:
    bounds = GenomeBounds(lower=(0.0,), upper=(1.0,))
    ind = Individual.from_genome(Genome.from_values((0.5,), bounds=bounds))
    ind.individual_id = aid
    ind.fitness = FitnessReport(
        score=float(sum(breakdown.values())) / max(1, len(breakdown)),
        breakdown=dict(breakdown),
    )
    return ind


def test_lexicase_picks_specialist_for_single_criterion() -> None:
    inds = [
        _ind_with_breakdown("gen", {"peer_score": 0.5, "novelty": 0.5}),
        _ind_with_breakdown("peer_spec", {"peer_score": 0.95, "novelty": 0.05}),
        _ind_with_breakdown("nov_spec", {"peer_score": 0.05, "novelty": 0.95}),
    ]
    bounds = GenomeBounds(lower=(0.0,), upper=(1.0,))
    pop = Population(individuals=inds, bounds=bounds, seed=0)
    sel = LexicaseSelection(criteria=("peer_score", "novelty"))
    # 100 trials で peer_spec と nov_spec が拮抗するはず
    counts = {"peer_spec": 0, "nov_spec": 0, "gen": 0}
    rng = np.random.default_rng(0)
    for _ in range(100):
        chosen = sel(pop, rng)
        counts[chosen.individual_id] += 1
    # specialist が generalist より選ばれやすい
    assert counts["peer_spec"] + counts["nov_spec"] > counts["gen"]


def test_lexicase_handles_missing_breakdown_key() -> None:
    inds = [
        _ind_with_breakdown("a", {"peer_score": 0.9}),  # novelty なし
        _ind_with_breakdown("b", {"novelty": 0.9}),  # peer_score なし
    ]
    bounds = GenomeBounds(lower=(0.0,), upper=(1.0,))
    pop = Population(individuals=inds, bounds=bounds, seed=0)
    sel = LexicaseSelection(criteria=("peer_score", "novelty"))
    rng = np.random.default_rng(0)
    chosen = sel(pop, rng)
    assert chosen.individual_id in {"a", "b"}


def test_lexicase_rejects_empty_criteria() -> None:
    with pytest.raises(ValueError, match="criteria"):
        LexicaseSelection(criteria=())


def test_lexicase_rejects_invalid_epsilon() -> None:
    with pytest.raises(ValueError, match="epsilon"):
        LexicaseSelection(criteria=("x",), epsilon=-0.1)


def test_lexicase_lower_is_better() -> None:
    """latency_ms のように低い方が良い基準でも動く."""
    inds = [
        _ind_with_breakdown("slow", {"latency_ms": 100.0}),
        _ind_with_breakdown("fast", {"latency_ms": 5.0}),
    ]
    bounds = GenomeBounds(lower=(0.0,), upper=(1.0,))
    pop = Population(individuals=inds, bounds=bounds, seed=0)
    sel = LexicaseSelection(criteria=("latency_ms",), higher_is_better=False)
    rng = np.random.default_rng(0)
    chosen = sel(pop, rng)
    assert chosen.individual_id == "fast"


def test_lexicase_rejects_empty_population() -> None:
    bounds = GenomeBounds(lower=(0.0,), upper=(1.0,))
    pop = Population(individuals=[], bounds=bounds, seed=0)
    sel = LexicaseSelection(criteria=("x",))
    rng = np.random.default_rng(0)
    with pytest.raises(ValueError, match="empty"):
        sel(pop, rng)
