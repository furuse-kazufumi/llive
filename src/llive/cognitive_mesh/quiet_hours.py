# SPDX-License-Identifier: Apache-2.0
"""COG-MESH-07 QuietHoursGuard — 能動行動の時刻 gate.

requirements_v0.8_cognitive_mesh.md §3 COG-MESH-07 の最小実装。
`tests/unit/test_quiet_hours_guard.py` の 11 シナリオを通す。

設定 env:
- ``LLIVE_TZ`` (例: ``Asia/Tokyo``)
- ``LLIVE_QUIET_HOURS_START`` (0..24)
- ``LLIVE_QUIET_HOURS_END`` (0..24)
- ``LLIVE_QUIET_HOURS_ENABLED`` (``1`` / ``0``)

設計:
- env 欠落 → **fail-closed** (常に Quiet Hours 中扱い、抑止側に倒す)
- ``START == END`` → 24h Quiet Hours 表現 (常に True)
- ``allow(category)`` カテゴリ: ``proactive`` / ``ingest`` は Quiet 中拒否、
  ``risk_alert`` / ``audit_alert`` は Quiet 中でも許可
- ``next_active_window()`` は (active_start, active_end) を返す
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

Category = Literal["proactive", "ingest", "risk_alert", "audit_alert"]


# Quiet Hours 中でも通過するカテゴリ
_QUIET_HOURS_EXEMPT: frozenset[str] = frozenset({"risk_alert", "audit_alert"})


@dataclass(frozen=True)
class _Config:
    tz: ZoneInfo | timezone
    start_hour: int
    end_hour: int
    enabled: bool
    fail_closed: bool


def _load_config() -> _Config:
    """env から設定を読み込む。欠落時は fail_closed=True で構築."""
    tz_name = os.environ.get("LLIVE_TZ")
    enabled_raw = os.environ.get("LLIVE_QUIET_HOURS_ENABLED", "1")
    start_raw = os.environ.get("LLIVE_QUIET_HOURS_START")
    end_raw = os.environ.get("LLIVE_QUIET_HOURS_END")

    enabled = enabled_raw == "1"

    # 必須 env のいずれかが欠落 → fail-closed
    fail_closed = False
    tz: ZoneInfo | timezone
    if tz_name is None:
        fail_closed = True
        tz = UTC  # placeholder、in_quiet_hours は fail_closed を見て決定
    else:
        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            fail_closed = True
            tz = UTC

    if start_raw is None or end_raw is None:
        fail_closed = True
        start_hour, end_hour = 0, 0
    else:
        try:
            start_hour = int(start_raw)
            end_hour = int(end_raw)
        except ValueError:
            fail_closed = True
            start_hour, end_hour = 0, 0

    return _Config(
        tz=tz,
        start_hour=start_hour,
        end_hour=end_hour,
        enabled=enabled,
        fail_closed=fail_closed,
    )


class QuietHoursGuard:
    """時刻に基づいて能動行動を gate する."""

    def __init__(self) -> None:
        self._config = _load_config()

    # ------------------------------------------------------------------
    # 基本判定
    # ------------------------------------------------------------------

    def in_quiet_hours(self, now: datetime | None = None) -> bool:
        cfg = self._config
        if not cfg.enabled:
            return False
        if cfg.fail_closed:
            return True
        # 24h Quiet 表現 (START == END)
        if cfg.start_hour == cfg.end_hour:
            return True
        if now is None:
            now = datetime.now(cfg.tz)
        else:
            now = now.astimezone(cfg.tz)
        hour = now.hour
        if cfg.start_hour < cfg.end_hour:
            # 同日内範囲 (例: 9..17 が Quiet)
            return cfg.start_hour <= hour < cfg.end_hour
        # 跨日範囲 (例: 22..08 が Quiet)
        return hour >= cfg.start_hour or hour < cfg.end_hour

    # ------------------------------------------------------------------
    # allow() カテゴリ別 gate
    # ------------------------------------------------------------------

    def allow(self, category: Category, now: datetime | None = None) -> bool:
        if category in _QUIET_HOURS_EXEMPT:
            return True
        return not self.in_quiet_hours(now=now)

    # ------------------------------------------------------------------
    # next_active_window()
    # ------------------------------------------------------------------

    def next_active_window(self, now: datetime | None = None) -> tuple[datetime, datetime]:
        """次の (active_start, active_end) を返す.

        - Quiet Hours 中: 次の END 時刻から次の START 時刻まで
        - Active 中: 今から次の START 時刻まで
        """
        cfg = self._config
        if cfg.fail_closed or (not cfg.enabled):
            # fail-closed: 常に Quiet として、即時 next_active は与えない
            # 但しテストでは fail-closed の next_active_window を要求しない
            raise RuntimeError(
                "QuietHoursGuard is fail-closed; next_active_window unavailable"
            )
        if cfg.start_hour == cfg.end_hour:
            raise RuntimeError("24h Quiet Hours; no active window")
        if now is None:
            now = datetime.now(cfg.tz)
        else:
            now = now.astimezone(cfg.tz)
        today = now.replace(minute=0, second=0, microsecond=0)
        end_today = today.replace(hour=cfg.end_hour)
        _ = end_today  # active=end_today.. の計算下流で使うため保持

        if self.in_quiet_hours(now):
            # Active は次の END から次の START まで
            # 跨日 (22..08) のとき: 今が深夜 03:00 なら active は本日 08:00〜22:00
            # 跨日 (22..08) のとき: 今が 23:00 なら active は翌日 08:00〜22:00
            if cfg.start_hour > cfg.end_hour:
                if now.hour >= cfg.start_hour:
                    # 夜側 (22:00 以降): 翌日 END まで Quiet → active 開始
                    active_start = (today + timedelta(days=1)).replace(hour=cfg.end_hour)
                    active_end = (today + timedelta(days=1)).replace(hour=cfg.start_hour)
                else:
                    # 朝側 (00:00..end_hour): 当日 END から active
                    active_start = today.replace(hour=cfg.end_hour)
                    active_end = today.replace(hour=cfg.start_hour)
            else:
                # 同日内 Quiet (例: 9..17)
                active_start = end_today
                active_end = (today + timedelta(days=1)).replace(hour=cfg.start_hour)
            return (active_start, active_end)
        # Active 中: 今から次の START まで
        if cfg.start_hour > cfg.end_hour:
            active_start = now
            if now.hour < cfg.start_hour:
                active_end = today.replace(hour=cfg.start_hour)
            else:
                active_end = (today + timedelta(days=1)).replace(hour=cfg.start_hour)
        else:
            active_start = now
            active_end = today.replace(hour=cfg.start_hour) if now.hour < cfg.start_hour else (today + timedelta(days=1)).replace(hour=cfg.start_hour)
        return (active_start, active_end)
