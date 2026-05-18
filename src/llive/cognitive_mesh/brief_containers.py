# SPDX-License-Identifier: Apache-2.0
"""COG-MESH-08 BriefDeque / BriefMap / BriefTree — STL 相当のセッション保持.

requirements_v0.8_cognitive_mesh.md §3 COG-MESH-08 の最小実装。

ユーザ言語化「セッションをどのように持つかも重要。入れ替えや
ブランチを考慮した STL で言うコンテナに入れないといけない」
(`user_cognitive_mesh_model` 追記 22:55) を実装に落とす。

このモジュールは llive 既存の Brief 型に依存せず、汎用的な
BriefRef (id + topic + payload) を扱う。Phase 5 で本格的な
`MultiBriefCoherenceManager` (COG-MESH-01) の内部表現として使う。
"""

from __future__ import annotations

import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator, Optional


@dataclass(frozen=True)
class BriefRef:
    """セッション保持コンテナで扱う Brief 参照 (軽量版)."""

    id: str
    topic: str
    payload: Any = None

    @staticmethod
    def new(topic: str, payload: Any = None) -> "BriefRef":
        return BriefRef(id=str(uuid.uuid4()), topic=topic, payload=payload)


class BriefDeque:
    """両端 push/pop な Brief 列。最新主セッション + 直近サブセッションを高速操作.

    `collections.deque` の薄ラッパだが、API を Brief 文脈に絞る。
    """

    def __init__(self, items: Iterable[BriefRef] = ()) -> None:
        self._items: deque[BriefRef] = deque(items)

    def push_front(self, brief: BriefRef) -> None:
        self._items.appendleft(brief)

    def push_back(self, brief: BriefRef) -> None:
        self._items.append(brief)

    def pop_front(self) -> BriefRef:
        return self._items.popleft()

    def pop_back(self) -> BriefRef:
        return self._items.pop()

    def peek_front(self) -> Optional[BriefRef]:
        return self._items[0] if self._items else None

    def peek_back(self) -> Optional[BriefRef]:
        return self._items[-1] if self._items else None

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[BriefRef]:
        return iter(self._items)

    def __contains__(self, brief_or_id: Any) -> bool:
        if isinstance(brief_or_id, BriefRef):
            return brief_or_id in self._items
        return any(b.id == brief_or_id for b in self._items)


class BriefMap:
    """topic -> Brief 配列 の多重マップ。主題による横断検索.

    `defaultdict(list)` の薄ラッパだが、API を Brief 文脈に絞る。
    """

    def __init__(self) -> None:
        self._by_topic: dict[str, list[BriefRef]] = defaultdict(list)
        self._by_id: dict[str, BriefRef] = {}

    def add(self, brief: BriefRef) -> None:
        if brief.id in self._by_id:
            raise ValueError(f"BriefMap already contains brief id={brief.id}")
        self._by_topic[brief.topic].append(brief)
        self._by_id[brief.id] = brief

    def remove(self, brief_id: str) -> BriefRef:
        if brief_id not in self._by_id:
            raise KeyError(brief_id)
        brief = self._by_id.pop(brief_id)
        self._by_topic[brief.topic].remove(brief)
        if not self._by_topic[brief.topic]:
            del self._by_topic[brief.topic]
        return brief

    def by_topic(self, topic: str) -> list[BriefRef]:
        return list(self._by_topic.get(topic, []))

    def get(self, brief_id: str) -> Optional[BriefRef]:
        return self._by_id.get(brief_id)

    def topics(self) -> list[str]:
        return list(self._by_topic.keys())

    def __len__(self) -> int:
        return len(self._by_id)

    def __contains__(self, brief_id: str) -> bool:
        return brief_id in self._by_id


@dataclass
class _TreeNode:
    brief: BriefRef
    parent_id: Optional[str] = None
    children: list[str] = field(default_factory=list)


class BriefTree:
    """1 Brief から複数 child Brief への分岐構造.

    子から親への merge() で知見集約 (payload を統合) を行う。
    """

    def __init__(self) -> None:
        self._nodes: dict[str, _TreeNode] = {}
        self._roots: list[str] = []

    def add_root(self, brief: BriefRef) -> None:
        if brief.id in self._nodes:
            raise ValueError(f"BriefTree already contains brief id={brief.id}")
        self._nodes[brief.id] = _TreeNode(brief=brief, parent_id=None)
        self._roots.append(brief.id)

    def branch(self, parent_id: str, child: BriefRef) -> str:
        if parent_id not in self._nodes:
            raise KeyError(parent_id)
        if child.id in self._nodes:
            raise ValueError(f"BriefTree already contains brief id={child.id}")
        self._nodes[child.id] = _TreeNode(brief=child, parent_id=parent_id)
        self._nodes[parent_id].children.append(child.id)
        return child.id

    def merge(self, child_ids: list[str]) -> BriefRef:
        """子の payload を集約して 1 つの BriefRef を返す.

        親を変更せず、新しい "merged" BriefRef を返すだけ (純粋関数寄り)。
        実 payload 統合は Phase 5 で BriefRunner と接続して決める。
        """
        if not child_ids:
            raise ValueError("merge requires at least 1 child id")
        children = [self._nodes[cid].brief for cid in child_ids if cid in self._nodes]
        if not children:
            raise ValueError("none of the child ids exist in tree")
        # 親が共通か確認
        parents = {self._nodes[cid].parent_id for cid in child_ids if cid in self._nodes}
        if len(parents) != 1:
            raise ValueError("merge requires children with a common parent")
        parent_id = parents.pop()
        topic = children[0].topic
        payloads = [c.payload for c in children]
        return BriefRef.new(topic=topic, payload={"merged_from": [c.id for c in children], "payloads": payloads, "parent_id": parent_id})

    def get(self, brief_id: str) -> Optional[BriefRef]:
        node = self._nodes.get(brief_id)
        return node.brief if node else None

    def children_of(self, parent_id: str) -> list[BriefRef]:
        node = self._nodes.get(parent_id)
        if node is None:
            return []
        return [self._nodes[cid].brief for cid in node.children]

    def roots(self) -> list[BriefRef]:
        return [self._nodes[rid].brief for rid in self._roots]

    def __len__(self) -> int:
        return len(self._nodes)

    def __contains__(self, brief_id: str) -> bool:
        return brief_id in self._nodes
