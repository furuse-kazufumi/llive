# SPDX-License-Identifier: Apache-2.0
"""予測検証メタゲート PoC: コスト削減 vs 有効候補誤却下の検証."""

from __future__ import annotations

from llive.evolution.predictive_gate_bench import GateModel, simulate, sweep


def test_gate_reduces_verify_calls():
    r = simulate(GateModel(invalid_rate=0.6, gate_recall=0.9), seed=0)
    assert r.verify_calls_gated < r.verify_calls_baseline
    assert r.cost_saving > 0.0


def test_saving_grows_with_invalid_rate():
    rows = sweep(seed=0)
    savings = [r.cost_saving for r in rows]  # invalid 0.3, 0.6, 0.9
    assert savings[0] < savings[1] < savings[2]
    assert savings[-1] > 0.7  # panic burst (90% invalid) で大きな削減


def test_lost_valid_tracks_false_reject():
    r = simulate(GateModel(invalid_rate=0.5, gate_false_reject=0.05, n_candidates=8000), seed=1)
    # 有効候補の誤却下率 ≈ gate_false_reject
    assert abs(r.lost_valid_rate - 0.05) < 0.02


def test_perfect_gate_no_lost_valid():
    r = simulate(GateModel(invalid_rate=0.6, gate_recall=1.0, gate_false_reject=0.0), seed=2)
    assert r.lost_valid_rate == 0.0
    assert r.cost_saving > 0.5  # 無効を全捕捉 → 重い verify は有効分のみ


def test_useless_gate_adds_overhead():
    # recall=0 (無効を一切捕まえない) → verify 呼出は減らず cheap 分だけ余計
    r = simulate(GateModel(invalid_rate=0.6, gate_recall=0.0, gate_false_reject=0.0), seed=3)
    assert r.verify_calls_gated == r.verify_calls_baseline
    assert r.cost_saving < 0.0  # 純粋なオーバーヘッド
