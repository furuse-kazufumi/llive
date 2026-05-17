# SPDX-License-Identifier: Apache-2.0
"""BriefRunner ↔ OKA (essence / notebook / orchestrator) integration tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from llive.brief import Brief, BriefLedger, BriefRunner, BriefStatus
from llive.fullsense.loop import FullSenseLoop, FullSenseResult
from llive.fullsense.types import ActionDecision, ActionPlan, Stimulus, Thought
from llive.oka import (
    CoreEssenceExtractor,
    ReflectiveNotebook,
    StrategyFamily,
    StrategyOrchestrator,
)


def test_essence_auto_extracted_on_submit(tmp_path: Path) -> None:
    """essence_extractor が attach されれば毎 Brief で essence が自動抽出される."""
    extractor = CoreEssenceExtractor()
    runner = BriefRunner(
        loop=FullSenseLoop(sandbox=True, salience_threshold=0.0),
        essence_extractor=extractor,
    )
    brief = Brief(
        brief_id="oka-runner-1",
        goal="なぜ熱は高温から低温へ流れるのか。総和は保存される。",
        approval_required=False,
        ledger_path=tmp_path / "1.jsonl",
    )
    result = runner.submit(brief)

    assert result.essence is not None
    assert "essence_summary" in result.essence
    assert result.essence["source_id"] == "oka-runner-1"

    events = [r for r in BriefLedger(brief.ledger_path).read() if r.event == "oka_essence_extracted"]  # type: ignore[arg-type]
    assert len(events) == 1
    # outcome event also mirrors the essence for replay
    outcome = next(r for r in BriefLedger(brief.ledger_path).read() if r.event == "outcome")  # type: ignore[arg-type]
    assert outcome.payload["essence"] is not None


def test_essence_extractor_ledger_rebound_per_brief(tmp_path: Path) -> None:
    """1 つの extractor を 2 Brief で使い回しても各 ledger に正しく書かれる."""
    extractor = CoreEssenceExtractor()
    runner = BriefRunner(
        loop=FullSenseLoop(sandbox=True, salience_threshold=0.0),
        essence_extractor=extractor,
    )
    a = Brief(brief_id="oka-a", goal="対称性を破る現象", approval_required=False, ledger_path=tmp_path / "a.jsonl")
    b = Brief(brief_id="oka-b", goal="保存量はなぜ存在するか", approval_required=False, ledger_path=tmp_path / "b.jsonl")
    runner.submit(a)
    runner.submit(b)
    a_evt = [r for r in BriefLedger(a.ledger_path).read() if r.event == "oka_essence_extracted"]  # type: ignore[arg-type]
    b_evt = [r for r in BriefLedger(b.ledger_path).read() if r.event == "oka_essence_extracted"]  # type: ignore[arg-type]
    assert len(a_evt) == 1
    assert len(b_evt) == 1


class _RaisingLoop:
    def process(self, stim: Stimulus) -> FullSenseResult:
        raise RuntimeError("intentional failure for notebook test")


def test_notebook_auto_records_failed_attempt_on_loop_error(tmp_path: Path) -> None:
    notebook = ReflectiveNotebook(tmp_path / "nb.jsonl")
    runner = BriefRunner(
        loop=_RaisingLoop(),  # type: ignore[arg-type]
        notebook=notebook,
    )
    brief = Brief(
        brief_id="oka-fail-1",
        goal="this will fail in loop",
        approval_required=False,
        ledger_path=tmp_path / "fail.jsonl",
    )
    result = runner.submit(brief)
    assert result.status is BriefStatus.ERROR

    notes = list(notebook.read())
    assert len(notes) == 1
    assert notes[0].kind == "failed_attempt"
    assert "intentional failure" in notes[0].body
    assert "loop_error" in notes[0].tags
    # the notebook event also lands in the brief's ledger
    led_evt = [r for r in BriefLedger(brief.ledger_path).read() if r.event == "oka_notebook_appended"]  # type: ignore[arg-type]
    assert led_evt


def test_strategy_orchestrator_ledger_bound_at_submit(tmp_path: Path) -> None:
    """orchestrator を attach すると submit 時に ledger が bind される."""
    orch = StrategyOrchestrator()
    orch.register(StrategyFamily(name="symbolic"))
    orch.register(StrategyFamily(name="geometric"))
    orch.activate("symbolic")

    runner = BriefRunner(
        loop=FullSenseLoop(sandbox=True, salience_threshold=0.0),
        strategy_orchestrator=orch,
    )
    brief = Brief(
        brief_id="oka-orch-1",
        goal="strategy bind test",
        approval_required=False,
        ledger_path=tmp_path / "o.jsonl",
    )
    runner.submit(brief)

    # After submit, switching the strategy should land in this brief's ledger
    for _ in range(5):
        orch.push_progress(0.05)
    orch.switch_to("geometric", reason="stalled")
    events = [r for r in BriefLedger(brief.ledger_path).read() if r.event == "oka_strategy_switched"]  # type: ignore[arg-type]
    assert events
    assert events[-1].payload["to_strategy"] == "geometric"


def test_runner_without_oka_components_unchanged(tmp_path: Path) -> None:
    runner = BriefRunner(loop=FullSenseLoop(sandbox=True, salience_threshold=0.0))
    brief = Brief(
        brief_id="oka-none",
        goal="no OKA wired",
        approval_required=False,
        ledger_path=tmp_path / "n.jsonl",
    )
    result = runner.submit(brief)
    assert result.essence is None
    assert all(r.event != "oka_essence_extracted" for r in BriefLedger(brief.ledger_path).read())  # type: ignore[arg-type]
