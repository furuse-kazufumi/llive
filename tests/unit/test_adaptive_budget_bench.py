# SPDX-License-Identifier: Apache-2.0
"""適応推論予算 PoC: 固定深さ vs 適応深さ の計算量/品質トレードオフ検証."""

from __future__ import annotations

import numpy as np

from llive.perf.adaptive_budget_bench import BudgetModel, compare, simulate


def test_required_depth_bounds():
    m = BudgetModel(max_depth=8)
    req = m.required_depth(np.array([0.0, 0.5, 1.0]))
    assert req.min() >= 1
    assert req.max() <= 8
    assert req[0] < req[2]  # 難しいほど深い


def test_fixed_is_always_correct():
    m = BudgetModel(max_depth=8, n_tasks=2000)
    r = simulate(m, adaptive=False, seed=0)
    assert r.accuracy == 1.0
    assert r.avg_depth == 8.0


def test_adaptive_perfect_estimator_saves_compute_same_quality():
    m = BudgetModel(max_depth=8, n_tasks=4000, confidence_noise=0.0)
    c = compare(m, seed=0)
    # 完全推定器: 大きな計算削減かつ品質同等
    assert c.compute_saving > 0.3
    assert c.accuracy_delta == 0.0
    assert c.adaptive.accuracy == 1.0


def test_adaptive_noisy_estimator_degrades_quality():
    m = BudgetModel(max_depth=8, n_tasks=4000, confidence_noise=0.2)
    c = compare(m, seed=0)
    # ノイズ大: 計算は削減するが品質低下 (early-exit しすぎ)
    assert c.compute_saving > 0.0
    assert c.accuracy_delta < -0.1


def test_quality_monotonic_in_noise():
    lo = compare(BudgetModel(confidence_noise=0.0, n_tasks=4000), seed=1)
    hi = compare(BudgetModel(confidence_noise=0.2, n_tasks=4000), seed=1)
    # ノイズが増えると adaptive 精度は下がる
    assert hi.adaptive.accuracy < lo.adaptive.accuracy
