# SPDX-License-Identifier: Apache-2.0
"""BriefRunner ↔ MathVerifier integration tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from llive.brief import Brief, BriefLedger, BriefRunner, BriefStatus
from llive.fullsense.loop import FullSenseLoop, FullSenseResult
from llive.fullsense.types import ActionDecision, ActionPlan, Stimulus, Thought
from llive.math import MathVerifier


class _PlanLoop:
    """Mock loop that decides NOTE — tools list optional via plan attr."""

    def __init__(self, tools: list[dict[str, Any]] | None = None) -> None:
        self._tools = tools or []

    def process(self, stim: Stimulus) -> FullSenseResult:
        plan = ActionPlan(
            decision=ActionDecision.NOTE,
            rationale="benign note rationale for verifier integration test",
            thought=Thought(text="t", confidence=0.7),
        )
        return FullSenseResult(stim=stim, plan=plan, stages={"tools": self._tools})


def test_runner_binds_verifier_ledger_to_brief(tmp_path: Path) -> None:
    """`runner.math_verifier.check_*` should append events to the Brief's ledger."""
    verifier = MathVerifier(source_id="brief:bind-1")
    runner = BriefRunner(
        loop=FullSenseLoop(sandbox=True, salience_threshold=0.0),
        math_verifier=verifier,
    )
    brief = Brief(
        brief_id="vbind-1",
        goal="equivalence check for runner-bound verifier",
        approval_required=False,
        ledger_path=tmp_path / "vbind-1.jsonl",
    )

    # Tool handler invokes the verifier mid-Brief — typical real-world pattern.
    runner.submit(brief)
    # Verifier should now be bound to this brief's ledger.
    assert runner.math_verifier is verifier
    verifier.check_equivalence("x + 0", "x")
    verifier.check_implication(["x > 5"], "x > 3")

    ledger = BriefLedger(brief.ledger_path)  # type: ignore[arg-type]
    math_events = [r for r in ledger.read() if r.event == "math_verified"]
    assert len(math_events) == 2
    assert math_events[0].payload["verdict"] == "equivalent"
    assert math_events[1].payload["verdict"] == "valid"


def test_runner_verifier_redirects_across_briefs(tmp_path: Path) -> None:
    """One shared verifier across two Briefs — each event lands in its own ledger."""
    verifier = MathVerifier()
    runner = BriefRunner(
        loop=FullSenseLoop(sandbox=True, salience_threshold=0.0),
        math_verifier=verifier,
    )

    brief_a = Brief(
        brief_id="vbind-a",
        goal="first brief",
        approval_required=False,
        ledger_path=tmp_path / "a.jsonl",
    )
    brief_b = Brief(
        brief_id="vbind-b",
        goal="second brief",
        approval_required=False,
        ledger_path=tmp_path / "b.jsonl",
    )

    runner.submit(brief_a)
    verifier.check_equivalence("a", "a")  # writes to a.jsonl
    runner.submit(brief_b)
    verifier.check_satisfiable(["x > 0"])  # writes to b.jsonl

    a_math = [r for r in BriefLedger(brief_a.ledger_path).read() if r.event == "math_verified"]  # type: ignore[arg-type]
    b_math = [r for r in BriefLedger(brief_b.ledger_path).read() if r.event == "math_verified"]  # type: ignore[arg-type]
    assert len(a_math) == 1 and a_math[0].payload["kind"] == "equivalence"
    assert len(b_math) == 1 and b_math[0].payload["kind"] == "satisfiability"


def test_runner_trace_graph_includes_runner_bound_math(tmp_path: Path) -> None:
    """COG-03 trace_graph should reflect runner-routed math evidence."""
    verifier = MathVerifier()
    runner = BriefRunner(
        loop=FullSenseLoop(sandbox=True, salience_threshold=0.0),
        math_verifier=verifier,
    )
    brief = Brief(
        brief_id="vbind-tg",
        goal="trace graph integration",
        approval_required=False,
        ledger_path=tmp_path / "tg.jsonl",
    )
    runner.submit(brief)
    verifier.check_equivalence("(x+1)**2", "x*x + 2*x + 1")

    tg = BriefLedger(brief.ledger_path).trace_graph()  # type: ignore[arg-type]
    math_evidence = [e for e in tg.evidence_chain if e.get("kind") == "math"]
    assert len(math_evidence) == 1
    assert math_evidence[0]["check_kind"] == "equivalence"
    assert math_evidence[0]["verdict"] == "equivalent"


def test_runner_without_verifier_is_unaffected(tmp_path: Path) -> None:
    runner = BriefRunner(loop=FullSenseLoop(sandbox=True, salience_threshold=0.0))
    brief = Brief(
        brief_id="vbind-none",
        goal="no verifier wired",
        approval_required=False,
        ledger_path=tmp_path / "none.jsonl",
    )
    result = runner.submit(brief)
    assert result.status in (BriefStatus.COMPLETED, BriefStatus.SILENT)
    assert runner.math_verifier is None
