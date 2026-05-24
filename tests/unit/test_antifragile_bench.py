# SPDX-License-Identifier: Apache-2.0
"""Antifragile 定量比較 PoC: 局所最適脱出を baseline と比較して検証."""

from __future__ import annotations

import numpy as np

from llive.evolution.antifragile_bench import (
    compare,
    deceptive_fitness,
    run_ga,
)


def test_landscape_global_beats_local():
    # 大域最適 (x=3) は局所最適 (x=-2) より高い
    assert deceptive_fitness(np.array([3.0]))[0] > deceptive_fitness(np.array([-2.0]))[0]
    assert deceptive_fitness(np.array([3.0]))[0] > 0.99
    assert abs(deceptive_fitness(np.array([-2.0]))[0] - 0.85) < 0.01


def test_baseline_gets_trapped():
    # 小 sigma の baseline は谷を越えられず局所最適 (~0.85) に捕まる
    r = run_ga(use_antifragile=False, seed=0)
    assert not r.reached_global
    assert r.best_fitness < 0.9
    assert r.panic_gens == 0


def test_antifragile_escapes():
    # panic mode は大きな sigma で谷を飛び越え大域最適へ
    r = run_ga(use_antifragile=True, seed=0)
    assert r.reached_global
    assert r.best_fitness > 0.95
    assert r.panic_gens > 0  # 停滞で panic が発火している


def test_compare_escape_rate_separation():
    r = compare(n_seeds=30)
    # baseline はほぼ捕まる、antifragile はほぼ脱出 (観測: 0% vs 100%)
    assert r.baseline_escape_rate < 0.2
    assert r.antifragile_escape_rate > 0.8
    assert r.antifragile_escape_rate > r.baseline_escape_rate
    assert r.antifragile_mean_best > r.baseline_mean_best
    # cost: panic 世代が発生している (タダではない)
    assert r.antifragile_mean_panic_gens > 0


def test_high_multiplier_helps_escape():
    # 探索増幅なし (multiplier=1) では panic でも sigma が増えず脱出しにくい
    weak = compare(n_seeds=15, exploration_multiplier=1.0)
    strong = compare(n_seeds=15, exploration_multiplier=8.0)
    assert strong.antifragile_escape_rate >= weak.antifragile_escape_rate
