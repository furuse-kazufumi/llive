# SPDX-License-Identifier: Apache-2.0
"""CREAT-05 — SynecticsEngine tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from llive.brief import Brief, BriefLedger
from llive.creat import Analogy, AnalogyKind, SynecticsEngine, SynecticsReport


def _b() -> Brief:
    return Brief(brief_id="sy-1", goal="エネルギー効率を最大化する")


def test_generate_returns_four_mechanism_analogies() -> None:
    report = SynecticsEngine().generate(_b())
    assert isinstance(report, SynecticsReport)
    kinds = [a.kind for a in report.analogies]
    assert set(kinds) == {AnalogyKind.DIRECT, AnalogyKind.PERSONAL, AnalogyKind.SYMBOLIC, AnalogyKind.FANTASY}


def test_each_analogy_has_description_and_id() -> None:
    report = SynecticsEngine().generate(_b())
    for a in report.analogies:
        assert isinstance(a, Analogy)
        assert a.description
        assert a.analogy_id


def test_ledger_integration(tmp_path: Path) -> None:
    ledger = BriefLedger(tmp_path / "sy.jsonl")
    SynecticsEngine(ledger=ledger).generate(_b())
    events = [r for r in ledger.read() if r.event == "synectics_analogies_generated"]
    assert events
    tg = ledger.trace_graph()
    assert any(e.get("kind") == "synectics_analogy" for e in tg.evidence_chain)


def test_custom_sources_respected() -> None:
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class _One:
        kind: AnalogyKind = AnalogyKind.DIRECT

        def propose(self, target, *, brief):
            return Analogy(
                analogy_id="x", kind=self.kind, source_domain="custom",
                description="custom analogy", bridge_terms=(),
            )

    report = SynecticsEngine(sources=(_One(),)).generate(_b())  # type: ignore[arg-type]
    assert len(report.analogies) == 1
    assert report.analogies[0].source_domain == "custom"
