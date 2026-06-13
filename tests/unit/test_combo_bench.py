# SPDX-License-Identifier: Apache-2.0
"""組み合わせ PoC (llive): Combo-A / Combo-C の synergy 検証."""

from __future__ import annotations

from llive.evolution.combo_bench import combo_a, combo_c


def test_combo_a_escape_preserved():
    # antifragile の脱出は並行度に依らず維持される
    r = combo_a(parallel_width=4, seeds=20)
    assert r.escape_rate > 0.8
    assert r.mean_gens_to_escape is not None


def test_combo_a_walltime_speedup_scales_with_width():
    w1 = combo_a(parallel_width=1, seeds=10)
    w2 = combo_a(parallel_width=2, seeds=10)
    w8 = combo_a(parallel_width=8, seeds=10)
    assert w1.walltime_speedup < w2.walltime_speedup < w8.walltime_speedup
    assert w8.walltime_speedup > 5.0   # W=8 で大きな wall-clock 短縮
    assert w1.walltime_speedup < 1.0   # W=1 は mesh overhead 分だけ純損 (honest)


def test_combo_c_panic_amplifies_gate():
    c = combo_c(seeds=20)
    assert c.mean_panic_gens > 0
    # panic burst (高 invalid) はゲートで通常区間より大きく削減できる
    assert c.panic_only_saving > c.baseline_only_saving
    # run 全体でも大きな verifier コスト削減 (panic が支配的)
    assert c.combined_cost_saving > 0.5


def test_combo_c_savings_between_regimes():
    c = combo_c(seeds=15)
    # 全体削減は通常区間と panic 区間の間に挟まれる
    assert c.baseline_only_saving <= c.combined_cost_saving <= c.panic_only_saving
