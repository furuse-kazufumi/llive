# SPDX-License-Identifier: Apache-2.0
"""EVO-06 Failed-Candidate Reservoir tests."""

from __future__ import annotations

import pytest

from llive.evolution.reservoir import (
    FailedCandidate,
    FailedCandidateReservoir,
    ReservoirSummary,
)


@pytest.fixture
def res(tmp_path):
    db = tmp_path / "reservoir.duckdb"
    r = FailedCandidateReservoir(db)
    yield r
    r.close()


def test_record_and_count(res):
    fc = FailedCandidate.new(diff={"target_container": "t"}, reason="verifier", rejector="self_reflection")
    res.record(fc)
    assert res.count() == 1
    assert res.count(reason="verifier") == 1
    assert res.count(reason="bench") == 0


def test_invalid_reason_rejected():
    with pytest.raises(ValueError):
        FailedCandidate.new(diff={}, reason="not_a_real_reason", rejector="x")


def test_list_returns_recent_first(res):
    a = FailedCandidate.new(diff={"a": 1}, reason="bench", rejector="r1", mutation_policy="triz_inspired")
    b = FailedCandidate.new(diff={"b": 2}, reason="hitl", rejector="r2", mutation_policy="llm_generated")
    res.record(a)
    res.record(b)
    rows = res.list(limit=10)
    # b inserted after a -> newer -> first
    assert rows[0].diff == {"b": 2}
    assert rows[1].diff == {"a": 1}


def test_list_filter_by_policy(res):
    res.record(FailedCandidate.new(diff={"x": 1}, reason="bench", rejector="r", mutation_policy="triz_inspired"))
    res.record(FailedCandidate.new(diff={"x": 2}, reason="bench", rejector="r", mutation_policy="llm_generated"))
    triz_only = res.list(mutation_policy="triz_inspired")
    assert len(triz_only) == 1
    assert triz_only[0].mutation_policy == "triz_inspired"


def test_summary_groups_correctly(res):
    res.record(FailedCandidate.new(diff={}, reason="verifier", rejector="x", mutation_policy="triz_inspired"))
    res.record(FailedCandidate.new(diff={}, reason="verifier", rejector="x", mutation_policy="triz_inspired"))
    res.record(FailedCandidate.new(diff={}, reason="bench", rejector="y", mutation_policy="llm_generated"))
    summary = res.summary()
    assert isinstance(summary, ReservoirSummary)
    assert summary.count == 3
    assert summary.by_reason["verifier"] == 2
    assert summary.by_reason["bench"] == 1
    assert summary.by_policy["triz_inspired"] == 2


def test_sample_returns_at_most_k(res):
    for i in range(20):
        res.record(FailedCandidate.new(diff={"i": i}, reason="bench", rejector="r"))
    samples = res.sample(k=5)
    assert len(samples) <= 5


def test_prune_keeps_recent(res):
    for i in range(10):
        res.record(FailedCandidate.new(diff={"i": i}, reason="bench", rejector="r"))
    deleted = res.prune(keep_last=3)
    assert deleted == 7
    assert res.count() == 3


def test_prune_no_op_when_under_threshold(res):
    res.record(FailedCandidate.new(diff={"i": 1}, reason="bench", rejector="r"))
    assert res.prune(keep_last=10) == 0
    assert res.count() == 1


def test_prune_zero_clears_all(res):
    for i in range(3):
        res.record(FailedCandidate.new(diff={"i": i}, reason="bench", rejector="r"))
    assert res.prune(keep_last=0) == 3
    assert res.count() == 0


def test_prune_negative_rejected(res):
    with pytest.raises(ValueError):
        res.prune(keep_last=-1)


def test_score_bundle_roundtrip(res):
    fc = FailedCandidate.new(
        diff={"x": 1},
        reason="bench",
        rejector="r",
        score_bundle={"latency_ms": 12.5, "accuracy": 0.81},
    )
    res.record(fc)
    rows = res.list(limit=1)
    assert rows[0].score_bundle == {"latency_ms": 12.5, "accuracy": 0.81}


def test_context_manager(tmp_path):
    db = tmp_path / "r.duckdb"
    with FailedCandidateReservoir(db) as r:
        r.record(FailedCandidate.new(diff={}, reason="other", rejector="r"))
        assert r.count() == 1
