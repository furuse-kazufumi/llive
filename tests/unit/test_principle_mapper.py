# SPDX-License-Identifier: Apache-2.0
"""TRIZ-03 Principle Mapper tests."""

from __future__ import annotations

from llive.triz.contradiction import Contradiction
from llive.triz.loader import Principle
from llive.triz.principle_mapper import map_contradiction


def _make_contradiction(improve: int = 9, degrade: int = 13) -> Contradiction:
    return Contradiction(
        contradiction_id="c1",
        improve_metric="pipeline.latency_ms",
        degrade_metric="evolution.forgetting",
        improve_feature_id=improve,
        degrade_feature_id=degrade,
        severity=0.6,
        evidence={"delta_improve_relative": -0.1, "delta_degrade_relative": 0.1},
    )


def test_known_pair_returns_recommendations():
    res = map_contradiction(_make_contradiction(9, 13), top_k=3)
    assert res.contradiction_id == "c1"
    assert res.improving_id == 9
    assert res.worsening_id == 13
    # Real TRIZ matrix has entries for (9, 13); the loader should resolve at least one principle.
    assert len(res.recommendations) >= 1


def test_top_k_respected():
    res = map_contradiction(_make_contradiction(9, 13), top_k=1)
    assert len(res.recommendations) <= 1


def test_top_k_zero_returns_empty_list():
    res = map_contradiction(_make_contradiction(9, 13), top_k=0)
    assert res.recommendations == []


def test_unknown_pair_falls_back():
    # Use a pair guaranteed to be missing from the matrix.
    res = map_contradiction(_make_contradiction(99, 98), top_k=2)
    assert res.fallback_used is True
    # Fallback library has principles 1, 13, 15, 35, 40
    assert len(res.recommendations) <= 2


def test_recommendations_sorted_by_score():
    res = map_contradiction(_make_contradiction(9, 13), top_k=5)
    scores = [r.score for r in res.recommendations]
    assert scores == sorted(scores, reverse=True)


def test_rank_is_one_indexed():
    res = map_contradiction(_make_contradiction(9, 13), top_k=2)
    for i, rec in enumerate(res.recommendations, start=1):
        assert rec.rank == i


def test_custom_matrix_and_index():
    custom_matrix = {(1, 2): (10, 20)}
    custom_principles = {
        10: Principle(id=10, name="Preliminary action"),
        20: Principle(id=20, name="Beforehand cushioning"),
    }
    contra = Contradiction(
        contradiction_id="c",
        improve_metric="x",
        degrade_metric="y",
        improve_feature_id=1,
        degrade_feature_id=2,
        severity=0.5,
        evidence={},
    )
    res = map_contradiction(
        contra, top_k=2, matrix=custom_matrix, principles_index=custom_principles
    )
    assert {r.principle.id for r in res.recommendations} == {10, 20}
    assert res.fallback_used is False


def test_examples_boost_score():
    custom_matrix = {(1, 2): (10, 11)}
    custom_principles = {
        10: Principle(id=10, name="A", examples=("ex1", "ex2", "ex3")),
        11: Principle(id=11, name="B"),
    }
    contra = Contradiction(
        contradiction_id="c",
        improve_metric="x",
        degrade_metric="y",
        improve_feature_id=1,
        degrade_feature_id=2,
        severity=0.5,
        evidence={},
    )
    res = map_contradiction(
        contra, top_k=2, matrix=custom_matrix, principles_index=custom_principles
    )
    # Principle 10 has examples and should rank above 11.
    assert res.recommendations[0].principle.id == 10
    assert res.recommendations[0].score > res.recommendations[1].score
