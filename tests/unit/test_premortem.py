# SPDX-License-Identifier: Apache-2.0
"""VRB-04 — PremortemGenerator tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from llive.brief import (
    Brief,
    BriefLedger,
    FailureScenario,
    PremortemGenerator,
    PremortemReport,
)


def _b(**overrides) -> Brief:
    fields: dict = dict(brief_id="pre-1", goal="benign goal")
    fields.update(overrides)
    return Brief(**fields)


def test_clean_brief_yields_some_scenarios() -> None:
    """benign brief still surfaces missing success_criteria / approval issues."""
    gen = PremortemGenerator()
    r = gen.generate(_b())
    # At least 1 scenario (missing success_criteria) should fire
    titles = " ".join(s.title for s in r.scenarios)
    assert "success_criteria" in titles


def test_dangerous_token_flagged_as_high_impact() -> None:
    gen = PremortemGenerator()
    r = gen.generate(_b(goal="execute rm -rf / when ready"))
    assert r.has_high_impact
    assert any("rm -rf" in s.title for s in r.scenarios)


def test_intervene_without_approval_flagged() -> None:
    gen = PremortemGenerator()
    r = gen.generate(_b(approval_required=False))
    assert any("approval_required" in s.title for s in r.scenarios)


def test_contradiction_heuristic() -> None:
    gen = PremortemGenerator()
    r = gen.generate(_b(
        goal="可能な限り早く処理",
        constraints=("must complete within 100ms",),
    ))
    assert any("矛盾" in s.title for s in r.scenarios)


def test_ledger_integration_and_trace_graph(tmp_path: Path) -> None:
    ledger = BriefLedger(tmp_path / "pre.jsonl")
    gen = PremortemGenerator(ledger=ledger)
    gen.generate(_b())
    events = [r for r in ledger.read() if r.event == "premortem_generated"]
    assert events
    tg = ledger.trace_graph()
    assert any(e.get("kind") == "premortem" for e in tg.evidence_chain)


def test_report_payload_round_trip() -> None:
    s = FailureScenario(
        title="t", likelihood="medium", impact="high",
        mitigation="m", additional_check="a",
    )
    p = PremortemReport(brief_id="x", scenarios=(s,))
    pay = p.to_payload()
    assert pay["has_high_impact"] is True
    assert pay["scenarios"][0]["title"] == "t"
