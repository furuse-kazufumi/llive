# SPDX-License-Identifier: Apache-2.0
"""Tests for BriefRunner core (LLIVE-002 Step 3)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from llive.approval.bus import ApprovalBus
from llive.brief import (
    Brief,
    BriefLedger,
    BriefRunner,
    BriefStatus,
)
from llive.fullsense.loop import FullSenseLoop
from llive.fullsense.types import ActionDecision


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_loop(**kwargs: Any) -> FullSenseLoop:
    """Construct a deterministic FullSenseLoop using template path only."""
    return FullSenseLoop(
        salience_threshold=kwargs.pop("salience_threshold", 0.0),
        curiosity_threshold=kwargs.pop("curiosity_threshold", 0.6),
        sandbox=True,
        **kwargs,
    )


def _brief(
    brief_id: str = "test-brief",
    goal: str = "Explore a novel territory",
    *,
    approval_required: bool = False,
    tools: tuple[str, ...] = (),
    ledger_dir: Path | None = None,
    constraints: tuple[str, ...] = (),
) -> Brief:
    return Brief(
        brief_id=brief_id,
        goal=goal,
        approval_required=approval_required,
        tools=tools,
        constraints=constraints,
        ledger_path=(ledger_dir / f"{brief_id}.jsonl") if ledger_dir else None,
    )


# ---------------------------------------------------------------------------
# Happy path — silent decision (no approval needed)
# ---------------------------------------------------------------------------


def test_runner_silent_decision_yields_silent_status(tmp_path: Path) -> None:
    # salience_threshold=1.0 → loop returns SILENT immediately.
    loop = _make_loop(salience_threshold=1.0)
    runner = BriefRunner(loop=loop)
    brief = _brief(goal="trivial stim", ledger_dir=tmp_path)

    result = runner.submit(brief)

    assert result.brief_id == "test-brief"
    assert result.status is BriefStatus.SILENT
    assert result.ledger_entries >= 1


def test_runner_completed_status_for_note_decision(tmp_path: Path) -> None:
    # Low salience threshold + novel content → NOTE decision (not requiring approval).
    loop = _make_loop()
    runner = BriefRunner(loop=loop)
    brief = _brief(
        goal="Discover novel patterns in the strange dataset from outer space",
        ledger_dir=tmp_path,
    )

    result = runner.submit(brief)

    # NOTE is not in approval-required set, so we end COMPLETED.
    assert result.status is BriefStatus.COMPLETED


# ---------------------------------------------------------------------------
# Ledger — records every transition
# ---------------------------------------------------------------------------


def test_runner_writes_full_ledger_trail(tmp_path: Path) -> None:
    loop = _make_loop()
    runner = BriefRunner(loop=loop)
    brief = _brief(goal="Novel discovery worth recording", ledger_dir=tmp_path)

    runner.submit(brief)

    ledger = BriefLedger(brief.ledger_path)  # type: ignore[arg-type]
    events = [r.event for r in ledger.read()]
    assert events[0] == "brief_submitted"
    assert "stimulus_built" in events
    assert "loop_completed" in events
    assert "decision" in events
    assert events[-1] == "outcome"


def test_runner_serialises_brief_payload_into_ledger(tmp_path: Path) -> None:
    loop = _make_loop()
    runner = BriefRunner(loop=loop)
    brief = _brief(
        goal="constrained brief",
        constraints=("never delete files",),
        ledger_dir=tmp_path,
    )

    runner.submit(brief)

    ledger = BriefLedger(brief.ledger_path)  # type: ignore[arg-type]
    first = next(ledger.read())
    assert first.event == "brief_submitted"
    assert first.payload["brief"]["constraints"] == ["never delete files"]


# ---------------------------------------------------------------------------
# Approval gate — Step 4 wired in
# ---------------------------------------------------------------------------


class _ForcePropose:
    """A loop fake whose ``process`` always returns a PROPOSE decision."""

    def __init__(self) -> None:
        from llive.fullsense.loop import FullSenseResult
        from llive.fullsense.types import ActionPlan, Thought

        self._FullSenseResult = FullSenseResult
        self._ActionPlan = ActionPlan
        self._Thought = Thought

    def process(self, stim: Any) -> Any:
        plan = self._ActionPlan(
            decision=ActionDecision.PROPOSE,
            rationale="forced propose",
            ego_score=0.0,
            altruism_score=1.0,
            thought=self._Thought(text="t"),
        )
        return self._FullSenseResult(stim=stim, plan=plan, stages={"forced": True})


def test_runner_awaiting_approval_without_bus(tmp_path: Path) -> None:
    runner = BriefRunner(loop=_ForcePropose())  # type: ignore[arg-type]
    brief = _brief(approval_required=True, ledger_dir=tmp_path)

    result = runner.submit(brief)

    assert result.status is BriefStatus.AWAITING_APPROVAL
    events = [r.event for r in BriefLedger(brief.ledger_path).read()]  # type: ignore[arg-type]
    assert "approval_required_no_bus" in events


def test_runner_rejected_when_bus_denies(tmp_path: Path) -> None:
    bus = ApprovalBus(policy=_DenyAll())
    runner = BriefRunner(loop=_ForcePropose(), approval_bus=bus)  # type: ignore[arg-type]
    brief = _brief(approval_required=True, ledger_dir=tmp_path)

    result = runner.submit(brief)

    assert result.status is BriefStatus.REJECTED


def test_runner_proceeds_when_bus_approves(tmp_path: Path) -> None:
    bus = ApprovalBus(policy=_ApproveAll())
    runner = BriefRunner(loop=_ForcePropose(), approval_bus=bus)  # type: ignore[arg-type]
    brief = _brief(approval_required=True, ledger_dir=tmp_path)

    result = runner.submit(brief)

    assert result.status is BriefStatus.COMPLETED


def test_runner_bypasses_approval_when_not_required(tmp_path: Path) -> None:
    runner = BriefRunner(loop=_ForcePropose())  # type: ignore[arg-type]
    brief = _brief(approval_required=False, ledger_dir=tmp_path)

    result = runner.submit(brief)

    assert result.status is BriefStatus.COMPLETED


# ---------------------------------------------------------------------------
# Tool execution — Step 5
# ---------------------------------------------------------------------------


class _PlanWithTools:
    """Loop fake whose result carries a list of tool calls in stages['tools']."""

    def __init__(self, tools: list[dict[str, Any]]) -> None:
        self._tools = tools

    def process(self, stim: Any) -> Any:
        from llive.fullsense.loop import FullSenseResult
        from llive.fullsense.types import ActionPlan, Thought

        plan = ActionPlan(
            decision=ActionDecision.NOTE,
            rationale="with tools",
            thought=Thought(text="t"),
        )
        return FullSenseResult(stim=stim, plan=plan, stages={"tools": self._tools})


def test_runner_executes_whitelisted_tool(tmp_path: Path) -> None:
    called: list[dict[str, Any]] = []

    def echo(args: dict[str, Any]) -> dict[str, Any]:
        called.append(args)
        return {"echoed": args, "artifact": "out.txt"}

    loop = _PlanWithTools([{"name": "echo", "args": {"msg": "hi"}}])
    runner = BriefRunner(loop=loop, tools={"echo": echo})  # type: ignore[arg-type]
    brief = _brief(tools=("echo",), ledger_dir=tmp_path)

    result = runner.submit(brief)

    assert called == [{"msg": "hi"}]
    assert result.artifacts == ("out.txt",)
    assert result.status is BriefStatus.COMPLETED


def test_runner_rejects_unwhitelisted_tool(tmp_path: Path) -> None:
    called: list[Any] = []

    def evil(args: dict[str, Any]) -> dict[str, Any]:
        called.append(args)
        return {}

    loop = _PlanWithTools([{"name": "evil", "args": {}}])
    # tool handler registered but NOT in brief.tools whitelist
    runner = BriefRunner(loop=loop, tools={"evil": evil})  # type: ignore[arg-type]
    brief = _brief(tools=("safe_only",), ledger_dir=tmp_path)

    runner.submit(brief)

    assert called == []  # never called
    events = [r.event for r in BriefLedger(brief.ledger_path).read()]  # type: ignore[arg-type]
    assert "tool_rejected" in events


def test_runner_records_tool_failure_without_aborting(tmp_path: Path) -> None:
    def crashy(args: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("boom")

    loop = _PlanWithTools([{"name": "crashy", "args": {}}])
    runner = BriefRunner(loop=loop, tools={"crashy": crashy})  # type: ignore[arg-type]
    brief = _brief(tools=("crashy",), ledger_dir=tmp_path)

    result = runner.submit(brief)

    events = [r.event for r in BriefLedger(brief.ledger_path).read()]  # type: ignore[arg-type]
    assert "tool_failed" in events
    assert result.status is BriefStatus.COMPLETED  # the Brief itself didn't fail


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class _CrashingLoop:
    def process(self, stim: Any) -> Any:
        raise RuntimeError("loop crashed")


def test_runner_returns_error_status_when_loop_raises(tmp_path: Path) -> None:
    runner = BriefRunner(loop=_CrashingLoop())  # type: ignore[arg-type]
    brief = _brief(ledger_dir=tmp_path)

    result = runner.submit(brief)

    assert result.status is BriefStatus.ERROR
    assert result.error and "loop crashed" in result.error


# ---------------------------------------------------------------------------
# Policy fakes
# ---------------------------------------------------------------------------


class _DenyAll:
    def evaluate(self, request: Any) -> Any:
        from llive.approval.bus import Verdict

        return Verdict.DENIED


class _ApproveAll:
    def evaluate(self, request: Any) -> Any:
        from llive.approval.bus import Verdict

        return Verdict.APPROVED
