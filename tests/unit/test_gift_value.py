# SPDX-License-Identifier: Apache-2.0
"""Tests for GiftValueEstimator (COG-MESH-05).

requirements_v0.8_cognitive_mesh.md §3 COG-MESH-05 の API 凍結。

シナリオ:
1. 完全新規 + relevance あり + risk 高 → should_speak True
2. リスニング側が Quiet Hours 中 → cost 高で should_speak False
3. 同一発話を cooldown 内に再評価 → novelty 0、aggregate 下落
4. relevance が listener_state に無いとき → 0.5 (neutral)
5. commit() 後の novelty 反映
6. cooldown 超過後は novelty 復活
"""

from __future__ import annotations

from datetime import datetime, timedelta

from llive.cognitive_mesh.gift_value import (
    DEFAULT_THRESHOLD,
    GiftValue,
    GiftValueEstimator,
)


def test_high_value_utterance_should_speak() -> None:
    estimator = GiftValueEstimator()
    gv = estimator.estimate(
        candidate_utterance="重要な進捗報告: build が完了しました",
        listener_state={
            "current_topic": "build",
            "risk_score": 0.8,
            "focus_level": 0.3,
            "in_quiet_hours": False,
        },
    )
    assert gv.should_speak is True
    assert gv.aggregate >= DEFAULT_THRESHOLD


def test_quiet_hours_blocks_via_cost() -> None:
    estimator = GiftValueEstimator()
    gv = estimator.estimate(
        candidate_utterance="軽い雑談です",
        listener_state={
            "current_topic": "雑談",
            "risk_score": 0.2,
            "focus_level": 0.3,
            "in_quiet_hours": True,
        },
    )
    # Quiet Hours 中は cost が 0.9 以上、aggregate 下落で 黙る
    assert gv.cost_to_listener >= 0.9
    assert gv.should_speak is False


def test_repeat_utterance_drops_novelty() -> None:
    estimator = GiftValueEstimator(cooldown=timedelta(minutes=30))
    now = datetime(2026, 5, 19, 0, 0)
    first = estimator.estimate("同じ発話", now=now)
    estimator.commit("同じ発話", now=now)
    later = estimator.estimate("同じ発話", now=now + timedelta(minutes=5))
    assert first.novelty == 1.0
    assert later.novelty == 0.0
    assert later.aggregate < first.aggregate


def test_cooldown_expiry_restores_novelty() -> None:
    estimator = GiftValueEstimator(cooldown=timedelta(minutes=10))
    now = datetime(2026, 5, 19, 0, 0)
    estimator.commit("発話 A", now=now)
    after_cooldown = estimator.estimate("発話 A", now=now + timedelta(minutes=15))
    assert after_cooldown.novelty == 1.0


def test_relevance_neutral_when_topic_missing() -> None:
    estimator = GiftValueEstimator()
    gv = estimator.estimate("発話", listener_state={"risk_score": 0.3})
    assert gv.relevance == 0.5


def test_should_speak_threshold_property() -> None:
    """GiftValue.should_speak は DEFAULT_THRESHOLD (0.6) で gate."""
    high = GiftValue(novelty=1.0, relevance=1.0, risk_avoidance=1.0,
                    cost_to_listener=0.0, aggregate=0.9)
    low = GiftValue(novelty=0.5, relevance=0.5, risk_avoidance=0.5,
                   cost_to_listener=0.5, aggregate=0.5)
    boundary = GiftValue(novelty=0.6, relevance=0.6, risk_avoidance=0.6,
                        cost_to_listener=0.6, aggregate=0.6)
    assert high.should_speak is True
    assert low.should_speak is False
    assert boundary.should_speak is True  # >= 0.6 で True


def test_weighted_aggregate_in_range() -> None:
    estimator = GiftValueEstimator()
    gv = estimator.estimate(
        "test",
        listener_state={"current_topic": "test", "risk_score": 0.5, "focus_level": 0.5},
    )
    assert 0.0 <= gv.aggregate <= 1.0
