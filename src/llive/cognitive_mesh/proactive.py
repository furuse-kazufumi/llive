# SPDX-License-Identifier: Apache-2.0
"""COG-MESH-06 ProactiveLoop — 周期/イベント駆動の能動発話ループ.

requirements_v0.8_cognitive_mesh.md §3 COG-MESH-06 の **skeleton**。
Phase 5 で full 実装する予定 (`project_proactive_llive_demo` Phase 0)。

現状は QuietHoursGuard との接続のみ最小実装し、tick() メソッドは
NotImplementedError を投げる "ready-to-implement" 状態。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from llive.cognitive_mesh.gift_value import GiftValueEstimator
from llive.cognitive_mesh.quiet_hours import QuietHoursGuard

Mode = Literal["timer", "event", "curiosity", "consistency"]


@dataclass
class ProactiveUtterance:
    """能動発話の最小データクラス."""

    content: str
    mode: Mode
    timestamp: datetime
    gift_value: float = 0.0  # COG-MESH-05 GiftValueEstimator の aggregate


@dataclass
class SuppressedUtterance:
    """発話 gate で抑制された候補発話 (cog.suppressed_utterance Annotation 相当)."""

    content: str
    reason: str  # "quiet_hours" / "gift_value_below_threshold" / "cooldown" 等
    gift_value: float
    timestamp: datetime


@dataclass
class ProactiveLoop:
    """FullSenseLoop を自発的に起動する周期/イベント駆動ループ.

    Phase 5 で full 実装。現状は Quiet Hours gate + GiftValueEstimator
    gate を備え、synthetic Stimulus 生成器を差し替えれば tick が回る。
    """

    quiet_hours: QuietHoursGuard
    gift_value: GiftValueEstimator | None = None
    tick_interval_seconds: float = 60.0
    mode: Mode = "timer"
    stimulus_source: Callable[[], str] | None = None
    _utterances: list[ProactiveUtterance] = field(default_factory=list)
    _suppressed: list[SuppressedUtterance] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.quiet_hours is None:
            raise TypeError(
                "ProactiveLoop requires a QuietHoursGuard (倫理は architecture の一部)"
            )
        if self.gift_value is None:
            # GiftValueEstimator を黙示的に与える (既定設定)
            self.gift_value = GiftValueEstimator()

    def can_speak_now(self, now: datetime | None = None) -> bool:
        """現在 Quiet Hours でないかつ category 'proactive' が許可されているか."""
        return self.quiet_hours.allow("proactive", now=now)

    def tick(
        self,
        now: datetime | None = None,
        listener_state: dict | None = None,
    ) -> ProactiveUtterance | None:
        """1 tick 進める.

        - Quiet Hours 中なら None で即時抑止
        - stimulus_source 未設定なら NotImplementedError (timer 以外の mode)
        - GiftValueEstimator で gate、閾値未満は抑制履歴に記録して None
        - 閾値以上で ProactiveUtterance を作成、commit() で履歴に反映
        """
        if not self.can_speak_now(now=now):
            return None
        if self.stimulus_source is None:
            raise NotImplementedError(
                "ProactiveLoop.tick: stimulus_source 未設定。Phase 5 M8.1 で "
                "synthetic Stimulus generator を注入する設計 (現時点は demo "
                "目的で外部から渡す)"
            )
        candidate = self.stimulus_source()
        gv = self.gift_value.estimate(
            candidate_utterance=candidate,
            listener_state=listener_state,
            now=now,
        )
        timestamp = now or datetime.now()
        if not gv.should_speak:
            self._suppressed.append(
                SuppressedUtterance(
                    content=candidate,
                    reason="gift_value_below_threshold",
                    gift_value=gv.aggregate,
                    timestamp=timestamp,
                )
            )
            return None
        utterance = ProactiveUtterance(
            content=candidate,
            mode=self.mode,
            timestamp=timestamp,
            gift_value=gv.aggregate,
        )
        self._utterances.append(utterance)
        self.gift_value.commit(candidate, now=timestamp)
        return utterance

    def latest_utterances(self, n: int = 10) -> list[ProactiveUtterance]:
        return self._utterances[-n:]

    def latest_suppressed(self, n: int = 10) -> list[SuppressedUtterance]:
        """抑制された候補発話の履歴 (`cog.suppressed_utterance` Annotation 相当)."""
        return self._suppressed[-n:]

    def start(self) -> None:
        """周期 tick を開始 (Phase 5 で threading.Timer / asyncio.Task)."""
        raise NotImplementedError("Phase 5: M8.1")

    def stop(self) -> None:
        """周期 tick を停止 (3 重停止の 1 つ)."""
        raise NotImplementedError("Phase 5: M8.1")
