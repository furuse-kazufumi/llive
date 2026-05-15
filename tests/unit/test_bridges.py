# SPDX-License-Identifier: Apache-2.0
"""TLB (Thought Layer Bridging) の単体テスト."""

from __future__ import annotations

from llive.fullsense.bridges import (
    Bridge,
    BridgeRegistry,
    GlobalCoordinator,
    LayerScore,
    ManifoldCache,
)
from llive.fullsense.bridges.manifold_cache import semantic_hash

# ---------------------------------------------------------------------------
# Bridge registry
# ---------------------------------------------------------------------------


def test_bridge_fires_and_returns_skip_layers() -> None:
    r = BridgeRegistry()
    r.register(
        Bridge(
            name="factual-high-conf",
            trigger_layer="FACTUAL",
            predicate=lambda x: float(x.get("confidence", 0.0)) >= 0.9,
            skip_layers=("DeceptionFilter", "TimeHorizon"),
        )
    )
    skipped = r.skipped_layers_for("FACTUAL", {"confidence": 0.95})
    assert skipped == {"DeceptionFilter", "TimeHorizon"}


def test_bridge_does_not_fire_when_pred_false() -> None:
    r = BridgeRegistry()
    r.register(
        Bridge(
            name="x",
            trigger_layer="FACTUAL",
            predicate=lambda x: bool(x.get("flag")),
            skip_layers=("Y",),
        )
    )
    assert r.skipped_layers_for("FACTUAL", {"flag": False}) == set()


def test_bridge_predicate_exception_is_caught() -> None:
    r = BridgeRegistry()
    r.register(
        Bridge(
            name="boom",
            trigger_layer="L",
            predicate=lambda x: 1 / 0,  # boom
            skip_layers=("Y",),
        )
    )
    assert r.skipped_layers_for("L", {}) == set()


def test_bridge_only_for_matching_trigger() -> None:
    r = BridgeRegistry()
    r.register(
        Bridge(name="a", trigger_layer="FACTUAL", predicate=lambda x: True, skip_layers=("Y",))
    )
    assert r.skipped_layers_for("OTHER", {}) == set()


# ---------------------------------------------------------------------------
# Global Coordinator
# ---------------------------------------------------------------------------


def test_coordinator_short_circuit_on_high_confidence() -> None:
    gc = GlobalCoordinator(confidence_threshold=0.8)
    scores = [LayerScore("A", 0.9), LayerScore("B", 0.95)]
    should, reason = gc.should_short_circuit(scores)
    assert should is True
    assert "high_confidence" in reason


def test_coordinator_short_circuit_on_low_confidence() -> None:
    gc = GlobalCoordinator(reject_threshold=0.2)
    scores = [LayerScore("A", 0.1), LayerScore("B", 0.05)]
    should, reason = gc.should_short_circuit(scores)
    assert should is True
    assert "low_confidence" in reason


def test_coordinator_in_band_continues() -> None:
    gc = GlobalCoordinator(confidence_threshold=0.9, reject_threshold=0.1)
    scores = [LayerScore("A", 0.5), LayerScore("B", 0.5)]
    should, _ = gc.should_short_circuit(scores)
    assert should is False


def test_coordinator_weighted_aggregate() -> None:
    gc = GlobalCoordinator(weights={"A": 3.0, "B": 1.0})
    scores = [LayerScore("A", 1.0), LayerScore("B", 0.0)]
    agg = gc.aggregate(scores)
    # 3*1 + 1*0 / (3+1) = 0.75
    assert abs(agg - 0.75) < 1e-9


# ---------------------------------------------------------------------------
# Manifold Cache
# ---------------------------------------------------------------------------


def test_cache_hit_and_miss() -> None:
    c = ManifoldCache(capacity=10)
    assert c.get("x") is None  # miss
    c.put("x", {"v": 1})
    assert c.get("x") == {"v": 1}  # hit
    assert c.hit_rate() == 0.5  # 1 hit + 1 miss


def test_cache_eviction() -> None:
    c = ManifoldCache(capacity=2)
    c.put("a", 1)
    c.put("b", 2)
    c.put("c", 3)  # 'a' evicted
    assert c.get("a") is None
    assert c.get("b") == 2
    assert c.get("c") == 3


def test_semantic_hash_stable() -> None:
    h1 = semantic_hash("hello world")
    h2 = semantic_hash("hello world")
    h3 = semantic_hash("hello WORLD")
    assert h1 == h2
    assert h1 != h3


def test_cache_clear() -> None:
    c = ManifoldCache()
    c.put("x", 1)
    c.clear()
    assert len(c) == 0
    assert c.hits == 0
    assert c.misses == 0
