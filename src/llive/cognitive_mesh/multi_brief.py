# SPDX-License-Identifier: Apache-2.0
"""COG-MESH-01 MultiBriefCoherenceManager — 複数 Brief 並列保持 + cross-brief 相互更新.

requirements_v0.8_cognitive_mesh.md §3 COG-MESH-01 の最小実装.

ユーザ言語化「頭の中に複数セッションが常にある状態。AI より頭いいかも」
(user_cognitive_mesh_model §11) を architectural に反映。

仕様:
- BriefDeque (主セッション + 直近) と BriefMap (主題横断検索) を内部保持
- coherence_graph: dict[(brief_id, brief_id), float] (重み付き相互参照)
- attach() で Brief 追加、detach() で除去
- record_impact(src, dst, weight) で edge を加算
- tick() で全 Brief を巡回し、coherence_graph から impact event を抽出
- freeze() / thaw() で一時凍結

Phase 7 で networkx + 実 Brief 統合、本実装は軽量 dict ベース。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from llive.cognitive_mesh.brief_containers import (
    BriefDeque,
    BriefMap,
    BriefRef,
)

if TYPE_CHECKING:
    from llive.brief.types import Brief


@dataclass(frozen=True)
class CoherenceEvent:
    """cross-brief 相互参照を Annotation Channel cog.cross_brief_impact 相当で出力."""

    src_brief_id: str
    dst_brief_id: str
    weight: float
    timestamp: datetime


@dataclass
class MultiBriefCoherenceManager:
    """複数 Brief を並列保持し、相互更新する coherence_graph を管理."""

    update_interval: float = 5.0  # 秒
    _deque: BriefDeque = field(default_factory=BriefDeque)
    _map: BriefMap = field(default_factory=BriefMap)
    _coherence: dict[tuple[str, str], float] = field(default_factory=dict)
    _frozen: set[str] = field(default_factory=set)
    _events: list[CoherenceEvent] = field(default_factory=list)
    _impact_threshold: float = 1.0  # この値以上を coherence event として emit

    # ------------------------------------------------------------------
    # attach / detach
    # ------------------------------------------------------------------

    def attach(self, brief: BriefRef) -> str:
        if brief.id in self._map:
            raise ValueError(f"Brief id={brief.id} already attached")
        self._deque.push_front(brief)
        self._map.add(brief)
        return brief.id

    def detach(self, brief_id: str) -> BriefRef:
        if brief_id not in self._map:
            raise KeyError(brief_id)
        brief = self._map.remove(brief_id)
        # deque から削除
        remaining = [b for b in self._deque if b.id != brief_id]
        self._deque = BriefDeque(remaining)
        # coherence_graph から関連 edge を削除
        keys_to_drop = [k for k in self._coherence if brief_id in k]
        for k in keys_to_drop:
            del self._coherence[k]
        self._frozen.discard(brief_id)
        return brief

    def __len__(self) -> int:
        return len(self._map)

    def brief_ids(self) -> list[str]:
        return [b.id for b in self._deque]

    def by_topic(self, topic: str) -> list[BriefRef]:
        return self._map.by_topic(topic)

    # ------------------------------------------------------------------
    # freeze / thaw
    # ------------------------------------------------------------------

    def freeze(self, brief_id: str) -> None:
        if brief_id not in self._map:
            raise KeyError(brief_id)
        self._frozen.add(brief_id)

    def thaw(self, brief_id: str) -> None:
        self._frozen.discard(brief_id)

    def is_frozen(self, brief_id: str) -> bool:
        return brief_id in self._frozen

    # ------------------------------------------------------------------
    # coherence_graph
    # ------------------------------------------------------------------

    def record_impact(self, src_id: str, dst_id: str, weight: float = 1.0) -> None:
        if src_id == dst_id:
            raise ValueError("self-impact not allowed")
        if src_id not in self._map:
            raise KeyError(f"src brief not attached: {src_id}")
        if dst_id not in self._map:
            raise KeyError(f"dst brief not attached: {dst_id}")
        key = (src_id, dst_id)
        self._coherence[key] = self._coherence.get(key, 0.0) + weight

    def impact_weight(self, src_id: str, dst_id: str) -> float:
        return self._coherence.get((src_id, dst_id), 0.0)

    # ------------------------------------------------------------------
    # tick — impact event を抽出
    # ------------------------------------------------------------------

    def tick(self, now: datetime | None = None) -> list[CoherenceEvent]:
        if now is None:
            now = datetime.now()
        events: list[CoherenceEvent] = []
        for (src, dst), weight in self._coherence.items():
            if src in self._frozen or dst in self._frozen:
                continue
            if weight >= self._impact_threshold:
                events.append(
                    CoherenceEvent(
                        src_brief_id=src,
                        dst_brief_id=dst,
                        weight=weight,
                        timestamp=now,
                    )
                )
        self._events.extend(events)
        return events

    def latest_events(self, n: int = 10) -> list[CoherenceEvent]:
        return self._events[-n:]
