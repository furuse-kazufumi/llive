# SPDX-License-Identifier: Apache-2.0
"""COG-MESH-06 ProactiveLoop — 周期/イベント駆動の能動発話ループ.

requirements_v0.8_cognitive_mesh.md §3 COG-MESH-06 の **skeleton**。
Phase 5 で full 実装する予定 (`project_proactive_llive_demo` Phase 0)。

現状は QuietHoursGuard との接続のみ最小実装し、tick() メソッドは
NotImplementedError を投げる "ready-to-implement" 状態。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Literal, Optional

from llive.cognitive_mesh.quiet_hours import QuietHoursGuard


Mode = Literal["timer", "event", "curiosity", "consistency"]


@dataclass
class ProactiveUtterance:
    """能動発話の最小データクラス."""

    content: str
    mode: Mode
    timestamp: datetime
    gift_value: float = 0.0  # COG-MESH-05 GiftValueEstimator の出力


@dataclass
class ProactiveLoop:
    """FullSenseLoop を自発的に起動する周期/イベント駆動ループ.

    Phase 5 で full 実装。今は Quiet Hours gate だけ接続。
    """

    quiet_hours: QuietHoursGuard
    tick_interval_seconds: float = 60.0
    mode: Mode = "timer"
    _utterances: list[ProactiveUtterance] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.quiet_hours is None:
            raise TypeError(
                "ProactiveLoop requires a QuietHoursGuard (倫理は architecture の一部)"
            )

    def can_speak_now(self, now: Optional[datetime] = None) -> bool:
        """現在 Quiet Hours でないかつ category 'proactive' が許可されているか."""
        return self.quiet_hours.allow("proactive", now=now)

    def tick(self, now: Optional[datetime] = None) -> Optional[ProactiveUtterance]:
        """1 tick 進める。Phase 5 で実装予定。

        - Quiet Hours 中なら何もしない (None を返す)
        - timer mode: synthetic Stimulus を作成 → FullSenseLoop.process →
          GiftValueEstimator → utterance を返す or 黙る
        """
        if not self.can_speak_now(now=now):
            return None
        raise NotImplementedError(
            "ProactiveLoop.tick is COG-MESH-06 Phase 5 milestone — see "
            "requirements_v0.8_cognitive_mesh.md M8.1 (Proactive demo timer)"
        )

    def latest_utterances(self, n: int = 10) -> list[ProactiveUtterance]:
        return self._utterances[-n:]

    def start(self) -> None:
        """周期 tick を開始 (Phase 5 で threading.Timer / asyncio.Task)."""
        raise NotImplementedError("Phase 5: M8.1")

    def stop(self) -> None:
        """周期 tick を停止 (3 重停止の 1 つ)."""
        raise NotImplementedError("Phase 5: M8.1")
