# SPDX-License-Identifier: Apache-2.0
"""Ledger replay consistency + 13-event-type trace_graph coverage."""

from __future__ import annotations

from pathlib import Path

import pytest

from llive.brief import BriefLedger


# All 13 event types currently produced by llive components.
_ALL_EVENTS: tuple[str, ...] = (
    "brief_submitted",
    "stimulus_built",
    "loop_completed",
    "decision",
    "governance_scored",
    "approval_requested",
    "approval_resolved",
    "tool_invoked",
    "outcome",
    "perspectives_observed",
    "grounding_applied",
    "math_verified",
    "oka_essence_extracted",
    "oka_notebook_appended",
    "oka_strategy_switched",
    "explanation_aligned",
    "insight_score_recorded",
    "kj_board_constructed",
    "mindmap_constructed",
    "synectics_analogies_generated",
    "requirement_draft_generated",
    "premortem_generated",
    "lint_findings_recorded",
    "eval_spec_evaluated",
)


def _seed_one_of_each(ledger: BriefLedger) -> None:
    """Write one event of each type — payload shape doesn't have to be perfect,
    only that ledger.read() + trace_graph() classify them without crashing."""
    ledger.append("brief_submitted", {"brief": {"brief_id": "x"}})
    ledger.append("stimulus_built", {"content_chars": 10})
    ledger.append("loop_completed", {"stages": {}})
    ledger.append("decision", {"decision": "note", "rationale": "r"})
    ledger.append("governance_scored", {
        "usefulness": 0.5, "feasibility": 0.5, "safety": 0.9,
        "traceability": 0.5, "weighted_total": 0.6, "recommend_block": False,
        "rationales": {},
    })
    ledger.append("approval_requested", {"request_id": "a", "action": "x"})
    ledger.append("approval_resolved", {"request_id": "a", "verdict": "approved"})
    ledger.append("tool_invoked", {"name": "echo", "args": {}, "output": {}})
    ledger.append("outcome", {"brief_id": "x", "status": "completed"})
    ledger.append("perspectives_observed", {"notes": [], "support_score": 0.5, "risk_score": 0.2, "divergence": 0.3, "critical_concerns": [], "consensus_recommendation": "proceed"})
    ledger.append("grounding_applied", {
        "triz": [{"principle_id": 1, "name": "Segmentation", "trigger": "vs"}],
        "rad": [{"domain": "x", "doc_path": "y", "score": 1.0, "matched_terms": []}],
        "calc": [{"expression": "1+1", "value": 2.0}],
        "augmented_goal_chars": 100,
    })
    ledger.append("math_verified", {
        "kind": "equivalence", "verdict": "equivalent",
        "solver": "sympy", "inputs": ["x", "x"],
        "rationale": "r", "source_id": "s", "counterexample": {},
        "elapsed_s": 0.0, "error": None,
    })
    ledger.append("oka_essence_extracted", {
        "problem_text": "p", "mystery": "m", "invariants": [],
        "symmetries": [], "essence_summary": "s", "source_id": "x",
    })
    ledger.append("oka_notebook_appended", {
        "note_id": "n", "brief_id": "x", "kind": "insight",
        "body": "b", "tags": [], "created_at": 0.0,
    })
    ledger.append("oka_strategy_switched", {
        "from_strategy": "a", "to_strategy": "b", "reason": "r",
        "progress_history": [], "timestamp": 0.0,
    })
    ledger.append("explanation_aligned", {
        "answer": "a", "naturalness_rationale": "n",
        "comparison_note": "c", "resonance_score": 0.5,
    })
    ledger.append("insight_score_recorded", {
        "coverage": 0.5, "succinctness": 0.5, "alignment": 0.5,
        "insight_score": 0.5, "diagnostics": {},
    })
    ledger.append("kj_board_constructed", {
        "brief_id": "x", "nodes": [{"node_id": "n1", "text": "t", "tags": [], "source": "d"}],
        "clusters": [],
    })
    ledger.append("mindmap_constructed", {
        "brief_id": "x", "root_id": "r", "max_depth": 1,
        "nodes": [{"node_id": "r", "label": "L", "parent_id": None, "depth": 0, "source": "d"}],
    })
    ledger.append("synectics_analogies_generated", {
        "brief_id": "x",
        "analogies": [{"analogy_id": "a1", "kind": "direct", "source_domain": "x", "description": "d", "bridge_terms": []}],
    })
    ledger.append("requirement_draft_generated", {
        "brief_id": "x", "themes": [], "categories": [],
        "risk_notes": [], "triz_principles": [],
    })
    ledger.append("premortem_generated", {
        "brief_id": "x", "scenarios": [], "has_high_impact": False,
    })
    ledger.append("lint_findings_recorded", {
        "brief_id": "x", "findings": [], "summary": {},
    })
    ledger.append("eval_spec_evaluated", {
        "brief_id": "x", "all_passed": True, "should_stop": False,
        "metric_results": [], "triggered_stop_conditions": [],
    })


def test_replay_consistency_two_reads_match(tmp_path: Path) -> None:
    """Same ledger.jsonl → identical trace_graph on two reads (SIL axis)."""
    ledger = BriefLedger(tmp_path / "rep.jsonl")
    _seed_one_of_each(ledger)
    tg1 = ledger.trace_graph()
    tg2 = ledger.trace_graph()
    assert tg1 == tg2


def test_all_known_events_classified_without_loss(tmp_path: Path) -> None:
    """Every emitted event should land in exactly one of evidence/tool/decision."""
    ledger = BriefLedger(tmp_path / "all.jsonl")
    _seed_one_of_each(ledger)
    tg = ledger.trace_graph()
    classified_events: set[str] = set()
    for e in tg.evidence_chain:
        # evidence entries carry the original event indirectly — re-derive from kind
        kind = e.get("kind", "")
        # grounding_applied fans out into triz/rad/calc — mark all three
        if kind == "triz":
            classified_events.add("grounding_applied")
        elif kind == "rad":
            classified_events.add("grounding_applied")
        elif kind == "calc":
            classified_events.add("grounding_applied")
        elif kind == "math":
            classified_events.add("math_verified")
        elif kind == "oka_essence":
            classified_events.add("oka_essence_extracted")
        elif kind == "oka_note":
            classified_events.add("oka_notebook_appended")
        elif kind == "oka_explanation":
            classified_events.add("explanation_aligned")
        elif kind == "kj_node":
            classified_events.add("kj_board_constructed")
        elif kind == "mindmap_node":
            classified_events.add("mindmap_constructed")
        elif kind == "synectics_analogy":
            classified_events.add("synectics_analogies_generated")
        elif kind == "premortem":
            classified_events.add("premortem_generated")
        elif kind == "lint":
            classified_events.add("lint_findings_recorded")
    for d in tg.decision_chain:
        ev = d.get("event", "")
        if ev:
            classified_events.add(ev)
    for t in tg.tool_chain:
        ev = t.get("event", "")
        if ev:
            classified_events.add(ev)

    # Events that should now be reachable through the trace graph
    expected = {
        "decision", "approval_requested", "approval_resolved",
        "governance_scored", "outcome",
        "tool_invoked", "grounding_applied", "math_verified",
        "oka_essence_extracted", "oka_notebook_appended",
        "oka_strategy_switched", "explanation_aligned", "insight_score_recorded",
        "kj_board_constructed", "mindmap_constructed",
        "synectics_analogies_generated", "requirement_draft_generated",
        "premortem_generated", "lint_findings_recorded", "eval_spec_evaluated",
    }
    missing = expected - classified_events
    assert not missing, f"events not classified: {missing}"


def test_evidence_kinds_complete(tmp_path: Path) -> None:
    """Every documented evidence kind is observable in the chain."""
    ledger = BriefLedger(tmp_path / "kinds.jsonl")
    _seed_one_of_each(ledger)
    tg = ledger.trace_graph()
    kinds = {e.get("kind") for e in tg.evidence_chain}
    expected = {
        "triz", "rad", "calc", "math",
        "oka_essence", "oka_note", "oka_explanation",
        "kj_node", "mindmap_node", "synectics_analogy",
        "premortem", "lint",
    }
    missing = expected - kinds
    assert not missing, f"missing evidence kinds: {missing}"


def test_decision_chain_includes_outcomes_and_judgements(tmp_path: Path) -> None:
    ledger = BriefLedger(tmp_path / "dec.jsonl")
    _seed_one_of_each(ledger)
    tg = ledger.trace_graph()
    events = {d["event"] for d in tg.decision_chain}
    expected = {
        "decision", "approval_requested", "approval_resolved",
        "governance_scored", "outcome",
        "oka_strategy_switched", "insight_score_recorded",
        "requirement_draft_generated", "eval_spec_evaluated",
    }
    missing = expected - events
    assert not missing, f"missing decision events: {missing}"
