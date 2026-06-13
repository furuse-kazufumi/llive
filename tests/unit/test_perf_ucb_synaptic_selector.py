# SPDX-License-Identifier: Apache-2.0
"""Tests for UCBSynapticSelector — UCB1-based selection.

SynapticSelector の Phase B-4 で発見した「真の最良に収束しない」病理を
解消するための代替実装. 同じ API を持つので既存 demo に差替え可能.
"""
from __future__ import annotations

import math
import random

import pytest

from llive.perf.synaptic_selector import (
    StrategyVariant,
    UCBSynapticSelector,
)


def _three_variants():
    return [
        StrategyVariant(name="fast", impl=lambda: "fast"),
        StrategyVariant(name="medium", impl=lambda: "medium"),
        StrategyVariant(name="slow", impl=lambda: "slow"),
    ]


# ---------------------------------------------------------------------------
# Construction validation
# ---------------------------------------------------------------------------


def test_empty_variants_rejected():
    with pytest.raises(ValueError, match="at least one"):
        UCBSynapticSelector(variants=[])


def test_duplicate_variant_names_rejected():
    a = StrategyVariant(name="dup", impl=lambda: 1)
    b = StrategyVariant(name="dup", impl=lambda: 2)
    with pytest.raises(ValueError, match="duplicate"):
        UCBSynapticSelector(variants=[a, b])


def test_negative_exploration_c_rejected():
    with pytest.raises(ValueError, match="exploration_c"):
        UCBSynapticSelector(variants=_three_variants(), exploration_c=-0.1)


def test_invalid_latency_window():
    with pytest.raises(ValueError, match="latency_window"):
        UCBSynapticSelector(variants=_three_variants(), latency_window=0)


# ---------------------------------------------------------------------------
# Unseen variants are tried first
# ---------------------------------------------------------------------------


def test_unseen_variants_are_tried_before_repeating():
    sel = UCBSynapticSelector(variants=_three_variants(), rng=random.Random(0))
    seen: set[str] = set()
    for _ in range(3):
        v = sel.choose()
        sel.record_result(v, 1.0)
        seen.add(v.name)
    assert seen == {"fast", "medium", "slow"}


# ---------------------------------------------------------------------------
# UCB converges to truly fastest variant (B-4 病理が解消されること)
# ---------------------------------------------------------------------------


def _simulate(sel: UCBSynapticSelector, latency_map: dict[str, float], n: int) -> None:
    for _ in range(n):
        v = sel.choose()
        sel.record_result(v, latency_map[v.name])


def test_ucb_converges_to_truly_fastest():
    """B-4 の病理ケース: 微差 latency でも真の最速に収束する."""
    sel = UCBSynapticSelector(
        variants=_three_variants(),
        exploration_c=math.sqrt(2.0),
        rng=random.Random(2026),
    )
    # 微差: fast=0.95, medium=1.00, slow=1.05 (差分 5%)
    _simulate(sel, {"fast": 0.95, "medium": 1.00, "slow": 1.05}, n=500)
    assert sel.converge().name == "fast"


def test_ucb_converges_in_large_disparity():
    sel = UCBSynapticSelector(
        variants=_three_variants(),
        rng=random.Random(0),
    )
    _simulate(sel, {"fast": 1.0, "medium": 10.0, "slow": 100.0}, n=500)
    assert sel.converge().name == "fast"


def test_ucb_visits_every_variant_at_least_once():
    """UCB は未試行 variant を最優先するので必ず全 variant が呼ばれる."""
    sel = UCBSynapticSelector(variants=_three_variants(), rng=random.Random(0))
    _simulate(sel, {"fast": 1.0, "medium": 2.0, "slow": 3.0}, n=300)
    counts = {v.name: v.n_calls for v in sel.variants}
    assert all(c >= 1 for c in counts.values()), counts
    # 真の最良 (fast) が最多呼び出し
    assert counts["fast"] == max(counts.values())


def test_ucb_high_exploration_distributes_more_evenly():
    """exploration_c を上げると各 variant の呼び出し回数差が縮む."""
    sel = UCBSynapticSelector(
        variants=_three_variants(),
        exploration_c=10.0,  # 強い exploration
        rng=random.Random(0),
    )
    _simulate(sel, {"fast": 1.0, "medium": 2.0, "slow": 3.0}, n=300)
    counts = {v.name: v.n_calls for v in sel.variants}
    # 全 variant が一定回数以上呼ばれる (exploration が強いので 50+ 期待)
    assert all(c >= 50 for c in counts.values()), counts


# ---------------------------------------------------------------------------
# Recording + snapshot
# ---------------------------------------------------------------------------


def test_record_negative_latency_rejected():
    sel = UCBSynapticSelector(variants=_three_variants())
    with pytest.raises(ValueError, match="latency_ms"):
        sel.record_result(sel.variants[0], -1.0)


def test_snapshot_includes_reward():
    sel = UCBSynapticSelector(variants=_three_variants())
    for v, lat in zip(sel.variants, [1.0, 2.0, 3.0]):
        sel.record_result(v, lat)
    snap = sel.snapshot()
    by = {s["name"]: s for s in snap}
    # fast (lat 1.0) が一番 reward 高い
    assert by["fast"]["reward"] >= by["medium"]["reward"] >= by["slow"]["reward"]
    for entry in snap:
        assert {"name", "weight", "n_calls", "avg_latency_ms", "last_latency_ms", "reward"} <= entry.keys()


def test_latency_window_truncates():
    sel = UCBSynapticSelector(variants=_three_variants(), latency_window=5)
    for i in range(20):
        sel.record_result(sel.variants[0], float(i))
    # window 5 まで切り詰められ, 直近 5 件 (15..19) のみ残る
    assert len(sel._latencies["fast"]) == 5
    assert sel._latencies["fast"] == [15.0, 16.0, 17.0, 18.0, 19.0]


def test_call_invokes_impl():
    sel = UCBSynapticSelector(variants=_three_variants(), rng=random.Random(0))
    r = sel.call()
    assert r in {"fast", "medium", "slow"}
    assert len(sel.history()) == 1


def test_history_capped():
    sel = UCBSynapticSelector(variants=_three_variants(), rng=random.Random(0))
    sel._history_cap = 30
    for _ in range(100):
        v = sel.choose()
        sel.record_result(v, 1.0)
    assert len(sel.history()) == 30


def test_thread_safety_smoke():
    import threading

    sel = UCBSynapticSelector(variants=_three_variants(), rng=random.Random(0))
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
