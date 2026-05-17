# SPDX-License-Identifier: Apache-2.0
"""MATH-02 — Traceability hooks (ledger auto-record + COG-03 trace_graph)."""

from __future__ import annotations

from pathlib import Path

from llive.brief import BriefLedger
from llive.math import MathVerifier


def test_verifier_appends_math_verified_event_to_ledger(tmp_path: Path) -> None:
    ledger = BriefLedger(tmp_path / "math.jsonl")
    v = MathVerifier(source_id="brief:trace-1", ledger=ledger)

    v.check_equivalence("(x + 1)**2", "x**2 + 2*x + 1")
    v.check_implication(["x > 5"], "x > 3")
    v.check_satisfiable(["x > 0", "x < 10"])

    events = [r for r in ledger.read() if r.event == "math_verified"]
    assert len(events) == 3

    kinds = [e.payload["kind"] for e in events]
    assert kinds == ["equivalence", "implication", "satisfiability"]
    for e in events:
        assert e.payload["source_id"] == "brief:trace-1"
        assert "solver" in e.payload
        assert "verdict" in e.payload


def test_verifier_without_ledger_is_silent(tmp_path: Path) -> None:
    v = MathVerifier()
    r = v.check_equivalence("x", "x")
    assert r.verdict == "equivalent"
    # No ledger attached — nothing to assert, just confirm no AttributeError raised.


def test_trace_graph_evidence_chain_contains_math_kind(tmp_path: Path) -> None:
    """COG-03 trace_graph が math_verified を evidence_chain にまとめることを確認。"""
    ledger = BriefLedger(tmp_path / "trace.jsonl")
    v = MathVerifier(source_id="brief:e2e", ledger=ledger)
    v.check_equivalence("a + 0", "a")
    v.check_implication(["x > 0"], "x > -1")

    tg = ledger.trace_graph()
    math_entries = [e for e in tg.evidence_chain if e.get("kind") == "math"]
    assert len(math_entries) == 2
    # Each entry should retain the verdict + solver so auditors can read it directly
    for e in math_entries:
        assert "verdict" in e
        assert "solver" in e
        assert "source_id" in e


def test_trace_graph_distinguishes_math_from_triz_and_rad(tmp_path: Path) -> None:
    """grounding_applied (triz/rad) と math_verified の kind が混じらないこと。"""
    ledger = BriefLedger(tmp_path / "mix.jsonl")
    ledger.append(
        "grounding_applied",
        {
            "triz": [{"principle_id": 1, "name": "Segmentation", "trigger": "vs"}],
            "rad": [],
            "augmented_goal_chars": 100,
        },
    )
    v = MathVerifier(ledger=ledger)
    v.check_equivalence("y", "y")

    tg = ledger.trace_graph()
    kinds = {e["kind"] for e in tg.evidence_chain}
    assert {"triz", "math"} <= kinds
