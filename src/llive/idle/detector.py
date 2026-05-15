# SPDX-License-Identifier: Apache-2.0
"""IdleDetector — OS の最終入力時刻を読み取り (read-only).

Windows: GetLastInputInfo (pywin32 経由が望ましいが、ない場合は
ctypes 直接呼出しでも可能、ここでは未実装の場合 None を返す MVP)。
Linux / macOS: 環境変数や fcitx ipc 経由は今回未実装。

MVP は **manual override** を主眼とし、テスト容易性を確保する。
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class IdleStatus:
    """現在の idle 状態."""

    idle: bool
    seconds_since_last_input: float | None
    threshold_s: float


class IdleDetector:
    """idle threshold を超えていれば ``IdleStatus(idle=True)`` を返す.

    Constructor 引数:
        threshold_s: idle と判定する秒数 (既定 60s)
        last_input_provider: () -> float か None。
            テストや非 Windows 環境では明示注入可能。
            None なら ``_default_provider`` を使う (未実装環境では常に None)。
    """

    def __init__(
        self,
        *,
        threshold_s: float = 60.0,
        last_input_provider=None,
    ) -> None:
        self.threshold_s = float(threshold_s)
        self._provider = last_input_provider or self._default_provider

    @staticmethod
    def _default_provider() -> float | None:
        """OS API がまだ無い MVP では None を返す.

        将来: Windows GetLastInputInfo / Linux xdotool / macOS CGEventSourceSecondsSinceLastEventType
        を実装する。
        """
        return None

    def status(self) -> IdleStatus:
        seconds = self._provider()
        if seconds is None:
            return IdleStatus(
                idle=False,
                seconds_since_last_input=None,
                threshold_s=self.threshold_s,
            )
        return IdleStatus(
            idle=seconds >= self.threshold_s,
            seconds_since_last_input=float(seconds),
            threshold_s=self.threshold_s,
        )


def manual_provider(last_input_at: float):
    """テスト用: 与えた timestamp から「最終入力からの経過秒」を返す provider."""
    def _f() -> float:
        return max(0.0, time.monotonic() - last_input_at)
    return _f


__all__ = ["IdleDetector", "IdleStatus", "manual_provider"]
