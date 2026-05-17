# SPDX-License-Identifier: Apache-2.0
"""Tests for BriefGrounder (L1: TRIZ × RAD grounding)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from llive.brief import (
    Brief,
    BriefGrounder,
    BriefLedger,
    BriefRunner,
    GroundedBrief,
    GroundingConfig,
)
from llive.brief.grounding import CalcCitation, RadCitation, TrizCitation
from llive.fullsense.loop import FullSenseLoop


# ---------------------------------------------------------------------------
# Stand-in TRIZ principles + RAD index — kept in-test so we don't depend on
# the live filesystem corpus for unit tests.
# ---------------------------------------------------------------------------


class _FakePrinciple:
    def __init__(self, pid: int, name: str, description: str = "") -> None:
        self.id = pid
        self.name = name
        self.description = description
        self.examples: list[str] = []


_PRINCIPLE_INDEX: dict[int, Any] = {
    1: _FakePrinciple(1, "Segmentation"),
    3: _FakePrinciple(3, "Local Quality", "領域別 specialist"),
    15: _FakePrinciple(15, "Dynamics"),
    24: _FakePrinciple(24, "Mediator"),
    35: _FakePrinciple(35, "Parameter Change"),
}


class _FakeRadIndex:
    """Minimal stand-in that satisfies the methods rad_query touches."""

    def __init__(self, docs: list[tuple[str, Path, str]]) -> None:
        # docs: (domain, path, content)
        self._docs = docs
        for _, p, content in docs:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")

    def list_domains(self) -> list[str]:
        return sorted({d for d, _, _ in self._docs})

    def list_read_domains(self) -> list[str]:
        return self.list_domains()

    def has_domain(self, name: str) -> bool:
        return name in self.list_domains()

    def iter_documents(self, domain: str):
        for d, p, _ in self._docs:
            if d == domain:
                yield p


# ---------------------------------------------------------------------------
# TRIZ extraction
# ---------------------------------------------------------------------------


def test_grounder_finds_principles_by_trigger() -> None:
    grounder = BriefGrounder(principles=_PRINCIPLE_INDEX)
    brief = Brief(
        brief_id="b1",
        goal="trade-off between high precision and speed; consider grounding",
    )
    grounded = grounder.ground(brief)

    triggers = {c.trigger for c in grounded.triz}
    pids = {c.principle_id for c in grounded.triz}
    assert "trade-off" in triggers
    assert "high precision" in triggers or "grounding" in triggers
    assert 1 in pids  # tradeoff -> Segmentation/Contradiction
    assert 3 in pids or 24 in pids


def test_grounder_respects_max_triz_cap() -> None:
    grounder = BriefGrounder(
        principles=_PRINCIPLE_INDEX,
        config=GroundingConfig(max_triz=2),
    )
    brief = Brief(
        brief_id="b1",
        goal="tradeoff static dynamic parameter mediator local quality",
    )
    grounded = grounder.ground(brief)
    assert len(grounded.triz) <= 2


def test_grounder_returns_empty_when_no_triggers() -> None:
    grounder = BriefGrounder(principles=_PRINCIPLE_INDEX)
    brief = Brief(brief_id="b1", goal="document the README")
    grounded = grounder.ground(brief)
    assert grounded.triz == ()


# ---------------------------------------------------------------------------
# RAD lookup
# ---------------------------------------------------------------------------


def test_grounder_fetches_rad_hits(tmp_path: Path, monkeypatch) -> None:
    # Override conftest's RAD opt-out for tests that exercise the real lookup
    monkeypatch.setenv("LLIVE_DISABLE_RAD_GROUNDING", "0")
    rad_index = _FakeRadIndex(
        [
            (
                "machine_learning",
                tmp_path / "ml" / "transformers.md",
                "transformers attention dropout layer normalization",
            ),
            (
                "machine_learning",
                tmp_path / "ml" / "rnn.md",
                "recurrent neural network gating",
            ),
        ]
    )
    grounder = BriefGrounder(rad_index=rad_index, principles=_PRINCIPLE_INDEX)
    brief = Brief(brief_id="b1", goal="optimize transformers attention path")

    grounded = grounder.ground(brief)

    assert len(grounded.rad) >= 1
    top = grounded.rad[0]
    assert "transformers.md" in top.doc_path
    assert "transformers" in top.matched_terms


def test_grounder_no_rad_when_no_keywords(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LLIVE_DISABLE_RAD_GROUNDING", "0")
    rad_index = _FakeRadIndex(
        [("dom", tmp_path / "x.md", "anything")]
    )
    grounder = BriefGrounder(rad_index=rad_index, principles=_PRINCIPLE_INDEX)
    brief = Brief(brief_id="b1", goal="a a")  # all stripped by stopwords/length
    grounded = grounder.ground(brief)
    assert grounded.rad == ()


def test_grounder_caps_rad_results(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LLIVE_DISABLE_RAD_GROUNDING", "0")
    docs = [
        ("d", tmp_path / f"doc{i}.md", f"transformers attention example {i}")
        for i in range(10)
    ]
    rad_index = _FakeRadIndex(docs)
    grounder = BriefGrounder(
        rad_index=rad_index,
        principles=_PRINCIPLE_INDEX,
        config=GroundingConfig(max_rad=2),
    )
    grounded = grounder.ground(Brief(brief_id="b1", goal="transformers attention"))
    assert len(grounded.rad) <= 2


# ---------------------------------------------------------------------------
# augmented_goal
# ---------------------------------------------------------------------------


def test_augmented_goal_appends_blocks() -> None:
    grounder = BriefGrounder(principles=_PRINCIPLE_INDEX)
    brief = Brief(
        brief_id="b1",
        goal="resolve a tradeoff between size and accuracy",
    )
    grounded = grounder.ground(brief)
    assert "[TRIZ principles considered]" in grounded.augmented_goal
    assert grounded.augmented_goal.startswith("resolve a tradeoff")


def test_augmented_goal_unchanged_when_no_grounding() -> None:
    grounder = BriefGrounder(principles=_PRINCIPLE_INDEX)
    brief = Brief(brief_id="b1", goal="write the README")
    grounded = grounder.ground(brief)
    assert grounded.augmented_goal == "write the README"


# ---------------------------------------------------------------------------
# BriefRunner integration — ledger captures citations
# ---------------------------------------------------------------------------


def test_runner_records_grounding_in_ledger(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LLIVE_BRIEF_LEDGER_DIR", str(tmp_path / "ledgers"))
    monkeypatch.setenv("LLIVE_DISABLE_RAD_GROUNDING", "0")
    rad_index = _FakeRadIndex(
        [
            (
                "ml",
                tmp_path / "ml" / "transformer.md",
                "transformer attention mechanism dropout",
            )
        ]
    )
    grounder = BriefGrounder(rad_index=rad_index, principles=_PRINCIPLE_INDEX)
    runner = BriefRunner(
        loop=FullSenseLoop(sandbox=True, salience_threshold=0.0),
        grounder=grounder,
    )
    brief = Brief(
        brief_id="grounded-1",
        goal="trade-off between transformer attention speed and precision",
        approval_required=False,
        ledger_path=tmp_path / "grounded-1.jsonl",
    )

    runner.submit(brief)

    records = list(BriefLedger(brief.ledger_path).read())  # type: ignore[arg-type]
    events = [r.event for r in records]
    assert "grounding_applied" in events
    grounding = next(r for r in records if r.event == "grounding_applied")
    assert grounding.payload["triz"]  # at least one principle cited
    assert any(t["trigger"] == "trade-off" for t in grounding.payload["triz"])
    # RAD citation traceable to a stable doc_path
    assert grounding.payload["rad"]
    assert "transformer.md" in grounding.payload["rad"][0]["doc_path"]


def test_runner_without_grounder_omits_event(tmp_path: Path) -> None:
    runner = BriefRunner(loop=FullSenseLoop(sandbox=True))
    brief = Brief(
        brief_id="ungrounded-1",
        goal="anything",
        approval_required=False,
        ledger_path=tmp_path / "u1.jsonl",
    )
    runner.submit(brief)
    events = [r.event for r in BriefLedger(brief.ledger_path).read()]  # type: ignore[arg-type]
    assert "grounding_applied" not in events


def test_brief_object_remains_unchanged_after_grounding(tmp_path: Path) -> None:
    """Precision invariant: the original Brief must be byte-identical after a
    grounded run, so callers can re-submit it or compare it across runs."""
    grounder = BriefGrounder(principles=_PRINCIPLE_INDEX)
    brief = Brief(
        brief_id="b1",
        goal="trade-off between speed and precision",
        approval_required=False,
        ledger_path=tmp_path / "x.jsonl",
    )
    original_goal = brief.goal
    runner = BriefRunner(
        loop=FullSenseLoop(sandbox=True, salience_threshold=0.0),
        grounder=grounder,
    )
    runner.submit(brief)
    assert brief.goal == original_goal


# ---------------------------------------------------------------------------
# Dataclass surface — citations are hashable + frozen
# ---------------------------------------------------------------------------


def test_citation_dataclasses_are_frozen() -> None:
    t = TrizCitation(principle_id=1, name="x")
    r = RadCitation(domain="d", doc_path="p", score=1.0, excerpt="e")
    with pytest.raises(Exception):
        t.principle_id = 2  # type: ignore[misc]
    with pytest.raises(Exception):
        r.score = 99.0  # type: ignore[misc]


def test_grounded_brief_carries_both_axes() -> None:
    gb = GroundedBrief(
        augmented_goal="x",
        triz=(TrizCitation(principle_id=1, name="x"),),
        rad=(RadCitation(domain="d", doc_path="p", score=1.0, excerpt="e"),),
    )
    assert gb.triz[0].principle_id == 1
    assert gb.rad[0].domain == "d"


# ---------------------------------------------------------------------------
# MATH-08 — Inlined calculation grounding
# ---------------------------------------------------------------------------


def test_grounder_inlines_calculations() -> None:
    grounder = BriefGrounder(principles=_PRINCIPLE_INDEX)
    brief = Brief(
        brief_id="b1",
        goal="confirm that (2.5 * 7.8) / 0.3 fits the budget",
    )
    grounded = grounder.ground(brief)
    assert len(grounded.calc) == 1
    cc = grounded.calc[0]
    assert cc.error is None
    assert cc.value == pytest.approx(65.0)
    assert cc.operation_count >= 2
    # Augmented goal includes the inlined block so the LLM sees the proof.
    assert "[Inlined calculations (MATH-08)]" in grounded.augmented_goal
    assert "= 65.0" in grounded.augmented_goal


def test_grounder_calc_handles_error_safely() -> None:
    grounder = BriefGrounder(principles=_PRINCIPLE_INDEX)
    brief = Brief(brief_id="b1", goal="check 10 / 0 in the math")
    grounded = grounder.ground(brief)
    # extract_expressions finds "10 / 0"; SafeCalculator rejects it
    assert len(grounded.calc) == 1
    cc = grounded.calc[0]
    assert cc.error is not None
    assert "zero division" in cc.error
    assert "ERROR" in grounded.augmented_goal


def test_grounder_respects_max_calc_cap() -> None:
    grounder = BriefGrounder(
        principles=_PRINCIPLE_INDEX,
        config=GroundingConfig(max_calc=2),
    )
    brief = Brief(
        brief_id="b1",
        goal="numbers: 1 + 1 and 2 * 3 and 4 - 1 and 5 / 1 and 6 + 6",
    )
    grounded = grounder.ground(brief)
    assert len(grounded.calc) <= 2


def test_grounder_no_calc_when_no_expressions() -> None:
    grounder = BriefGrounder(principles=_PRINCIPLE_INDEX)
    brief = Brief(brief_id="b1", goal="write the architecture overview")
    grounded = grounder.ground(brief)
    assert grounded.calc == ()


def test_calc_citation_is_frozen() -> None:
    c = CalcCitation(expression="1+1", value=2.0)
    with pytest.raises(Exception):
        c.value = 99.0  # type: ignore[misc]


def test_runner_records_calc_in_ledger(tmp_path: Path) -> None:
    grounder = BriefGrounder(principles=_PRINCIPLE_INDEX)
    runner = BriefRunner(
        loop=FullSenseLoop(sandbox=True, salience_threshold=0.0),
        grounder=grounder,
    )
    brief = Brief(
        brief_id="calc-1",
        goal="verify (3 + 4) * 2 produces the expected throughput",
        approval_required=False,
        ledger_path=tmp_path / "calc-1.jsonl",
    )
    runner.submit(brief)

    records = list(BriefLedger(brief.ledger_path).read())  # type: ignore[arg-type]
    grounding = next(r for r in records if r.event == "grounding_applied")
    calc_payload = grounding.payload["calc"]
    assert len(calc_payload) == 1
    assert calc_payload[0]["value"] == pytest.approx(14.0)
    assert calc_payload[0]["error"] is None
    assert calc_payload[0]["operation_count"] >= 2
