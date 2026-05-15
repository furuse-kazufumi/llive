# SPDX-License-Identifier: Apache-2.0
"""DTKR TieredRouter の単体テスト."""

from __future__ import annotations

from llive.memory.tier import ChunkRef, Tier, TierCache, TieredRouter


def test_tier_cache_lru_eviction() -> None:
    c = TierCache(Tier.HOT, capacity_bytes=100)
    c.put(ChunkRef(key="a", tier=Tier.HOT, size_bytes=50, value="x"))
    c.put(ChunkRef(key="b", tier=Tier.HOT, size_bytes=50, value="y"))
    evicted = c.put(ChunkRef(key="c", tier=Tier.HOT, size_bytes=50, value="z"))
    assert len(evicted) == 1
    assert evicted[0].key == "a"


def test_tier_cache_refresh_on_put() -> None:
    c = TierCache(Tier.WARM, capacity_bytes=100)
    c.put(ChunkRef(key="a", tier=Tier.WARM, size_bytes=50, value="v1"))
    c.put(ChunkRef(key="a", tier=Tier.WARM, size_bytes=50, value="v2"))
    assert c.used_bytes() == 50
    assert c.get("a").value == "v2"


def test_router_promotes_cold_to_warm() -> None:
    r = TieredRouter(hot_capacity=1000, warm_capacity=1000, cold_capacity=1000)
    r.insert(ChunkRef(key="x", tier=Tier.COLD, size_bytes=10, path=None))
    ref = r.lookup("x")
    assert ref is not None
    assert ref.tier is Tier.WARM


def test_router_promotes_warm_to_hot() -> None:
    r = TieredRouter(hot_capacity=1000, warm_capacity=1000, cold_capacity=1000)
    r.insert(ChunkRef(key="y", tier=Tier.WARM, size_bytes=10, value="hello"))
    ref = r.lookup("y")
    assert ref is not None
    assert ref.tier is Tier.HOT


def test_router_lookup_missing() -> None:
    r = TieredRouter()
    assert r.lookup("missing") is None


def test_router_stats_reflect_inserts() -> None:
    r = TieredRouter()
    r.insert(ChunkRef(key="a", tier=Tier.HOT, size_bytes=10))
    r.insert(ChunkRef(key="b", tier=Tier.WARM, size_bytes=20))
    r.insert(ChunkRef(key="c", tier=Tier.COLD, size_bytes=30))
    s = r.stats()
    assert s["hot_count"] == 1
    assert s["warm_count"] == 1
    assert s["cold_count"] == 1
    assert s["hot_bytes"] == 10
    assert s["warm_bytes"] == 20
    assert s["cold_bytes"] == 30
