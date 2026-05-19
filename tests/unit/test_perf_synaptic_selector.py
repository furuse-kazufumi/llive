# SPDX-License-Identifier: Apache-2.0
"""Tests for SynapticSelector — Hebbian-style variant selection."""
from __future__ import annotations

import random
import time

import pytest

from llive.perf.synaptic_selector import (
    SelectionRecord,
    StrategyVariant,
    SynapticSelector,
)


# ---------------------------------------------------------------------------
# Construction / validation
# ---------------------------------------------------------------------------


def _three_variants():
    """fast / medium / slow の 3 variant. impl は固定 latency を sleep する."""
    def fast():
        return "fast"

    def medium():
        return "medium"

    def slow():
        return "slow"

    return [
        StrategyVariant(name="fast", impl=fast),
        StrategyVariant(name="medium", impl=medium),
        StrategyVariant(name="slow", impl=slow),
    ]


def test_empty_variants_rejected():
    with pytest.raises(ValueError, match="at least one"):
        SynapticSelector(variants=[])


def test_duplicate_variant_names_rejected():
    v = StrategyVariant(name="dup", impl=lambda: 1)
    w = StrategyVariant(name="dup", impl=lambda: 2)
    with pytest.raises(ValueError, match="duplicate"):
        SynapticSelector(variants=[v, w])


def test_invalid_learning_rate():
    with pytest.raises(ValueError, match="learning_rate"):
        SynapticSelector(variants=_three_variants(), learning_rate=0.0)
    with pytest.raises(ValueError, match="learning_rate"):
        SynapticSelector(variants=_three_variants(), learning_rate=1.5)


def test_invalid_exploration_rate():
    with pytest.raises(ValueError, match="exploration_rate"):
        SynapticSelector(variants=_three_variants(), exploration_rate=-0.1)
    with pytest.raises(ValueError, match="exploration_rate"):
        SynapticSelector(variants=_three_variants(), exploration_rate=1.5)


def test_invalid_ewma_alpha():
    with pytest.raises(ValueError, match="ewma_alpha"):
        SynapticSelector(variants=_three_variants(), ewma_alpha=0.0)


def test_invalid_weight_bounds():
    with pytest.raises(ValueError, match="min_weight"):
        SynapticSelector(
            variants=_three_variants(), min_weight=1.0, max_weight=1.0
        )


def test_initial_weight_clipped_to_bounds():
    v = StrategyVariant(name="x", impl=lambda: 1, weight=200.0)
    sel = SynapticSelector(variants=[v], max_weight=10.0)
    assert sel.variants[0].weight == 10.0


# ---------------------------------------------------------------------------
# choose / converge / call
# ---------------------------------------------------------------------------


def test_choose_returns_a_variant():
    sel = SynapticSelector(variants=_three_variants(), rng=random.Random(42))
    chosen = sel.choose()
    assert chosen.name in {"fast", "medium", "slow"}


def test_converge_returns_max_weight():
    variants = _three_variants()
    variants[1].weight = 10.0  # medium が突出
    sel = SynapticSelector(variants=variants)
    assert sel.converge().name == "medium"


def test_pure_greedy_when_exploration_zero():
    variants = _three_variants()
    variants[0].weight = 99.0  # fast 突出
    sel = SynapticSelector(
        variants=variants, exploration_rate=0.0, rng=random.Random(0)
    )
    # 重み突出なので softmax ほぼ 1.0 で fast.
    counts = {"fast": 0, "medium": 0, "slow": 0}
    for _ in range(200):
        counts[sel.choose().name] += 1
    assert counts["fast"] >= 180


def test_call_invokes_impl_and_records():
    sel = SynapticSelector(variants=_three_variants(), rng=random.Random(7))
    result = sel.call()
    assert result in {"fast", "medium", "slow"}
    # 1 件履歴あり
    assert len(sel.history()) == 1


# ---------------------------------------------------------------------------
# Hebbian update — fast variant should converge to dominance
# ---------------------------------------------------------------------------


def _simulate(sel: SynapticSelector, latency_map: dict[str, float], n: int):
    """sel.choose() → 指定 latency で record_result() を n 回繰返す."""
    for _ in range(n):
        v = sel.choose()
        sel.record_result(v, latency_map[v.name])


def test_fast_variant_converges_to_max_weight():
    """fast=1ms, medium=10ms, slow=100ms で 500 回回したら fast の重みが最大."""
    sel = SynapticSelector(
        variants=_three_variants(),
        learning_rate=0.20,
        exploration_rate=0.05,
        rng=random.Random(2026),
    )
    _simulate(sel, {"fast": 1.0, "medium": 10.0, "slow": 100.0}, n=500)
    snap = sel.snapshot()
    by = {s["name"]: s for s in snap}
    assert by["fast"]["weight"] > by["medium"]["weight"]
    assert by["medium"]["weight"] > by["slow"]["weight"]
    assert sel.converge().name == "fast"


def test_weights_stay_within_bounds():
    sel = SynapticSelector(
        variants=_three_variants(),
        learning_rate=0.50,
        min_weight=0.05,
        max_weight=5.0,
        rng=random.Random(1),
    )
    _simulate(sel, {"fast": 1.0, "medium": 5.0, "slow": 50.0}, n=300)
    for v in sel.variants:
        assert 0.05 - 1e-9 <= v.weight <= 5.0 + 1e-9


def test_n_calls_and_ewma_are_tracked():
    sel = SynapticSelector(
        variants=_three_variants(), exploration_rate=1.0, rng=random.Random(0)
    )
    # exploration=1.0 で一様分布 → 全 variant が呼ばれることを期待
    _simulate(sel, {"fast": 1.0, "medium": 5.0, "slow": 25.0}, n=150)
    total = sum(v.n_calls for v in sel.variants)
    assert total == 150
    assert all(v.n_calls > 0 for v in sel.variants)
    # ewma が観測 latency に近い順序になる
    by = {v.name: v for v in sel.variants}
    assert by["fast"].avg_latency_ms < by["medium"].avg_latency_ms
    assert by["medium"].avg_latency_ms < by["slow"].avg_latency_ms


def test_record_with_negative_latency_rejected():
    sel = SynapticSelector(variants=_three_variants())
    with pytest.raises(ValueError, match="latency_ms"):
        sel.record_result(sel.variants[0], -1.0)


def test_history_capped():
    sel = SynapticSelector(variants=_three_variants(), rng=random.Random(0))
    sel._history_cap = 50
    for _ in range(200):
        v = sel.choose()
        sel.record_result(v, 1.0)
    assert len(sel.history()) == 50


def test_snapshot_shape():
    sel = SynapticSelector(variants=_three_variants(), rng=random.Random(0))
    sel.record_result(sel.variants[0], 1.0)
    snap = sel.snapshot()
    assert {s["name"] for s in snap} == {"fast", "medium", "slow"}
    for entry in snap:
        assert {"name", "weight", "n_calls", "avg_latency_ms", "last_latency_ms"} <= entry.keys()


def test_thread_safety_smoke():
    """並列に call() しても crash / race しないことの smoke."""
    import threading

    sel = SynapticSelector(
        variants=_three_variants(),
        rng=random.Random(0),
    )
    errors: list[Exception] = []

    def worker():
        try:
            for _ in range(100):
                sel.call()
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    total = sum(v.n_calls for v in sel.variants)
    assert total == 400


def test_selection_record_fields():
    sel = SynapticSelector(variants=_three_variants(), rng=random.Random(0))
    rec = sel.record_result(sel.variants[0], 5.0)
    assert isinstance(rec, SelectionRecord)
    assert rec.variant_name == "fast"
    assert rec.latency_ms == 5.0
    assert rec.timestamp_s > 0
