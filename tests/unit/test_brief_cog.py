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
