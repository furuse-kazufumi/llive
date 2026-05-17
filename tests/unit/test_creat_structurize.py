# SPDX-License-Identifier: Apache-2.0
"""CREAT-03 — StructureSynthesizer tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from llive.brief import Brief, BriefLedger, RoleBasedMultiTrack
from llive.creat import (
    KJExtractor,
    MindMapBuilder,
    RequirementDraft,
    StructureSynthesizer,
)
from llive.fullsense.types import ActionDecision, ActionPlan, Thought


def _b() -> Brief:
    return Brief(
        brief_id="syn-1",
        goal="保存量と対称性を活かす設計",
        constraints=("p99 < 100ms",),
        success_criteria=("data loss 0 件",),
    )


def test_synthesize_with_all_inputs(tmp_path: Path) -> None:
    brief = _b()
    kj = KJExtractor(max_ideas=5).extract(brief)
    mm = MindMapBuilder(max_depth=2).build(brief)
    plan = ActionPlan(
        decision=ActionDecision.PROPOSE,
        rationale="proposal rationale",
        thought=Thought(text="t", confidence=0.7, triz_principles=[1]),
    )
    persp = RoleBasedMultiTrack().observe(brief, ActionDecision.PROPOSE, plan)
    draft = StructureSynthesizer().synthesize(
        brief,
        kj_board=kj,
        mindmap=mm,
        perspectives=persp,
        triz_principle_names=("1: Segmentation",),
    )
    assert isinstance(draft, RequirementDraft)
    cat_names = [c.name for c in draft.categories]
    assert "Constraints (from Brief)" in cat_names
    assert "Success criteria (from Brief)" in cat_names
    assert "MindMap top branches" in cat_names
    assert draft.triz_principles == ("1: Segmentation",)


def test_synthesize_minimal_inputs() -> None:
    draft = StructureSynthesizer().synthesize(_b())
    # Brief 自体の constraints / success_criteria だけは抽出される
    cat_names = [c.name for c in draft.categories]
    assert "Constraints (from Brief)" in cat_names


def test_to_markdown_renders_sections() -> None:
    brief = _b()
    kj = KJExtractor(max_ideas=4).extract(brief)
    mm = MindMapBuilder(max_depth=2).build(brief)
    draft = StructureSynthesizer().synthesize(brief, kj_board=kj, mindmap=mm)
    md = draft.to_markdown()
    assert "# Requirement draft" in md
    assert "## Themes" in md
    assert "## Constraints (from Brief)" in md


def test_ledger_integration(tmp_path: Path) -> None:
    ledger = BriefLedger(tmp_path / "syn.jsonl")
    StructureSynthesizer(ledger=ledger).synthesize(_b())
    events = [r for r in ledger.read() if r.event == "requirement_draft_generated"]
    assert events
    tg = ledger.trace_graph()
    assert any(d["event"] == "requirement_draft_generated" for d in tg.decision_chain)
