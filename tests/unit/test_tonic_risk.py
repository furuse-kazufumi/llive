# SPDX-License-Identifier: Apache-2.0
"""Tests for COG-MESH-03 TonicRiskMonitor."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from llive.cognitive_mesh.tonic_risk import (
    RiskAlert,
    RiskModel,
    TonicRiskMonitor,
)


def _at(hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(2026, 5, 19, hour, minute, second)


# ---------------------------------------------------------------------------
# 登録
# ---------------------------------------------------------------------------


def test_register_model() -> None:
    monitor = TonicRiskMonitor()
    model = RiskModel(name="m1", score_fn=lambda s: 0.5)
    monitor.register(model)
    assert monitor.models() == [model]


def test_register_duplicate_rejected() -> None:
    monitor = TonicRiskMonitor()
    monitor.register(RiskModel(name="m1", score_fn=lambda s: 0.1))
    with pytest.raises(ValueError, match="already"):
        monitor.register(RiskModel(name="m1", score_fn=lambda s: 0.2))


# ---------------------------------------------------------------------------
# latest_scores
# ---------------------------------------------------------------------------


def test_latest_scores_returns_dict() -> None:
    monitor = TonicRiskMonitor()
    monitor.register(RiskModel(name="m1", score_fn=lambda s: 0.3))
    monitor.register(RiskModel(name="m2", score_fn=lambda s: 0.8))
    scores = monitor.latest_scores(state={})
    assert scores == {"m1": 0.3, "m2": 0.8}


# ---------------------------------------------------------------------------
# tick
# ---------------------------------------------------------------------------


def test_tick_no_alert_when_below_threshold() -> None:
    monitor = TonicRiskMonitor(interrupt_threshold=0.7)
    monitor.register(RiskModel(name="m", score_fn=lambda s: 0.3))
    assert monitor.tick(state={}) is None


def test_tick_emits_alert_when_above_threshold() -> None:
    received: list[RiskAlert] = []
    monitor = TonicRiskMonitor(
        interrupt_threshold=0.7, on_alert=lambda a: received.append(a)
    )
    monitor.register(RiskModel(name="hot", score_fn=lambda s: 0.9))
    alert = monitor.tick(state={"k": "v"}, now=_at(10))
    assert alert is not None
    assert alert.model_name == "hot"
    assert alert.score == 0.9
    assert alert.state_snapshot == {"k": "v"}
    assert received == [alert]


def test_tick_respects_weight() -> None:
    monitor = TonicRiskMonitor(interrupt_threshold=0.7)
    # raw 0.5 だが重み 2.0 で weighted=1.0 → alert
    monitor.register(RiskModel(name="m", score_fn=lambda s: 0.5, weight=2.0))
    alert = monitor.tick(state={})
    assert alert is not None
    assert alert.score == pytest.approx(1.0)


def test_tick_cooldown_blocks_repeat() -> None:
    monitor = TonicRiskMonitor(interrupt_threshold=0.5, cooldown=timedelta(seconds=10))
    monitor.register(RiskModel(name="m", score_fn=lambda s: 0.9))
    first = monitor.tick(state={}, now=_at(10, 0, 0))
    second = monitor.tick(state={}, now=_at(10, 0, 5))
    assert first is not None
    # cooldown 5 秒経過 (< 10 秒) → 抑止
    assert second is None
    # cooldown 11 秒経過 → 再発火
    third = monitor.tick(state={}, now=_at(10, 0, 11))
    assert third is not None


def test_tick_picks_highest_weighted_model() -> None:
    monitor = TonicRiskMonitor(interrupt_threshold=0.6)
    monitor.register(RiskModel(name="low", score_fn=lambda s: 0.4))
    monitor.register(RiskModel(name="high", score_fn=lambda s: 0.9))
    alert = monitor.tick(state={})
    assert alert is not None
    assert alert.model_name == "high"


def test_tick_state_snapshot_is_a_copy() -> None:
    monitor = TonicRiskMonitor(interrupt_threshold=0.5)
    monitor.register(RiskModel(name="m", score_fn=lambda s: 0.8))
    state = {"k": "v"}
    alert = monitor.tick(state=state)
    assert alert is not None
    state["k"] = "modified"
    # snapshot は変更されない
    assert alert.state_snapshot["k"] == "v"


def test_latest_alerts_history() -> None:
    monitor = TonicRiskMonitor(interrupt_threshold=0.5, cooldown=timedelta(seconds=0))
    monitor.register(RiskModel(name="m", score_fn=lambda s: 0.9))
    a1 = monitor.tick(state={"i": 1}, now=_at(10, 0, 0))
    a2 = monitor.tick(state={"i": 2}, now=_at(10, 0, 1))
    history = monitor.latest_alerts(n=10)
    assert history == [a1, a2]
