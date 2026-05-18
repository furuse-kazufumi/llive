# SPDX-License-Identifier: Apache-2.0
"""Tests for COG-MESH-02 TitleRecallPlanner."""

from __future__ import annotations

import pytest

from llive.cognitive_mesh.title_recall import (
    RecallStatus,
    TitleRecallPlanner,
)

# ---------------------------------------------------------------------------
# 起 — setup
# ---------------------------------------------------------------------------


def test_setup_creates_pending_foreshadow() -> None:
    planner = TitleRecallPlanner()
    fs = planner.setup(text="build success", tag="build")
    assert fs.status == RecallStatus.PENDING
    assert fs.tag == "build"
    assert fs.set_at is not None
    assert fs in planner.pending()


def test_setup_duplicate_tag_rejected() -> None:
    planner = TitleRecallPlanner()
    planner.setup("hello", tag="greet")
    with pytest.raises(ValueError, match="already set"):
        planner.setup("hi", tag="greet")


# ---------------------------------------------------------------------------
# 結 — evaluate
# ---------------------------------------------------------------------------


def test_evaluate_full_recovery() -> None:
    planner = TitleRecallPlanner()
    planner.setup("build success", tag="build", weight=1.0)
    planner.setup("test pass", tag="test", weight=1.0)
    report = planner.evaluate("build success and test pass")
    assert report.recall_rate == 1.0
    assert report.unrecovered == []


def test_evaluate_partial_recovery() -> None:
    planner = TitleRecallPlanner()
    planner.setup("build success", tag="build", weight=1.0)
    planner.setup("deploy complete", tag="deploy", weight=1.0)
    report = planner.evaluate("build success but deployment broken")
    # build success は full match、deploy complete は 1/2 (deploy 含む、complete なし)
    # → recovered_weight = 1.0 + 1.0*0.5 = 1.5、total = 2.0、rate = 0.75
    assert 0.7 <= report.recall_rate <= 0.8
    assert len(report.unrecovered) == 0  # 両方 >=0.5 で recovered


def test_evaluate_misses() -> None:
    planner = TitleRecallPlanner()
    planner.setup("important detail XYZ", tag="detail")
    report = planner.evaluate("totally unrelated content")
    assert report.recall_rate == 0.0
    assert len(report.unrecovered) == 1
    assert report.unrecovered[0].status == RecallStatus.MISSED


def test_evaluate_respects_weight() -> None:
    planner = TitleRecallPlanner()
    planner.setup("alpha", tag="a", weight=3.0)
    planner.setup("beta", tag="b", weight=1.0)
    # alpha は recovered、beta は missed
    report = planner.evaluate("alpha is here")
    # recovered_weight = 3.0、total = 4.0、rate = 0.75
    assert report.recall_rate == pytest.approx(0.75)
    assert report.unrecovered[0].tag == "b"


def test_evaluate_marks_status() -> None:
    planner = TitleRecallPlanner()
    planner.setup("foo", tag="x")
    planner.setup("bar", tag="y")
    planner.evaluate("foo only")
    assert planner._foreshadows["x"].status == RecallStatus.RECOVERED
    assert planner._foreshadows["y"].status == RecallStatus.MISSED


def test_unrecovered_foreshadows_after_evaluate() -> None:
    planner = TitleRecallPlanner()
    planner.setup("a", tag="a")
    planner.setup("b", tag="b")
    planner.evaluate("a is here")
    unrec = planner.unrecovered_foreshadows()
    assert len(unrec) == 1
    assert unrec[0].tag == "b"


def test_evaluate_zero_total_weight_returns_zero() -> None:
    planner = TitleRecallPlanner()
    report = planner.evaluate("anything")
    assert report.recall_rate == 0.0
    assert report.total_weight == 0.0
