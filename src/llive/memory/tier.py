# SPDX-License-Identifier: Apache-2.0
"""DTKR — Disk-Tier Knowledge Routing.

VRAM (hot) / RAM (warm) / SSD (cold) / HDD (frozen) の 4 tier に knowledge
chunks を配置する LRU policy の MVP. 実 GPU 操作は将来。今は in-memory の
論理 tier (hot/warm) + on-disk metadata (cold/frozen) を扱う。
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class Tier(StrEnum):
    HOT = "hot"     # VRAM (in-process, GPU-mapped 想定)
    WARM = "warm"   # RAM (in-process Python dict)
    COLD = "cold"   # SSD (file system)
    FROZEN = "frozen"  # HDD / off-host (archive)


@dataclass
class ChunkRef:
    """1 つの knowledge chunk への参照. テキストは tier に応じて lazy load."""

    key: str
    tier: Tier
    size_bytes: int = 0
    path: Path | None = None
    """COLD/FROZEN tier の実体パス. HOT/WARM では None."""

    value: object | None = None
    """HOT/WARM tier の本体 (Python オブジェクト or bytes)."""


@dataclass
class TierCache:
    """1 tier 分の LRU 容量制限付きキャッシュ.

    MVP: HOT/WARM は in-memory、COLD/FROZEN は path 参照のみ。
    """

    tier: Tier
    capacity_bytes: int = 256 * 1024 * 1024  # 256 MB
    _entries: OrderedDict[str, ChunkRef] = field(default_factory=OrderedDict)
    _used_bytes: int = 0

    def get(self, key: str) -> ChunkRef | None:
        if key in self._entries:
            self._entries.move_to_end(key)
            return self._entries[key]
        return None

    def put(self, ref: ChunkRef) -> list[ChunkRef]:
        """Insert (or refresh) ``ref``. 容量を超えたら evicted を返す."""
        evicted: list[ChunkRef] = []
        if ref.key in self._entries:
            old = self._entries.pop(ref.key)
            self._used_bytes -= old.size_bytes
        self._entries[ref.key] = ref
        self._used_bytes += ref.size_bytes
        while self._used_bytes > self.capacity_bytes and self._entries:
            _k_old, ref_old = self._entries.popitem(last=False)
            self._used_bytes -= ref_old.size_bytes
            evicted.append(ref_old)
        return evicted

    def used_bytes(self) -> int:
        return self._used_bytes

    def __len__(self) -> int:
        return len(self._entries)


@dataclass
class TieredRouter:
    """4 tier をまとめて管理する router.

    promotion policy: COLD で hit → WARM に昇格、WARM で hit → HOT に昇格。
    demotion: HOT が満杯 → 末尾を WARM に降格、以下同様。FROZEN は archive
    のみで読み出されない (Level 3 で復活 routing 実装)。
    """

    hot_capacity: int = 64 * 1024 * 1024
    warm_capacity: int = 1024 * 1024 * 1024
    cold_capacity: int = 16 * 1024 * 1024 * 1024
    _hot: TierCache = field(init=False)
    _warm: TierCache = field(init=False)
    _cold: TierCache = field(init=False)

    def __post_init__(self) -> None:
        self._hot = TierCache(Tier.HOT, self.hot_capacity)
        self._warm = TierCache(Tier.WARM, self.warm_capacity)
        self._cold = TierCache(Tier.COLD, self.cold_capacity)

    def lookup(self, key: str) -> ChunkRef | None:
        """tier を hot→warm→cold で順に探し、見つかれば 1 段昇格させる."""
        ref = self._hot.get(key)
        if ref is not None:
            return ref
        ref = self._warm.get(key)
        if ref is not None:
            ref = ChunkRef(key=ref.key, tier=Tier.HOT, size_bytes=ref.size_bytes, value=ref.value)
            for ev in self._hot.put(ref):
                # demote evicted hot → warm
                ev2 = ChunkRef(key=ev.key, tier=Tier.WARM, size_bytes=ev.size_bytes, value=ev.value)
                self._warm.put(ev2)
            return ref
        ref = self._cold.get(key)
        if ref is not None:
            promoted = ChunkRef(key=ref.key, tier=Tier.WARM, size_bytes=ref.size_bytes, path=ref.path)
            self._warm.put(promoted)
            return promoted
        return None

    def insert(self, ref: ChunkRef) -> None:
        if ref.tier is Tier.HOT:
            self._hot.put(ref)
        elif ref.tier is Tier.WARM:
            self._warm.put(ref)
        else:
            self._cold.put(ref)

    def stats(self) -> dict[str, int]:
        return {
            "hot_count": len(self._hot),
            "warm_count": len(self._warm),
            "cold_count": len(self._cold),
            "hot_bytes": self._hot.used_bytes(),
            "warm_bytes": self._warm.used_bytes(),
            "cold_bytes": self._cold.used_bytes(),
        }


__all__ = ["ChunkRef", "Tier", "TierCache", "TieredRouter"]
