# SPDX-License-Identifier: Apache-2.0
"""OKA-07 — InsightScorer tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from llive.brief import BriefLedger
from llive.oka import (
    CoreEssence,
    GroundTruthEssence,
    InsightScore,
    InsightScorer,
)


def test_perfect_match_yields_top_scores() -> None:
    cand = CoreEssence(
        problem_text="x",
        mystery="保存則について",
        invariants=("総和",),
        symmetries=("回転",),
        essence_summary="保存則と回転対称",
    )
    gt = GroundTruthEssence(
        essence_summary="保存則と回転対称",
        mystery="保存則について",
        invariants=("総和",),
        symmetries=("回転",),
    )
    s = InsightScorer().score(cand, gt)
    assert isinstance(s, InsightScore)
    assert s.coverage == pytest.approx(1.0)
    assert s.alignment == pytest.approx(1.0)
    assert s.succinctness == pytest.approx(1.0)


def test_partial_match_drops_coverage() -> None:
    cand = CoreEssence(
        problem_text="x",
        mystery="",
        invariants=(),
        symmetries=(),
        essence_summary="保存則",
    )
    gt = GroundTruthEssence(
        essence_summary="保存則と回転対称と離散時間",
    )
    s = InsightScorer().score(cand, gt)
    assert s.coverage < 1.0
    assert s.insight_score < 0.9


def test_succinctness_penalises_long_candidate() -> None:
    cand = CoreEssence(
        problem_text="x",
        mystery="",
        invariants=(),
        symmetries=(),
        essence_summary="A" * 200,
    )
    gt = GroundTruthEssence(essence_summary="A" * 50)
    s = InsightScorer().score(cand, gt)
    assert s.succinctness < 1.0


def test_insight_score_within_unit_interval() -> None:
    cand = CoreEssence(
        problem_text="x", mystery="", invariants=(), symmetries=(),
        essence_summary="something",
    )
    gt = GroundTruthEssence(essence_summary="ground truth here")
    s = InsightScorer().score(cand, gt)
    assert 0.0 <= s.insight_score <= 1.0


def test_ledger_integration(tmp_path: Path) -> None:
    ledger = BriefLedger(tmp_path / "i.jsonl")
    cand = CoreEssence(
        problem_text="x", mystery="m", invariants=("a",), symmetries=("b",),
        essence_summary="m a b",
    )
    gt = GroundTruthEssence(essence_summary="m a b", invariants=("a",), symmetries=("b",))
    InsightScorer(ledger=ledger).score(cand, gt)
    events = [r for r in ledger.read() if r.event == "insight_score_recorded"]
    assert events
    tg = ledger.trace_graph()
    assert any(d["event"] == "insight_score_recorded" for d in tg.decision_chain)


def test_custom_weights_respected() -> None:
    cand = CoreEssence(
        problem_text="x", mystery="", invariants=(), symmetries=(),
        essence_summary="保存則",
    )
    gt = GroundTruthEssence(essence_summary="保存則と回転対称")
    s1 = InsightScorer(weights={"coverage": 1.0, "succinctness": 0.0, "alignment": 0.0}).score(cand, gt)
    s2 = InsightScorer(weights={"coverage": 0.0, "succinctness": 1.0, "alignment": 0.0}).score(cand, gt)
    # succinctness all-on gives full mark; coverage all-on gives partial
    assert s2.insight_score >= s1.insight_score
