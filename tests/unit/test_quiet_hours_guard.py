# SPDX-License-Identifier: Apache-2.0
"""Tests for QuietHoursGuard (COG-MESH-07).

requirements_v0.8_cognitive_mesh.md §3 / §6 / §10 で予告した先行配備テスト。
実装より先に test を置くことで仕様を凍結する (feedback_response_timing
の 70 点運用)。

実装は `llive.cognitive_mesh.quiet_hours.QuietHoursGuard` (TBD) に着地予定。
test は実装パスができるまで `pytest.importorskip` で skip される。

シナリオ:
1. JST 02:00 (Quiet Hours 中) → in_quiet_hours() == True
2. JST 10:00 (Active 中) → in_quiet_hours() == False
3. env LLIVE_QUIET_HOURS_ENABLED=0 → 常に False
4. env LLIVE_QUIET_HOURS_START/END を 0/24 → 常に True
5. env LLIVE_TZ 欠落 → fail-closed (常に True)
6. allow("risk_alert") は Quiet Hours 中でも True (Risk Score 高は例外)
7. allow("proactive") は Quiet Hours 中は False
8. next_active_window() は Quiet Hours 中なら次の 08:00 を返す
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

import os

import pytest

# 先行配備: 実装パスが無いうちは skip
quiet_hours_module = pytest.importorskip(
    "llive.cognitive_mesh.quiet_hours",
    reason="COG-MESH-07 QuietHoursGuard は Phase 5 で実装予定 (requirements_v0.8)",
)


JST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _at(hour: int, minute: int = 0) -> datetime:
    """JST の指定時刻を返す (日付は固定 2026-05-18)."""
    return datetime(2026, 5, 18, hour, minute, tzinfo=JST)


def _make_guard(env: dict[str, str] | None = None) -> Any:
    """env を上書きして QuietHoursGuard を生成する."""
    if env is not None:
        for key, value in env.items():
            os.environ[key] = value
    return quiet_hours_module.QuietHoursGuard()


# ---------------------------------------------------------------------------
# 基本判定
# ---------------------------------------------------------------------------


def test_in_quiet_hours_at_night_jst(monkeypatch: pytest.MonkeyPatch) -> None:
    """JST 02:00 は Quiet Hours 中."""
    monkeypatch.setenv("LLIVE_TZ", "Asia/Tokyo")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_START", "22")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_END", "8")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_ENABLED", "1")
    guard = _make_guard()
    assert guard.in_quiet_hours(now=_at(2)) is True


def test_in_quiet_hours_at_day_jst(monkeypatch: pytest.MonkeyPatch) -> None:
    """JST 10:00 は Active."""
    monkeypatch.setenv("LLIVE_TZ", "Asia/Tokyo")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_START", "22")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_END", "8")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_ENABLED", "1")
    guard = _make_guard()
    assert guard.in_quiet_hours(now=_at(10)) is False


def test_quiet_hours_disabled_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLIVE_QUIET_HOURS_ENABLED=0 のときは常に False."""
    monkeypatch.setenv("LLIVE_TZ", "Asia/Tokyo")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_ENABLED", "0")
    guard = _make_guard()
    assert guard.in_quiet_hours(now=_at(2)) is False
    assert guard.in_quiet_hours(now=_at(10)) is False


def test_all_day_quiet_when_start_eq_end(monkeypatch: pytest.MonkeyPatch) -> None:
    """START=END=0 のとき (24h Quiet Hours 表現) は常に True."""
    monkeypatch.setenv("LLIVE_TZ", "Asia/Tokyo")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_START", "0")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_END", "0")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_ENABLED", "1")
    guard = _make_guard()
    # 全時刻で True
    for h in range(0, 24, 3):
        assert guard.in_quiet_hours(now=_at(h)) is True


# ---------------------------------------------------------------------------
# fail-closed
# ---------------------------------------------------------------------------


def test_tz_missing_is_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLIVE_TZ 欠落時は常に Quiet Hours 中扱い (fail-closed)."""
    monkeypatch.delenv("LLIVE_TZ", raising=False)
    monkeypatch.setenv("LLIVE_QUIET_HOURS_ENABLED", "1")
    guard = _make_guard()
    # 真昼 10:00 でも fail-closed なので True
    assert guard.in_quiet_hours(now=_at(10)) is True


def test_env_partial_is_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """START だけあって END が無い等の不完全 env は fail-closed."""
    monkeypatch.setenv("LLIVE_TZ", "Asia/Tokyo")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_START", "22")
    monkeypatch.delenv("LLIVE_QUIET_HOURS_END", raising=False)
    monkeypatch.setenv("LLIVE_QUIET_HOURS_ENABLED", "1")
    guard = _make_guard()
    assert guard.in_quiet_hours(now=_at(10)) is True


# ---------------------------------------------------------------------------
# allow() カテゴリ別
# ---------------------------------------------------------------------------


def test_allow_proactive_blocked_in_quiet_hours(monkeypatch: pytest.MonkeyPatch) -> None:
    """proactive 発話は Quiet Hours 中に拒否される."""
    monkeypatch.setenv("LLIVE_TZ", "Asia/Tokyo")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_START", "22")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_END", "8")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_ENABLED", "1")
    guard = _make_guard()
    # 2:00 = Quiet Hours
    assert guard.allow("proactive", now=_at(2)) is False
    # 10:00 = Active
    assert guard.allow("proactive", now=_at(10)) is True


def test_allow_risk_alert_passes_in_quiet_hours(monkeypatch: pytest.MonkeyPatch) -> None:
    """risk_alert は Quiet Hours 中でも許可される (例外カテゴリ)."""
    monkeypatch.setenv("LLIVE_TZ", "Asia/Tokyo")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_START", "22")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_END", "8")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_ENABLED", "1")
    guard = _make_guard()
    assert guard.allow("risk_alert", now=_at(2)) is True
    assert guard.allow("risk_alert", now=_at(10)) is True


def test_allow_ingest_blocked_in_quiet_hours(monkeypatch: pytest.MonkeyPatch) -> None:
    """idle ingest は Quiet Hours 中に抑止."""
    monkeypatch.setenv("LLIVE_TZ", "Asia/Tokyo")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_START", "22")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_END", "8")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_ENABLED", "1")
    guard = _make_guard()
    assert guard.allow("ingest", now=_at(2)) is False
    assert guard.allow("ingest", now=_at(10)) is True


# ---------------------------------------------------------------------------
# next_active_window()
# ---------------------------------------------------------------------------


def test_next_active_window_during_quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    """Quiet Hours 中なら次の active window は (END, NEXT_START) を返す."""
    monkeypatch.setenv("LLIVE_TZ", "Asia/Tokyo")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_START", "22")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_END", "8")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_ENABLED", "1")
    guard = _make_guard()
    start, end = guard.next_active_window(now=_at(2))
    assert start.hour == 8
    assert end.hour == 22
    assert (end - start) == timedelta(hours=14)


def test_next_active_window_during_active(monkeypatch: pytest.MonkeyPatch) -> None:
    """Active 中なら次の active window は今すぐから次の Quiet 開始まで."""
    monkeypatch.setenv("LLIVE_TZ", "Asia/Tokyo")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_START", "22")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_END", "8")
    monkeypatch.setenv("LLIVE_QUIET_HOURS_ENABLED", "1")
    guard = _make_guard()
    start, end = guard.next_active_window(now=_at(10))
    assert start == _at(10)
    assert end.hour == 22
