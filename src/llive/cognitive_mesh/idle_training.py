# SPDX-License-Identifier: Apache-2.0
"""COG-MESH-04 IdleTrainingScheduler — Quiet Hours 外の自発 ingest.

requirements_v0.8_cognitive_mesh.md §3 COG-MESH-04 の最小実装。
ユーザ「空き時間トレーニング」の architectural 反映。

仕様:
- 外部情報源 (InfoSource) を `register()` で登録
- `should_ingest(now)` で「ingest すべきタイミングか」を判定
  - Quiet Hours 中 → False
  - QuietHoursGuard.allow("ingest") を経由
  - idle_threshold_seconds 以内に最近 source が走っていたら False
- `tick(now)` で 1 ソースを ingest し、IngestEvent を返す
- 各 source は `name` + `fetch()` callable で表現

安全境界:
- ingest した content は Quarantined Memory (SEC-01) に着地する想定
  (本実装では payload を返すだけで、SEC 統合は Phase 6 で)
- PII redaction / Ed25519 (SEC-02) は本実装では未統合
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from llive.cognitive_mesh.quarantined_memory import (
    QuarantinedMemory,
    QuarantineEntry,
    SignedPayload,
)
from llive.cognitive_mesh.quiet_hours import QuietHoursGuard


@dataclass(frozen=True)
class InfoSource:
    """ingest 対象の外部情報源."""

    name: str
    fetch: Callable[[], Any]
    cooldown: timedelta = timedelta(minutes=30)


@dataclass(frozen=True)
class IngestEvent:
    """ingest が走った 1 回分の記録."""

    source_name: str
    payload: Any
    timestamp: datetime


@dataclass
class IdleTrainingScheduler:
    """Quiet Hours 外の空き時間に外部情報を ingest する."""

    quiet_hours: QuietHoursGuard
    idle_threshold_seconds: int = 60
    _sources: dict[str, InfoSource] = field(default_factory=dict)
    _last_ingest: dict[str, datetime] = field(default_factory=dict)
    _events: list[IngestEvent] = field(default_factory=list)
    _paused: bool = False

    def __post_init__(self) -> None:
        if self.quiet_hours is None:
            raise TypeError(
                "IdleTrainingScheduler requires a QuietHoursGuard "
                "(fail-closed in Quiet Hours)"
            )

    # ------------------------------------------------------------------
    # source 登録
    # ------------------------------------------------------------------

    def register(self, source: InfoSource) -> None:
        if source.name in self._sources:
            raise ValueError(f"InfoSource '{source.name}' already registered")
        self._sources[source.name] = source

    def sources(self) -> list[InfoSource]:
        return list(self._sources.values())

    # ------------------------------------------------------------------
    # gate
    # ------------------------------------------------------------------

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def should_ingest(self, now: datetime | None = None) -> bool:
        if self._paused:
            return False
        if not self.quiet_hours.allow("ingest", now=now):
            return False
        if not self._sources:
            return False
        # 直近 ingest から idle_threshold_seconds 以内なら待つ
        if now is None:
            now = datetime.now()
        if self._events:
            most_recent = max(e.timestamp for e in self._events)
            if (now - most_recent).total_seconds() < self.idle_threshold_seconds:
                return False
        return True

    # ------------------------------------------------------------------
    # tick
    # ------------------------------------------------------------------

    def tick(self, now: datetime | None = None) -> IngestEvent | None:
        if not self.should_ingest(now=now):
            return None
        if now is None:
            now = datetime.now()
        # cooldown を満たすソースのうち、最も古い ingest のものを選ぶ
        ranked: list[tuple[datetime, InfoSource]] = []
        for src in self._sources.values():
            last = self._last_ingest.get(src.name)
            if last is None:
                ranked.append((datetime.min.replace(tzinfo=now.tzinfo), src))
                continue
            # cooldown 内ならスキップ
            if (now - last) < src.cooldown:
                continue
            ranked.append((last, src))
        if not ranked:
            return None
        ranked.sort(key=lambda pair: pair[0])
        src = ranked[0][1]
        payload = src.fetch()
        event = IngestEvent(source_name=src.name, payload=payload, timestamp=now)
        self._events.append(event)
        self._last_ingest[src.name] = now
        return event

    def latest_events(self, n: int = 10) -> list[IngestEvent]:
        return self._events[-n:]
