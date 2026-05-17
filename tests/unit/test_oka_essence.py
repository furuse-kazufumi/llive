# SPDX-License-Identifier: Apache-2.0
"""OKA-01 / OKA-02 — CoreEssenceExtractor tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from llive.brief import BriefLedger
from llive.oka import CoreEssence, CoreEssenceExtractor


def test_extract_returns_core_essence_with_required_fields() -> None:
    ext = CoreEssenceExtractor(source_id="brief:e1")
    text = (
        "なぜ熱は高温から低温へ流れるのか。"
        "総和は保存されるが、エントロピーは増大する。"
        "反転対称性が破れている。"
    )
    ce = ext.extract(text)
    assert isinstance(ce, CoreEssence)
    assert ce.source_id == "brief:e1"
    assert "なぜ" in ce.mystery or "熱" in ce.mystery
    assert ce.invariants  # 保存量候補が拾えていること
    assert ce.symmetries  # 対称性候補が拾えていること
    assert ce.essence_summary  # 核心メモが組み立てられている


def test_extract_falls_back_when_no_triggers_match() -> None:
    ext = CoreEssenceExtractor()
    ce = ext.extract("abc def ghi.")
    assert ce.invariants == ()
    assert ce.symmetries == ()
    assert "fallback" in ce.essence_summary or "abc" in ce.essence_summary


def test_extract_records_ledger_event(tmp_path: Path) -> None:
    ledger = BriefLedger(tmp_path / "oka1.jsonl")
    ext = CoreEssenceExtractor(ledger=ledger)
    ext.extract("対称性が破れる現象を考える。なぜそうなるのか。")
    events = [r for r in ledger.read() if r.event == "oka_essence_extracted"]
    assert len(events) == 1
    assert "essence_summary" in events[0].payload


def test_extract_evidence_chain_kind(tmp_path: Path) -> None:
    ledger = BriefLedger(tmp_path / "oka1tg.jsonl")
    ext = CoreEssenceExtractor(ledger=ledger)
    ext.extract("不思議な保存則の性質")
    tg = ledger.trace_graph()
    kinds = {e.get("kind") for e in tg.evidence_chain}
    assert "oka_essence" in kinds


def test_bind_ledger_after_construction(tmp_path: Path) -> None:
    ext = CoreEssenceExtractor()  # no ledger initially
    ext.extract("foo")  # nothing happens
    ledger = BriefLedger(tmp_path / "bind.jsonl")
    ext.bind_ledger(ledger)
    ext.extract("対称性の問題")
    events = [r for r in ledger.read() if r.event == "oka_essence_extracted"]
    assert len(events) == 1
