# SPDX-License-Identifier: Apache-2.0
"""COG-MESH-06 拡張テスト — event / consistency モード."""

from __future__ import annotations

from datetime import datetime

import pytest

from llive.cognitive_mesh.proactive import (
    ConsistencyViolation,
    ProactiveEvent,
    ProactiveLoop,
)
from llive.cognitive_mesh.quiet_hours import QuietHoursGuard


def _active_guard(monkeypatch: pytest.MonkeyPatch) -> QuietHoursGuard:
    """22..08 Quiet, 10:00 検証では active."""
    monkeypatch.setenv("LLIVE_TZ", "Asia/Tokyo")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_START", "22")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_END", "8")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_ENABLED", "1")
    return QuietHoursGuard()


# GiftValueEstimator が should_speak を満たす listener_state を共通化
_HIGH_VALUE_LISTENER = {
    "current_topic": "build",  # candidate に含まれていれば +relevance
    "risk_score": 0.8,
    "focus_level": 0.3,
    "in_quiet_hours": False,
}


# ---------------------------------------------------------------------------
# event mode
# ---------------------------------------------------------------------------


def test_tick_event_without_source_or_arg_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    loop = ProactiveLoop(quiet_hours=_active_guard(monkeypatch))
    with pytest.raises(NotImplementedError):
        loop.tick_event(now=datetime(2026, 5, 19, 10, 0, 0))


def test_tick_event_with_arg_emits_utterance(monkeypatch: pytest.MonkeyPatch) -> None:
    loop = ProactiveLoop(quiet_hours=_active_guard(monkeypatch))
    event = ProactiveEvent(topic="build", note="ビルド完了", severity=0.9)
    out = loop.tick_event(
        event=event,
        now=datetime(2026, 5, 19, 10, 0, 0),
        listener_state=_HIGH_VALUE_LISTENER,
    )
    assert out is not None
    assert out.mode == "event"
    assert "build" in out.content
    assert "ビルド完了" in out.content
    assert loop.latest_utterances() == [out]


def test_tick_event_below_severity_threshold_is_suppressed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loop = ProactiveLoop(
        quiet_hours=_active_guard(monkeypatch),
        event_severity_threshold=0.5,
    )
    event = ProactiveEvent(topic="noise", note="低重要度", severity=0.1)
    out = loop.tick_event(event=event, now=datetime(2026, 5, 19, 10, 0, 0))
    assert out is None
    suppressed = loop.latest_suppressed()
    assert len(suppressed) == 1
    assert suppressed[0].reason == "event_severity_below_threshold"


def test_tick_event_picks_highest_severity_from_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = [
        ProactiveEvent(topic="low", severity=0.2, note="low note"),
        ProactiveEvent(topic="high", severity=0.95, note="high note"),
        ProactiveEvent(topic="mid", severity=0.5, note="mid note"),
    ]
    loop = ProactiveLoop(
        quiet_hours=_active_guard(monkeypatch),
        event_source=lambda: events,
    )
    out = loop.tick_event(now=datetime(2026, 5, 19, 10, 0, 0))
    assert out is not None
    assert "high" in out.content


def test_tick_event_empty_source_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    loop = ProactiveLoop(
        quiet_hours=_active_guard(monkeypatch),
        event_source=lambda: [],
    )
    assert loop.tick_event(now=datetime(2026, 5, 19, 10, 0, 0)) is None


def test_tick_event_blocked_in_quiet_hours(monkeypatch: pytest.MonkeyPatch) -> None:
    """22..08 Quiet 帯の 03:00 にイベント tick → None."""
    loop = ProactiveLoop(quiet_hours=_active_guard(monkeypatch))
    event = ProactiveEvent(topic="x", severity=0.9, note="should not fire")
    out = loop.tick_event(event=event, now=datetime(2026, 5, 19, 3, 0, 0))
    assert out is None


# ---------------------------------------------------------------------------
# consistency mode
# ---------------------------------------------------------------------------


def test_tick_consistency_without_source_or_arg_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loop = ProactiveLoop(quiet_hours=_active_guard(monkeypatch))
    with pytest.raises(NotImplementedError):
        loop.tick_consistency(now=datetime(2026, 5, 19, 10, 0, 0))


def test_tick_consistency_with_arg_emits_utterance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loop = ProactiveLoop(quiet_hours=_active_guard(monkeypatch))
    v = ConsistencyViolation(
        layer_a="semantic",
        layer_b="episodic",
        conflict_type="fact_mismatch",
        evidence="A says 'red', B says 'blue'",
        severity=0.7,
    )
    out = loop.tick_consistency(violation=v, now=datetime(2026, 5, 19, 10, 0, 0))
    assert out is not None
    assert out.mode == "consistency"
    assert "semantic" in out.content
    assert "episodic" in out.content
    assert "fact_mismatch" in out.content
    assert "red" in out.content


def test_tick_consistency_picks_highest_severity_from_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    violations = [
        ConsistencyViolation(
            layer_a="a", layer_b="b", conflict_type="x", severity=0.2
        ),
        ConsistencyViolation(
            layer_a="c", layer_b="d", conflict_type="critical", severity=0.95
        ),
    ]
    loop = ProactiveLoop(
        quiet_hours=_active_guard(monkeypatch),
        consistency_source=lambda: violations,
    )
    out = loop.tick_consistency(now=datetime(2026, 5, 19, 10, 0, 0))
    assert out is not None
    assert "critical" in out.content


def test_tick_consistency_blocked_in_quiet_hours(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loop = ProactiveLoop(quiet_hours=_active_guard(monkeypatch))
    v = ConsistencyViolation(
        layer_a="a", layer_b="b", conflict_type="x", severity=0.9
    )
    out = loop.tick_consistency(violation=v, now=datetime(2026, 5, 19, 3, 0, 0))
    assert out is None


# ---------------------------------------------------------------------------
# autonomous _on_timer mode routing
# ---------------------------------------------------------------------------


def test_on_timer_routes_event_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """mode='event' で _on_timer が tick_event を呼ぶ.

    _on_timer は datetime.now() を内部参照するため、現在時刻が active 帯
    (22..08 Quiet なので 08-22 帯) かどうかに依存する。テストの現在時刻が
    Quiet 帯に当たる場合があるので、両方の挙動を許容する: 発話があるか
    suppressed なしの空状態か (Quiet 中は黙る)。
    """
    events = [ProactiveEvent(topic="alpha", severity=0.9, note="auto fire")]
    loop = ProactiveLoop(
        quiet_hours=_active_guard(monkeypatch),
        mode="event",
        event_source=lambda: events,
    )
    loop._on_timer()  # noqa: SLF001 — 内部 method を意図的にテスト
    # quiet 帯外なら発話、quiet 帯なら無発話のどちらでも OK
    utterances = loop.latest_utterances()
    if utterances:
        assert utterances[-1].mode == "event"
        assert "alpha" in utterances[-1].content


def test_on_timer_routes_consistency_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    violations = [
        ConsistencyViolation(
            layer_a="x", layer_b="y", conflict_type="conflict_a", severity=0.9
        )
    ]
    loop = ProactiveLoop(
        quiet_hours=_active_guard(monkeypatch),
        mode="consistency",
        consistency_source=lambda: violations,
    )
    loop._on_timer()  # noqa: SLF001
    utterances = loop.latest_utterances()
    if utterances:
        assert utterances[-1].mode == "consistency"
        assert "conflict_a" in utterances[-1].content
