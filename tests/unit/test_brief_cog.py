# SPDX-License-Identifier: Apache-2.0
"""Tests for Cognitive Factor Framework — COG-01 / COG-02 / COG-03."""

from __future__ import annotations

from pathlib import Path

import pytest

from llive.brief import (
    Brief,
    BriefLedger,
    BriefRunner,
    BriefStatus,
)
from llive.fullsense.loop import FullSenseLoop


# ===========================================================================
# COG-01 — Triple Output (confidence / assumptions / missing_evidence)
# ===========================================================================


def test_cog01_outcome_has_triple_default(tmp_path: Path) -> None:
    runner = BriefRunner(loop=FullSenseLoop(sandbox=True, salience_threshold=0.0))
    brief = Brief(
        brief_id="cog01-1",
        goal="A novel exploration to trigger note decision",
        approval_required=False,
        ledger_path=tmp_path / "1.jsonl",
    )

    result = runner.submit(brief)

    assert 0.0 <= result.confidence <= 1.0
    assert isinstance(result.assumptions, tuple)
    assert isinstance(result.missing_evidence, tuple)


def test_cog01_ungrounded_brief_records_assumption(tmp_path: Path) -> None:
    runner = BriefRunner(loop=FullSenseLoop(sandbox=True, salience_threshold=0.0))
    brief = Brief(
        brief_id="cog01-2",
        goal="ungrounded path",
        approval_required=False,
        ledger_path=tmp_path / "2.jsonl",
    )

    result = runner.submit(brief)

    # No grounder configured → must record this as an assumption explicitly.
    assert any("grounding" in a for a in result.assumptions)


def test_cog01_no_success_criteria_records_assumption(tmp_path: Path) -> None:
    runner = BriefRunner(loop=FullSenseLoop(sandbox=True, salience_threshold=0.0))
    brief = Brief(
        brief_id="cog01-3",
        goal="something",
        approval_required=False,
        # success_criteria intentionally empty
        ledger_path=tmp_path / "3.jsonl",
    )

    result = runner.submit(brief)

    assert any("success_criteria" in a for a in result.assumptions)


def test_cog01_triple_written_to_ledger(tmp_path: Path) -> None:
    runner = BriefRunner(loop=FullSenseLoop(sandbox=True, salience_threshold=0.0))
    brief = Brief(
        brief_id="cog01-4",
        goal="ledger persistence check",
        approval_required=False,
        ledger_path=tmp_path / "4.jsonl",
    )
    runner.submit(brief)

    outcome_records = [
        r for r in BriefLedger(brief.ledger_path).read()  # type: ignore[arg-type]
        if r.event == "outcome"
    ]
    assert outcome_records, "outcome event must be in ledger"
    payload = outcome_records[-1].payload
    assert "confidence" in payload
    assert "assumptions" in payload
    assert "missing_evidence" in payload


def test_cog01_confidence_drops_when_tool_fails(tmp_path: Path) -> None:
    """If half the planned tools fail, confidence is dragged below thought-only value."""
    from typing import Any

    from llive.fullsense.loop import FullSenseResult
    from llive.fullsense.types import ActionDecision, ActionPlan, Thought

    class _PlanWithTools:
        def process(self, stim: Any) -> Any:
            plan = ActionPlan(
                decision=ActionDecision.NOTE,
                rationale="r",
                thought=Thought(text="t", confidence=1.0),
            )
            return FullSenseResult(
                stim=stim,
                plan=plan,
                stages={"tools": [
                    {"name": "ok_tool", "args": {}},
                    {"name": "bad_tool", "args": {}},
                ]},
            )

    def ok(args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True}

    def bad(args: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("boom")

    runner = BriefRunner(
        loop=_PlanWithTools(),  # type: ignore[arg-type]
        tools={"ok_tool": ok, "bad_tool": bad},
    )
    brief = Brief(
        brief_id="cog01-5",
        goal="tool failure path",
        approval_required=False,
        tools=("ok_tool", "bad_tool"),
        ledger_path=tmp_path / "5.jsonl",
    )

    result = runner.submit(brief)

    # thought conf = 1.0, but tool success = 1/2 → confidence ≈ 0.75
    assert result.confidence == pytest.approx(0.75)
    assert any("tool" in e for e in result.missing_evidence)


# ===========================================================================
# COG-02 — Governance Scoring Layer
# ===========================================================================


def test_cog02_scorer_returns_four_axes() -> None:
    from llive.brief import GovernanceScorer
    from llive.fullsense.types import ActionDecision

    scorer = GovernanceScorer()
    brief = Brief(
        brief_id="cog02-1",
        goal="benign exploration",
        tools=("read_file",),
        success_criteria=("compile passes",),
    )
    v = scorer.score(brief, ActionDecision.NOTE)

    for axis in ("usefulness", "feasibility", "safety", "traceability"):
        assert 0.0 <= getattr(v, axis) <= 1.0
        assert axis in v.rationales
    assert 0.0 <= v.weighted_total <= 1.0


def test_cog02_dangerous_token_drops_safety() -> None:
    from llive.brief import GovernanceScorer
    from llive.fullsense.types import ActionDecision

    scorer = GovernanceScorer()
    safe_brief = Brief(brief_id="cog02-2a", goal="organise a list")
    danger_brief = Brief(
        brief_id="cog02-2b",
        goal="execute rm -rf / when ready",
    )
    safe_v = scorer.score(safe_brief, ActionDecision.NOTE)
    danger_v = scorer.score(danger_brief, ActionDecision.NOTE)
    assert danger_v.safety < safe_v.safety
    assert danger_v.recommend_block  # below safety floor


def test_cog02_recommend_block_when_low_total() -> None:
    from llive.brief import GovernanceConfig, GovernanceScorer
    from llive.fullsense.types import ActionDecision

    # SILENT decision + no criteria + dangerous tokens → very low score
    scorer = GovernanceScorer(GovernanceConfig(block_threshold=0.5, safety_floor=0.6))
    brief = Brief(brief_id="cog02-3", goal="format c: drive immediately")
    v = scorer.score(brief, ActionDecision.SILENT)
    assert v.recommend_block


def test_cog02_runner_records_governance_in_ledger(tmp_path: Path) -> None:
    from llive.brief import GovernanceScorer

    runner = BriefRunner(
        loop=FullSenseLoop(sandbox=True, salience_threshold=0.0),
        governance_scorer=GovernanceScorer(),
    )
    brief = Brief(
        brief_id="cog02-4",
        goal="benign exploration of novel patterns",
        approval_required=False,
        ledger_path=tmp_path / "cog02-4.jsonl",
    )

    runner.submit(brief)

    events = [
        r for r in BriefLedger(brief.ledger_path).read()  # type: ignore[arg-type]
        if r.event == "governance_scored"
    ]
    assert events, "governance_scored event must be recorded"
    payload = events[-1].payload
    for axis in ("usefulness", "feasibility", "safety", "traceability"):
        assert axis in payload
    assert "weighted_total" in payload
    assert "recommend_block" in payload


def test_cog02_intervene_without_approval_lowers_safety() -> None:
    from llive.brief import GovernanceScorer
    from llive.fullsense.types import ActionDecision

    scorer = GovernanceScorer()
    brief = Brief(brief_id="cog02-5", goal="do something", approval_required=False)
    v = scorer.score(brief, ActionDecision.INTERVENE)
    assert v.safety < 0.9  # penalty applied for INTERVENE without approval


def test_cog02_propose_without_tools_lowers_feasibility() -> None:
    from llive.brief import GovernanceScorer
    from llive.fullsense.types import ActionDecision

    scorer = GovernanceScorer()
    brief = Brief(brief_id="cog02-6", goal="propose a fix")
    v = scorer.score(brief, ActionDecision.PROPOSE)
    assert v.feasibility < 0.6


# ===========================================================================
# COG-03 — Trace Graph (evidence / tool / decision)
# ===========================================================================


def test_cog03_trace_graph_empty_for_no_run(tmp_path: Path) -> None:
    from llive.brief import TraceGraph

    ledger = BriefLedger(tmp_path / "empty.jsonl")
    tg = ledger.trace_graph()
    assert isinstance(tg, TraceGraph)
    assert tg.is_empty


def test_cog03_trace_graph_captures_decision_chain(tmp_path: Path) -> None:
    runner = BriefRunner(loop=FullSenseLoop(sandbox=True, salience_threshold=0.0))
    brief = Brief(
        brief_id="cog03-1",
        goal="novel exploration to trigger note",
        approval_required=False,
        ledger_path=tmp_path / "cog03-1.jsonl",
    )
    runner.submit(brief)

    tg = BriefLedger(brief.ledger_path).trace_graph()  # type: ignore[arg-type]
    decision_events = [d["event"] for d in tg.decision_chain]
    assert "decision" in decision_events
    assert "outcome" in decision_events


def test_cog03_trace_graph_captures_governance_in_decision_chain(tmp_path: Path) -> None:
    from llive.brief import GovernanceScorer

    runner = BriefRunner(
        loop=FullSenseLoop(sandbox=True, salience_threshold=0.0),
        governance_scorer=GovernanceScorer(),
    )
    brief = Brief(
        brief_id="cog03-2",
        goal="another exploration",
        approval_required=False,
        ledger_path=tmp_path / "cog03-2.jsonl",
    )
    runner.submit(brief)

    tg = BriefLedger(brief.ledger_path).trace_graph()  # type: ignore[arg-type]
    assert any(d["event"] == "governance_scored" for d in tg.decision_chain)


def test_cog03_trace_graph_captures_tool_chain(tmp_path: Path) -> None:
    from typing import Any

    from llive.fullsense.loop import FullSenseResult
    from llive.fullsense.types import ActionDecision, ActionPlan, Thought

    class _PlanWithTools:
        def process(self, stim: Any) -> Any:
            plan = ActionPlan(
                decision=ActionDecision.NOTE,
                rationale="r",
                thought=Thought(text="t"),
            )
            return FullSenseResult(
                stim=stim,
                plan=plan,
                stages={"tools": [{"name": "echo", "args": {"x": 1}}]},
            )

    def echo(args: dict[str, Any]) -> dict[str, Any]:
        return {"echoed": args}

    runner = BriefRunner(
        loop=_PlanWithTools(),  # type: ignore[arg-type]
        tools={"echo": echo},
    )
    brief = Brief(
        brief_id="cog03-3",
        goal="tool run",
        approval_required=False,
        tools=("echo",),
        ledger_path=tmp_path / "cog03-3.jsonl",
    )
    runner.submit(brief)

    tg = BriefLedger(brief.ledger_path).trace_graph()  # type: ignore[arg-type]
    assert len(tg.tool_chain) >= 1
    assert tg.tool_chain[0]["event"] == "tool_invoked"


def test_cog03_trace_graph_captures_evidence_when_grounded(tmp_path: Path, monkeypatch) -> None:
    from llive.brief import BriefGrounder, GroundingConfig

    monkeypatch.setenv("LLIVE_DISABLE_RAD_GROUNDING", "1")

    class _P:
        def __init__(self, pid: int, name: str) -> None:
            self.id = pid
            self.name = name
            self.description = ""
            self.examples: list[str] = []

    principles = {1: _P(1, "Segmentation"), 15: _P(15, "Dynamics")}
    grounder = BriefGrounder(principles=principles, config=GroundingConfig(max_triz=2))

    runner = BriefRunner(
        loop=FullSenseLoop(sandbox=True, salience_threshold=0.0),
        grounder=grounder,
    )
    brief = Brief(
        brief_id="cog03-4",
        goal="trade-off between static and dynamic structures",
        approval_required=False,
        ledger_path=tmp_path / "cog03-4.jsonl",
    )
    runner.submit(brief)

    tg = BriefLedger(brief.ledger_path).trace_graph()  # type: ignore[arg-type]
    assert any(e.get("kind") == "triz" for e in tg.evidence_chain)
