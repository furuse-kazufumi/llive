# SPDX-License-Identifier: Apache-2.0
"""Tests for COG-MESH-04 IdleTrainingScheduler.

requirements_v0.8_cognitive_mesh.md §3 COG-MESH-04 の API 凍結。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from llive.cognitive_mesh.idle_training import (
    IdleTrainingScheduler,
    InfoSource,
)
from llive.cognitive_mesh.quiet_hours import QuietHoursGuard

JST = timezone(timedelta(hours=9))


def _at(hour: int) -> datetime:
    return datetime(2026, 5, 18, hour, 0, tzinfo=JST)


def _make_guard(monkeypatch: pytest.MonkeyPatch) -> QuietHoursGuard:
    monkeypatch.setenv("LLIVE_TZ", "Asia/Tokyo")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_START", "22")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_END", "8")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_ENABLED", "1")
    return QuietHoursGuard()


# ---------------------------------------------------------------------------
# 依存
# ---------------------------------------------------------------------------


def test_requires_quiet_hours_guard() -> None:
    with pytest.raises(TypeError, match="QuietHoursGuard"):
        IdleTrainingScheduler(quiet_hours=None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# source 登録
# ---------------------------------------------------------------------------


def test_register_source(monkeypatch: pytest.MonkeyPatch) -> None:
    guard = _make_guard(monkeypatch)
    sched = IdleTrainingScheduler(quiet_hours=guard)
    src = InfoSource(name="rss-arxiv", fetch=lambda: "payload")
    sched.register(src)
    assert sched.sources() == [src]


def test_register_duplicate_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    guard = _make_guard(monkeypatch)
    sched = IdleTrainingScheduler(quiet_hours=guard)
    src = InfoSource(name="x", fetch=lambda: 1)
    sched.register(src)
    with pytest.raises(ValueError, match="already registered"):
        sched.register(src)


# ---------------------------------------------------------------------------
# should_ingest gate
# ---------------------------------------------------------------------------


def test_no_ingest_during_quiet_hours(monkeypatch: pytest.MonkeyPatch) -> None:
    guard = _make_guard(monkeypatch)
    sched = IdleTrainingScheduler(quiet_hours=guard)
    sched.register(InfoSource(name="s", fetch=lambda: "x"))
    assert sched.should_ingest(now=_at(2)) is False


def test_can_ingest_during_active(monkeypatch: pytest.MonkeyPatch) -> None:
    guard = _make_guard(monkeypatch)
    sched = IdleTrainingScheduler(quiet_hours=guard)
    sched.register(InfoSource(name="s", fetch=lambda: "x"))
    assert sched.should_ingest(now=_at(10)) is True


def test_no_ingest_when_no_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    guard = _make_guard(monkeypatch)
    sched = IdleTrainingScheduler(quiet_hours=guard)
    assert sched.should_ingest(now=_at(10)) is False


def test_pause_blocks_ingest(monkeypatch: pytest.MonkeyPatch) -> None:
    guard = _make_guard(monkeypatch)
    sched = IdleTrainingScheduler(quiet_hours=guard)
    sched.register(InfoSource(name="s", fetch=lambda: 1))
    sched.pause()
    assert sched.should_ingest(now=_at(10)) is False
    sched.resume()
    assert sched.should_ingest(now=_at(10)) is True


# ---------------------------------------------------------------------------
# tick 動作
# ---------------------------------------------------------------------------


def test_tick_returns_ingest_event(monkeypatch: pytest.MonkeyPatch) -> None:
    guard = _make_guard(monkeypatch)
    sched = IdleTrainingScheduler(quiet_hours=guard)
    sched.register(InfoSource(name="rss", fetch=lambda: {"title": "x"}))
    event = sched.tick(now=_at(10))
    assert event is not None
    assert event.source_name == "rss"
    assert event.payload == {"title": "x"}
    assert sched.latest_events(n=5) == [event]


def test_tick_during_quiet_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    guard = _make_guard(monkeypatch)
    sched = IdleTrainingScheduler(quiet_hours=guard)
    sched.register(InfoSource(name="rss", fetch=lambda: "x"))
    assert sched.tick(now=_at(2)) is None


def test_tick_respects_idle_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """直近 ingest から idle_threshold_seconds 以内なら待つ."""
    guard = _make_guard(monkeypatch)
    sched = IdleTrainingScheduler(quiet_hours=guard, idle_threshold_seconds=60)
    sched.register(InfoSource(name="rss", fetch=lambda: "x"))
    first = sched.tick(now=_at(10))
    assert first is not None
    # 30 秒後は待ち
    later = sched.tick(now=_at(10) + timedelta(seconds=30))
    assert later is None
    # 61 秒後は再 ingest 可能 (ただし source cooldown 30 分内なので skip)
    # cooldown 短い source を使った場合
    sched2 = IdleTrainingScheduler(quiet_hours=guard, idle_threshold_seconds=60)
    sched2.register(InfoSource(name="r", fetch=lambda: 1, cooldown=timedelta(seconds=10)))
    e1 = sched2.tick(now=_at(10))
    e2 = sched2.tick(now=_at(10) + timedelta(seconds=90))
    assert e1 is not None
    assert e2 is not None


def test_tick_with_cooldown_skips_recent_source(monkeypatch: pytest.MonkeyPatch) -> None:
    """source cooldown 内のソースは skip."""
    guard = _make_guard(monkeypatch)
    sched = IdleTrainingScheduler(quiet_hours=guard, idle_threshold_seconds=10)
    sched.register(
        InfoSource(name="rss", fetch=lambda: "x", cooldown=timedelta(hours=1))
    )
    first = sched.tick(now=_at(10))
    assert first is not None
    # 30 分後だが source cooldown は 1 時間 → None
    second = sched.tick(now=_at(10) + timedelta(minutes=30))
    assert second is None


def test_tick_round_robins_between_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    """複数ソースのとき、最も古い ingest のものから順に走る."""
    guard = _make_guard(monkeypatch)
    sched = IdleTrainingScheduler(quiet_hours=guard, idle_threshold_seconds=1)
    sched.register(
        InfoSource(name="a", fetch=lambda: "A", cooldown=timedelta(seconds=1))
    )
    sched.register(
        InfoSource(name="b", fetch=lambda: "B", cooldown=timedelta(seconds=1))
    )
    e1 = sched.tick(now=_at(10))
    e2 = sched.tick(now=_at(10) + timedelta(seconds=5))
    e3 = sched.tick(now=_at(10) + timedelta(seconds=10))
    names = {e1.source_name, e2.source_name, e3.source_name}
    # 3 tick で a / b 両方が走る (順序は実装依存)
    assert {"a", "b"} <= names
