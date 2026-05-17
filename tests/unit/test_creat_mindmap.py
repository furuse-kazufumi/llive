# SPDX-License-Identifier: Apache-2.0
"""CREAT-02 — MindMapBuilder tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from llive.brief import Brief, BriefLedger
from llive.creat import MindMapBuilder, MindMapNode, MindMapTree


def _b(**overrides) -> Brief:
    fields: dict = dict(brief_id="mm-1", goal="システムを設計する")
    fields.update(overrides)
    return Brief(**fields)


def test_build_returns_root_and_children() -> None:
    tree = MindMapBuilder(max_depth=2).build(_b())
    assert isinstance(tree, MindMapTree)
    assert tree.root.depth == 0
    children = tree.children_of(tree.root.node_id)
    assert children, "root should have depth-1 children"
    assert all(c.depth == 1 for c in children)


def test_max_depth_respected() -> None:
    t1 = MindMapBuilder(max_depth=1).build(_b())
    t2 = MindMapBuilder(max_depth=3).build(_b())
    assert t1.max_depth() == 1
    assert t2.max_depth() >= 2


def test_ledger_integration(tmp_path: Path) -> None:
    ledger = BriefLedger(tmp_path / "mm.jsonl")
    MindMapBuilder(ledger=ledger).build(_b())
    events = [r for r in ledger.read() if r.event == "mindmap_constructed"]
    assert events
    tg = ledger.trace_graph()
    assert any(e.get("kind") == "mindmap_node" for e in tg.evidence_chain)


def test_custom_expander_strategy() -> None:
    class _Stub:
        def expand(self, label, depth, *, brief):
            if depth >= 1:
                return ()
            return ("子A", "子B")

    tree = MindMapBuilder(expander=_Stub(), max_depth=3).build(_b())  # type: ignore[arg-type]
    assert tree.max_depth() == 1
    labels = {n.label for n in tree.nodes}
    assert "子A" in labels and "子B" in labels
