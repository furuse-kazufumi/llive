# SPDX-License-Identifier: Apache-2.0
"""IdleDetector の単体テスト."""

from __future__ import annotations

from llive.idle.detector import IdleDetector


def test_default_provider_returns_non_idle() -> None:
    # 未実装環境では idle=False を返す
    det = IdleDetector(threshold_s=10.0)
    s = det.status()
    assert s.idle is False
    assert s.seconds_since_last_input is None
    assert s.threshold_s == 10.0


def test_manual_provider_below_threshold() -> None:
    det = IdleDetector(threshold_s=60.0, last_input_provider=lambda: 30.0)
    s = det.status()
    assert s.idle is False
    assert s.seconds_since_last_input == 30.0


def test_manual_provider_above_threshold() -> None:
    det = IdleDetector(threshold_s=60.0, last_input_provider=lambda: 120.0)
    s = det.status()
    assert s.idle is True
    assert s.seconds_since_last_input == 120.0
