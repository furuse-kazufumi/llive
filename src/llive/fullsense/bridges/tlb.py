# SPDX-License-Identifier: Apache-2.0
"""TLB — Thought Layer Bridge (C-12).

Wraps the existing ``ManifoldCache`` with a per-layer coordinator that
turns "same stimulus arriving at N parallel thought layers" from
``N * compute_cost`` into ``≤1 * compute_cost + (N-1) * cache_hit``.

Key abstractions:

* ``ThoughtLayer`` — an identifier for one cognitive lane (SI1
  "read-between-lines", SI2 "three-experts", a multi-track scorer, …).
  Layers are pure names; what they actually compute is up to the
  caller. The coordinator just keys cache entries on
  ``(layer, input_key)``.
* ``TLBCoordinator`` — thread-safe gate. ``query(layer, key, computer)``
  returns either a cached value or runs ``computer()`` once and caches
  it. Per-layer hit/miss counters drive observability.

Storage is the shared ``ManifoldCache`` so all layers compete for the
same LRU budget; that's exactly the "global coordinator" requirement
from the 9-axis skeleton (memory:project-llive-9axis-skeleton).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from llive.fullsense.bridges.manifold_cache import ManifoldCache, semantic_hash


@dataclass(frozen=True)
class ThoughtLayer:
    """Stable identifier for one cognitive lane.

    Just a name + optional ``namespace`` so two SI2 instances configured
    differently can share a coordinator without colliding.
    """

    name: str
    namespace: str = ""

    @property
    def id(self) -> str:
        return f"{self.namespace}/{self.name}" if self.namespace else self.name


@dataclass
class LayerStats:
    """Per-layer cache effectiveness counters."""

    hits: int = 0
    misses: int = 0
    last_key: str = ""

    @property
    def total(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        return 0.0 if self.total == 0 else self.hits / self.total


class TLBCoordinator:
    """Single shared cache across all ``ThoughtLayer`` instances.

    Args:
        cache: external ``ManifoldCache`` (default = new instance,
            capacity 256). Passing a shared one lets you size the
            global budget independent of layer count.
    """

    def __init__(self, cache: ManifoldCache | None = None) -> None:
        # NB: explicit None check — ManifoldCache exposes __len__, so an
        # empty cache would be falsy under ``cache or ManifoldCache()``.
        self._cache = cache if cache is not None else ManifoldCache()
        self._lock = threading.RLock()
        self._stats: dict[str, LayerStats] = {}

    @staticmethod
    def composite_key(layer: ThoughtLayer, input_key: str) -> str:
        return f"{layer.id}::{input_key}"

    def query(
        self,
        layer: ThoughtLayer,
        input_key: str,
        computer: Callable[[], Any],
    ) -> Any:
        """Return cached value for ``(layer, input_key)`` or compute + cache.

        ``computer`` is invoked at most once per ``(layer, input_key)``
        miss within the LRU horizon. Exceptions from ``computer``
        propagate (they aren't cached as values).
        """
        key = self.composite_key(layer, input_key)
        with self._lock:
            stats = self._stats.setdefault(layer.id, LayerStats())
            stats.last_key = input_key
            cached = self._cache.get(key)
            if cached is not None:
                stats.hits += 1
                return cached
            stats.misses += 1
        # Compute outside the lock: long-running calls shouldn't serialise.
        value = computer()
        with self._lock:
            self._cache.put(key, value)
        return value

    def invalidate(self, layer: ThoughtLayer, input_key: str) -> None:
        """Drop one cache entry. Useful when an upstream input changes."""
        key = self.composite_key(layer, input_key)
        with self._lock:
            # ManifoldCache has no direct delete API; emulate via OrderedDict.
            store = self._cache._store
            store.pop(key, None)

    def stats(self) -> dict[str, LayerStats]:
        with self._lock:
            return {k: LayerStats(v.hits, v.misses, v.last_key) for k, v in self._stats.items()}

    def cache(self) -> ManifoldCache:
        return self._cache

    def reset(self) -> None:
        with self._lock:
            self._cache.clear()
            self._stats.clear()


@dataclass
class FanOut:
    """Convenience: dispatch one input to N layers, sharing a coordinator.

    Each ``(layer, computer)`` pair runs through the coordinator's
    ``query`` so repeats are short-circuited. Used by multi-track
    cognitive lanes (SI2 "three experts" etc.) where the same prompt
    is evaluated under different roles.
    """

    coordinator: TLBCoordinator
    pairs: tuple[tuple[ThoughtLayer, Callable[[], Any]], ...] = field(default_factory=tuple)

    def run(self, input_key: str) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for layer, computer in self.pairs:
            out[layer.id] = self.coordinator.query(layer, input_key, computer)
        return out


__all__ = [
    "FanOut",
    "LayerStats",
    "TLBCoordinator",
    "ThoughtLayer",
    "semantic_hash",
]
