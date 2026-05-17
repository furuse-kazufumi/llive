# SPDX-License-Identifier: Apache-2.0
"""CREAT-02 — MindMap node generator (minimal prototype).

Brief から root + N 階層の子ノードを deterministic に展開する MindMap 層。
KJ法 (発散) の次の段階「構造化」を担う。

設計:

* :class:`MindMapNode` — id / label / parent_id / depth / source
* :class:`MindMapTree` — root + 子ノード集合
* :class:`MindMapBuilder` — Brief → MindMapTree (deterministic)
* :class:`BranchExpander` (Protocol) — 子ノード候補を返す Strategy 注入点

`bind_ledger()` で `mindmap_constructed` event 連動。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, Sequence

if TYPE_CHECKING:
    from llive.brief.ledger import BriefLedger
    from llive.brief.types import Brief


_TOKEN_RE = re.compile(r"[A-Za-z0-9_ぁ-ゟ゠-ヿ一-鿿]+", re.UNICODE)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MindMapNode:
    """1 件の MindMap ノード."""

    node_id: str
    label: str
    parent_id: str | None
    depth: int
    source: str = "deterministic"

    def to_payload(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "label": self.label,
            "parent_id": self.parent_id,
            "depth": self.depth,
            "source": self.source,
        }


@dataclass(frozen=True)
class MindMapTree:
    """root から DFS 展開された MindMap."""

    brief_id: str
    root: MindMapNode
    nodes: tuple[MindMapNode, ...]   # root を含む全ノード

    def children_of(self, parent_id: str) -> tuple[MindMapNode, ...]:
        return tuple(n for n in self.nodes if n.parent_id == parent_id)

    def max_depth(self) -> int:
        return max((n.depth for n in self.nodes), default=0)

    def to_payload(self) -> dict[str, object]:
        return {
            "brief_id": self.brief_id,
            "root_id": self.root.node_id,
            "max_depth": self.max_depth(),
            "nodes": [n.to_payload() for n in self.nodes],
        }


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------


class BranchExpander(Protocol):
    """ある node ラベルから子 label 候補を返す Strategy."""

    def expand(self, label: str, depth: int, *, brief: "Brief") -> tuple[str, ...]:  # pragma: no cover
        ...


# Deterministic prefix families per depth level — 階層ごとに違う観点で展開。
_DEPTH_PREFIXES: tuple[tuple[str, ...], ...] = (
    (),  # depth 0 = root
    ("構造", "制約", "リスク"),               # depth 1
    ("分解", "代替案", "検証"),               # depth 2
    ("ベースライン", "比較対象", "停止条件"),  # depth 3
)


@dataclass(frozen=True)
class DeterministicBranchExpander:
    """label + depth から固定プレフィックスで子を生成する mock expander."""

    max_branch: int = 3

    def expand(self, label: str, depth: int, *, brief: "Brief") -> tuple[str, ...]:
        if depth + 1 >= len(_DEPTH_PREFIXES):
            return ()
        prefixes = _DEPTH_PREFIXES[depth + 1][: self.max_branch]
        return tuple(f"{p}: {label}" for p in prefixes)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


class MindMapBuilder:
    """Brief → MindMapTree (deterministic DFS expansion)."""

    def __init__(
        self,
        *,
        expander: BranchExpander | None = None,
        max_depth: int = 3,
        ledger: "BriefLedger | None" = None,
    ) -> None:
        self._expander: BranchExpander = expander or DeterministicBranchExpander()
        self._max_depth = max_depth
        self._ledger = ledger

    def bind_ledger(self, ledger: "BriefLedger | None") -> None:
        self._ledger = ledger

    def build(self, brief: "Brief") -> MindMapTree:
        root = MindMapNode(
            node_id=f"mm-{brief.brief_id}-root",
            label=brief.goal,
            parent_id=None,
            depth=0,
        )
        all_nodes: list[MindMapNode] = [root]
        self._expand(root, brief=brief, all_nodes=all_nodes)
        tree = MindMapTree(brief_id=brief.brief_id, root=root, nodes=tuple(all_nodes))
        if self._ledger is not None:
            self._ledger.append("mindmap_constructed", tree.to_payload())
        return tree

    def _expand(
        self,
        parent: MindMapNode,
        *,
        brief: "Brief",
        all_nodes: list[MindMapNode],
    ) -> None:
        if parent.depth >= self._max_depth:
            return
        children_labels = self._expander.expand(parent.label, parent.depth, brief=brief)
        for i, label in enumerate(children_labels):
            child = MindMapNode(
                node_id=f"{parent.node_id}-{i}",
                label=label,
                parent_id=parent.node_id,
                depth=parent.depth + 1,
            )
            all_nodes.append(child)
            self._expand(child, brief=brief, all_nodes=all_nodes)


__all__ = [
    "BranchExpander",
    "DeterministicBranchExpander",
    "MindMapBuilder",
    "MindMapNode",
    "MindMapTree",
]
