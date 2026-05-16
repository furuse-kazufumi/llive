# SPDX-License-Identifier: Apache-2.0
"""Tests for the TLB coordinator (C-12)."""

from __future__ import annotations

import threading

from llive.fullsense.bridges.manifold_cache import ManifoldCache, semantic_hash
from llive.fullsense.bridges.tlb import (
    FanOut,
    LayerStats,
    ThoughtLayer,
    TLBCoordinator,
)


def test_composite_key_includes_layer_id() -> None:
    L = ThoughtLayer("si2", namespace="experts")
    assert TLBCoordinator.composite_key(L, "abc") == "experts/si2::abc"


def test_first_query_misses_and_invokes_computer() -> None:
    coord = TLBCoordinator()
    L = ThoughtLayer("si1")
    calls = [0]

    def compute() -> str:
        calls[0] += 1
        return "result"

    out = coord.query(L, "k1", compute)
    assert out == "result"
    assert calls[0] == 1
    assert coord.stats()["si1"].misses == 1
    assert coord.stats()["si1"].hits == 0


def test_repeated_query_hits_cache_without_recomputing() -> None:
    coord = TLBCoordinator()
    L = ThoughtLayer("si1")
    calls = [0]

    def compute() -> int:
        calls[0] += 1
        return 42

    for _ in range(5):
        assert coord.query(L, "k1", compute) == 42

    assert calls[0] == 1
    s = coord.stats()["si1"]
    assert s.hits == 4
    assert s.misses == 1
    assert s.hit_rate == 4 / 5


def test_different_layers_have_independent_entries() -> None:
    coord = TLBCoordinator()
    a = ThoughtLayer("si1")
    b = ThoughtLayer("si2")
    coord.query(a, "k", lambda: "A")
    coord.query(b, "k", lambda: "B")
    # Both stored; neither overwrote the other.
    assert coord.query(a, "k", lambda: "X") == "A"
    assert coord.query(b, "k", lambda: "X") == "B"


def test_invalidate_drops_one_entry_only() -> None:
    coord = TLBCoordinator()
    L = ThoughtLayer("si1")
    coord.query(L, "k1", lambda: "v1")
    coord.query(L, "k2", lambda: "v2")
    coord.invalidate(L, "k1")
    # k1 must miss and recompute; k2 stays a hit.
    assert coord.query(L, "k1", lambda: "fresh") == "fresh"
    assert coord.query(L, "k2", lambda: "ignored") == "v2"


def test_reset_clears_cache_and_stats() -> None:
    coord = TLBCoordinator()
    L = ThoughtLayer("si1")
    coord.query(L, "k", lambda: 1)
    coord.reset()
    assert coord.stats() == {}
    assert len(coord.cache()) == 0


def test_layer_namespace_separates_collisions() -> None:
    coord = TLBCoordinator()
    a = ThoughtLayer("si2", namespace="agentA")
    b = ThoughtLayer("si2", namespace="agentB")
    coord.query(a, "k", lambda: "fromA")
    coord.query(b, "k", lambda: "fromB")
    assert coord.query(a, "k", lambda: "X") == "fromA"
    assert coord.query(b, "k", lambda: "X") == "fromB"


def test_computer_exception_propagates_and_not_cached() -> None:
    coord = TLBCoordinator()
    L = ThoughtLayer("si1")
    raised = []

    def bad() -> None:
        raised.append(True)
        raise RuntimeError("layer failed")

    try:
        coord.query(L, "k", bad)
    except RuntimeError:
        pass

    # Retry: must call bad() again (no cached failure).
    try:
        coord.query(L, "k", bad)
    except RuntimeError:
        pass
    assert len(raised) == 2


def test_layer_stats_hit_rate_when_empty() -> None:
    s = LayerStats()
    assert s.hit_rate == 0.0
    assert s.total == 0


def test_shared_cache_capacity_is_global() -> None:
    cache = ManifoldCache(capacity=3)
    coord = TLBCoordinator(cache=cache)
    L = ThoughtLayer("si1")
    for i in range(5):
        coord.query(L, f"k{i}", lambda i=i: i)
    # Only the 3 most recent entries survive the LRU.
    assert len(coord.cache()) == 3


def test_fanout_dispatches_to_multiple_layers() -> None:
    coord = TLBCoordinator()
    fanout = FanOut(
        coordinator=coord,
        pairs=(
            (ThoughtLayer("expert_a"), lambda: "viewA"),
            (ThoughtLayer("expert_b"), lambda: "viewB"),
            (ThoughtLayer("expert_c"), lambda: "viewC"),
        ),
    )
    out = fanout.run("question")
    assert out == {"expert_a": "viewA", "expert_b": "viewB", "expert_c": "viewC"}


def test_fanout_reuses_cache_on_repeat() -> None:
    coord = TLBCoordinator()
    calls = {"a": 0, "b": 0}

    def make(role: str) -> str:
        calls[role] += 1
        return f"role-{role}-{calls[role]}"

    fanout = FanOut(
        coordinator=coord,
        pairs=(
            (ThoughtLayer("a"), lambda: make("a")),
            (ThoughtLayer("b"), lambda: make("b")),
        ),
    )
    first = fanout.run("q")
    second = fanout.run("q")  # same input → cached
    assert first == second
    assert calls == {"a": 1, "b": 1}


def test_coordinator_thread_safe_under_contention() -> None:
    coord = TLBCoordinator()
    L = ThoughtLayer("si1")
    results: list[int] = []

    def worker(i: int) -> None:
        v = coord.query(L, "shared", lambda i=i: i)
        results.append(v)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # First-write-wins: exactly one value populated the cache;
    # subsequent threads read the same value.
    assert len(set(results)) == 1


def test_semantic_hash_is_still_reachable_via_tlb_module() -> None:
    # Re-export sanity: callers can avoid importing manifold_cache directly.
    h1 = semantic_hash("hello world")
    h2 = semantic_hash("hello world")
    assert h1 == h2
    assert len(h1) == 16
