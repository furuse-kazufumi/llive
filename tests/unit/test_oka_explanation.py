# SPDX-License-Identifier: Apache-2.0
"""OKA-06 — ExplanationAligner tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from llive.brief import BriefLedger
from llive.oka import (
    CoreEssence,
    ExplanationAligner,
    ExplanationDraft,
)


def _ce() -> CoreEssence:
    return CoreEssence(
        problem_text="保存量と対称性に関する問い",
        mystery="なぜ保存されるか",
        invariants=("総和",),
        symmetries=("回転対称",),
        essence_summary="保存量と対称性が同時に成り立つ",
    )


def test_align_with_essence_includes_invariant_and_symmetry_notes() -> None:
    draft = ExplanationAligner().align("答え: 総和は保存", essence=_ce())
    assert isinstance(draft, ExplanationDraft)
    assert "保存量" in draft.naturalness_rationale
    assert "対称性" in draft.naturalness_rationale


def test_align_with_alternatives_increases_score() -> None:
    a1 = ExplanationAligner().align("ans", essence=_ce())
    a2 = ExplanationAligner().align(
        "ans",
        essence=_ce(),
        alternative_descriptions=("方法A: 直接計算", "方法B: 帰納法"),
    )
    assert a2.resonance_score > a1.resonance_score


def test_align_without_essence_returns_default_rationale() -> None:
    draft = ExplanationAligner().align("answer")
    assert "強い見方候補がない" in draft.naturalness_rationale


def test_align_ledger_integration(tmp_path: Path) -> None:
    ledger = BriefLedger(tmp_path / "expl.jsonl")
    ExplanationAligner(ledger=ledger).align("answer", essence=_ce())
    events = [r for r in ledger.read() if r.event == "explanation_aligned"]
    assert events
    tg = ledger.trace_graph()
    assert any(e.get("kind") == "oka_explanation" for e in tg.evidence_chain)


def test_score_within_unit_interval() -> None:
    draft = ExplanationAligner().align("ans", essence=_ce(), alternative_descriptions=("a", "b", "c", "d", "e"))
    assert 0.0 <= draft.resonance_score <= 1.0
