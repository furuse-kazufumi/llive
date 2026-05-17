# SPDX-License-Identifier: Apache-2.0
"""OKA-04 — ReflectiveNotebook tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from llive.brief import BriefLedger
from llive.oka import ReflectiveNote, ReflectiveNotebook


def test_append_and_read_roundtrip(tmp_path: Path) -> None:
    nb = ReflectiveNotebook(tmp_path / "notes.jsonl")
    nb.append(brief_id="b1", kind="insight", body="保存量に着目すると見通しがよい")
    nb.append(brief_id="b1", kind="failed_attempt", body="幾何的アプローチで詰まった")
    notes = list(nb.read())
    assert len(notes) == 2
    assert notes[0].kind == "insight"
    assert notes[1].kind == "failed_attempt"


def test_note_rejects_invalid_kind(tmp_path: Path) -> None:
    nb = ReflectiveNotebook(tmp_path / "n.jsonl")
    with pytest.raises(ValueError):
        nb.append(brief_id="b1", kind="wat", body="x")


def test_note_rejects_empty_body(tmp_path: Path) -> None:
    nb = ReflectiveNotebook(tmp_path / "n.jsonl")
    with pytest.raises(ValueError):
        nb.append(brief_id="b1", kind="insight", body="  ")


def test_find_by_kind_and_tag(tmp_path: Path) -> None:
    nb = ReflectiveNotebook(tmp_path / "n.jsonl")
    nb.append(brief_id="b1", kind="insight", body="A", tags=("symmetry",))
    nb.append(brief_id="b1", kind="insight", body="B", tags=("invariant",))
    nb.append(brief_id="b2", kind="failed_attempt", body="C", tags=("symmetry",))
    sym = nb.find(tag="symmetry")
    insights = nb.find(kind="insight")
    assert len(sym) == 2
    assert len(insights) == 2


def test_related_to_returns_keyword_matches(tmp_path: Path) -> None:
    nb = ReflectiveNotebook(tmp_path / "n.jsonl")
    nb.append(brief_id="b1", kind="insight", body="保存量と対称性を同時に追う")
    nb.append(brief_id="b1", kind="insight", body="まったく無関係な内容")
    hits = nb.related_to("対称性 保存量")
    assert hits
    assert "対称性" in hits[0].body or "保存量" in hits[0].body


def test_ledger_integration(tmp_path: Path) -> None:
    ledger = BriefLedger(tmp_path / "led.jsonl")
    nb = ReflectiveNotebook(tmp_path / "n.jsonl", ledger=ledger)
    nb.append(brief_id="b1", kind="reframing", body="図形で見直す")
    events = [r for r in ledger.read() if r.event == "oka_notebook_appended"]
    assert len(events) == 1
    tg = ledger.trace_graph()
    assert any(e.get("kind") == "oka_note" for e in tg.evidence_chain)


def test_bind_ledger_after_construction(tmp_path: Path) -> None:
    nb = ReflectiveNotebook(tmp_path / "n.jsonl")
    nb.append(brief_id="b0", kind="insight", body="ledger 未接続でも書ける")
    ledger = BriefLedger(tmp_path / "led2.jsonl")
    nb.bind_ledger(ledger)
    nb.append(brief_id="b1", kind="insight", body="now logged")
    assert any(r.event == "oka_notebook_appended" for r in ledger.read())
