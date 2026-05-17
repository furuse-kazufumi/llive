# SPDX-License-Identifier: Apache-2.0
"""CREAT-01 — KJ-method extractor tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from llive.brief import Brief, BriefLedger
from llive.creat import (
    AffinityCluster,
    IdeaGenerator,
    KJBoard,
    KJExtractor,
    KJNode,
)


def _b(**overrides) -> Brief:
    fields: dict = dict(
        brief_id="kj-1",
        goal="保存量と対称性を見出す",
        constraints=("時間制約あり",),
    )
    fields.update(overrides)
    return Brief(**fields)


def test_extract_returns_board_with_nodes() -> None:
    board = KJExtractor(max_ideas=5).extract(_b())
    assert isinstance(board, KJBoard)
    assert len(board.nodes) == 5
    for n in board.nodes:
        assert isinstance(n, KJNode)
        assert n.text
        assert n.node_id.startswith("kj-kj-1-")


def test_extract_clusters_returned() -> None:
    board = KJExtractor(max_ideas=4, cluster_threshold=0.1).extract(_b())
    assert board.clusters
    for c in board.clusters:
        assert isinstance(c, AffinityCluster)
        assert c.node_ids


def test_higher_threshold_yields_more_singleton_clusters() -> None:
    a = KJExtractor(max_ideas=6, cluster_threshold=0.1).extract(_b())
    b = KJExtractor(max_ideas=6, cluster_threshold=0.9).extract(_b())
    assert len(b.clusters) >= len(a.clusters)


def test_ledger_integration(tmp_path: Path) -> None:
    ledger = BriefLedger(tmp_path / "kj.jsonl")
    KJExtractor(ledger=ledger).extract(_b())
    events = [r for r in ledger.read() if r.event == "kj_board_constructed"]
    assert events
    tg = ledger.trace_graph()
    assert any(e.get("kind") == "kj_node" for e in tg.evidence_chain)


def test_custom_generator_strategy_injection() -> None:
    class _Stub:
        def generate(self, brief, *, max_ideas):
            return (
                KJNode(node_id="x", text="custom 1", tags=("a",), source="stub"),
                KJNode(node_id="y", text="custom 2", tags=("b",), source="stub"),
            )

    board = KJExtractor(generator=_Stub()).extract(_b())  # type: ignore[arg-type]
    assert len(board.nodes) == 2
    assert all(n.source == "stub" for n in board.nodes)
