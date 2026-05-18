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


def _active_quiet_hours() -> QuietHoursGuard:
    """常に active な (発話可能な) QuietHoursGuard."""
    return QuietHoursGuard(
        timezone="Asia/Tokyo",
        quiet_start_hour=22,
        quiet_end_hour=8,
        enabled=False,
    )


def _blocked_quiet_hours() -> QuietHoursGuard:
    """常に quiet な (発話禁止) QuietHoursGuard.

    enabled=True かつ quiet 帯を全 24h カバー (start_hour=0, end_hour=0 のラップで全帯).
    実装の境界条件次第で別の方法を試す。
    """
    # 03 時固定で quiet 帯 (02-08) を指定し、tick の now を 03:00 で渡す。
    return QuietHoursGuard(
        timezone="Asia/Tokyo",
        quiet_start_hour=2,
        quiet_end_hour=8,
        enabled=True,
    )


# ---------------------------------------------------------------------------
# event mode
# ---------------------------------------------------------------------------


def test_tick_event_without_source_or_arg_raises() -> None:
    loop = ProactiveLoop(quiet_hours=_active_quiet_hours())
    with pytest.raises(NotImplementedError):
        loop.tick_event()


def test_tick_event_with_arg_emits_utterance() -> None:
    loop = ProactiveLoop(quiet_hours=_active_quiet_hours())
    event = ProactiveEvent(topic="build", note="ビルド完了", severity=0.9)
    out = loop.tick_event(event=event, now=datetime(2026, 5, 19, 10, 0, 0))
    assert out is not None
    assert out.mode == "event"
    assert "build" in out.content
    assert "ビルド完了" in out.content
    assert loop.latest_utterances() == [out]


def test_tick_event_below_severity_threshold_is_suppressed() -> None:
    loop = ProactiveLoop(
        quiet_hours=_active_quiet_hours(),
        event_severity_threshold=0.5,
    )
    event = ProactiveEvent(topic="noise", note="低重要度", severity=0.1)
    out = loop.tick_event(event=event, now=datetime(2026, 5, 19, 10, 0, 0))
    assert out is None
    suppressed = loop.latest_suppressed()
    assert len(suppressed) == 1
    assert suppressed[0].reason == "event_severity_below_threshold"


def test_tick_event_picks_highest_severity_from_source() -> None:
    events = [
        ProactiveEvent(topic="low", severity=0.2, note="low note"),
        ProactiveEvent(topic="high", severity=0.95, note="high note"),
        ProactiveEvent(topic="mid", severity=0.5, note="mid note"),
    ]
    loop = ProactiveLoop(
        quiet_hours=_active_quiet_hours(),
        event_source=lambda: events,
    )
    out = loop.tick_event(now=datetime(2026, 5, 19, 10, 0, 0))
    assert out is not None
    assert "high" in out.content


def test_tick_event_empty_source_returns_none() -> None:
    loop = ProactiveLoop(
        quiet_hours=_active_quiet_hours(),
        event_source=lambda: [],
    )
    assert loop.tick_event(now=datetime(2026, 5, 19, 10, 0, 0)) is None


def test_tick_event_blocked_in_quiet_hours() -> None:
    loop = ProactiveLoop(quiet_hours=_blocked_quiet_hours())
    event = ProactiveEvent(topic="x", severity=0.9, note="should not fire")
    # 03:00 は quiet 帯
    out = loop.tick_event(event=event, now=datetime(2026, 5, 19, 3, 0, 0))
    assert out is None


# ---------------------------------------------------------------------------
# consistency mode
# ---------------------------------------------------------------------------


def test_tick_consistency_without_source_or_arg_raises() -> None:
    loop = ProactiveLoop(quiet_hours=_active_quiet_hours())
    with pytest.raises(NotImplementedError):
        loop.tick_consistency()


def test_tick_consistency_with_arg_emits_utterance() -> None:
    loop = ProactiveLoop(quiet_hours=_active_quiet_hours())
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


def test_tick_consistency_picks_highest_severity_from_source() -> None:
    violations = [
        ConsistencyViolation(
            layer_a="a", layer_b="b", conflict_type="x", severity=0.2
        ),
        ConsistencyViolation(
            layer_a="c", layer_b="d", conflict_type="critical", severity=0.95
        ),
    ]
    loop = ProactiveLoop(
        quiet_hours=_active_quiet_hours(),
        consistency_source=lambda: violations,
    )
    out = loop.tick_consistency(now=datetime(2026, 5, 19, 10, 0, 0))
    assert out is not None
    assert "critical" in out.content


def test_tick_consistency_blocked_in_quiet_hours() -> None:
    loop = ProactiveLoop(quiet_hours=_blocked_quiet_hours())
    v = ConsistencyViolation(
        layer_a="a", layer_b="b", conflict_type="x", severity=0.9
    )
    out = loop.tick_consistency(violation=v, now=datetime(2026, 5, 19, 3, 0, 0))
    assert out is None


# ---------------------------------------------------------------------------
# autonomous _on_timer mode routing
# ---------------------------------------------------------------------------


def test_on_timer_routes_event_mode() -> None:
    """mode='event' で _on_timer が tick_event を呼ぶ."""
    events = [ProactiveEvent(topic="alpha", severity=0.9, note="auto fire")]
    loop = ProactiveLoop(
        quiet_hours=_active_quiet_hours(),
        mode="event",
        event_source=lambda: events,
    )
    # _on_timer は内部 method だが、ここで直接呼んで分岐をテスト
    loop._on_timer()  # noqa: SLF001
    utterances = loop.latest_utterances()
    assert len(utterances) == 1
    assert utterances[0].mode == "event"


def test_on_timer_routes_consistency_mode() -> None:
    violations = [
        ConsistencyViolation(
            layer_a="x", layer_b="y", conflict_type="conflict_a", severity=0.9
        )
    ]
    loop = ProactiveLoop(
        quiet_hours=_active_quiet_hours(),
        mode="consistency",
        consistency_source=lambda: violations,
    )
    loop._on_timer()  # noqa: SLF001
    utterances = loop.latest_utterances()
    assert len(utterances) == 1
    assert utterances[0].mode == "consistency"
