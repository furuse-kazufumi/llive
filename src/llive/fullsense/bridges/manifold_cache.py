"""Manifold Cache — semantic hash で過去組合せ memo.

同じ stimulus pattern が再来したら filter chain 計算をスキップして
過去結果を再利用する LRU cache。
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from dataclasses import dataclass


def semantic_hash(content: str, *, n_chars: int = 200) -> str:
    """先頭 N 文字 + sha256 で軽量 hash. 完全な意味的等価性は保証しない."""
    head = (content or "")[:n_chars]
    return hashlib.sha256(head.encode("utf-8", errors="replace")).hexdigest()[:16]


@dataclass
class ManifoldCache:
    """LRU cache: semantic_hash → 任意の結果オブジェクト."""

    capacity: int = 256
    hits: int = 0
    misses: int = 0

    def __post_init__(self) -> None:
        self._store: OrderedDict[str, object] = OrderedDict()

    def get(self, key: str) -> object | None:
        if key in self._store:
            self._store.move_to_end(key)
            self.hits += 1
            return self._store[key]
        self.misses += 1
        return None

    def put(self, key: str, value: object) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = value
        while len(self._store) > self.capacity:
            self._store.popitem(last=False)

    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return 0.0 if total == 0 else self.hits / total

    def __len__(self) -> int:
        return len(self._store)

    def clear(self) -> None:
        self._store.clear()
        self.hits = 0
        self.misses = 0


__all__ = ["ManifoldCache", "semantic_hash"]
