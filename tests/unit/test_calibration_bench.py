# SPDX-License-Identifier: Apache-2.0
"""較正 + 安定性 評価 PoC の検証."""

from __future__ import annotations

from llive.perf.calibration_bench import (
    evaluate_calibration,
    stability_antifragile,
)


def test_calibrated_estimator_low_ece_zero_gap():
    r = evaluate_calibration(bias=0.0, seed=0)
    assert r.ece < 0.06
    assert abs(r.gap) < 0.02


def test_overconfident_inflates_claimed():
    r = evaluate_calibration(bias=0.2, seed=0)
    # 主張精度 > 実精度 = 速度 PoC を過大評価
    assert r.gap > 0.15
    assert r.claimed_accuracy > r.realized_accuracy
    assert r.ece > 0.1


def test_underconfident_negative_gap():
    r = evaluate_calibration(bias=-0.1, seed=0)
    assert r.gap < 0.0


def test_brier_and_ece_bounded():
    for b in (-0.1, 0.0, 0.1, 0.2):
        r = evaluate_calibration(bias=b, seed=1)
        assert 0.0 <= r.ece <= 1.0
        assert 0.0 <= r.brier <= 1.0


def test_antifragile_escape_is_stable_across_seeds():
    s = stability_antifragile(n_batches=6, batch_size=12)
    # 100% 脱出が seed 運でないこと (std≈0, min 高)
    assert s.mean > 0.9
    assert s.std < 0.1
    assert s.min >= 0.8
