# SPDX-License-Identifier: Apache-2.0
"""OKA-03 — Strategy Orchestrator.

岡潔「数学は必ず発見の前に一度行き詰まる」を実装に置き換えた戦略管理層。
複数の解法ファミリーを並列に登録しておき、進捗が停滞したら別戦略へ切り替える。

最小プロトタイプの責務:

* :class:`StrategyFamily` — 1 つの解法ファミリー (record-only — 実行は呼び出し側)
* :class:`StrategyOrchestrator` — 進捗 push / stall 検出 / switch 提案
* :class:`StrategySwitchEvent` — 切替の audit 単位

LLM や solver を直接呼ばない — それらは呼び出し側 (BriefRunner の tool
handler 等) が担当する。orchestrator は「どの戦略で攻めているか」「停滞して
いないか」だけを deterministic に追跡し、切替の意思決定を audit する。

トレーサビリティ:

* ``bind_ledger`` で BriefLedger に attach → 切替が起きたら
  ``oka_strategy_switched`` event を記録
* COG-03 trace_graph の decision_chain に統合される (ledger.py 側で対応)
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Deque

if TYPE_CHECKING:
    from llive.brief.ledger import BriefLedger


@dataclass(frozen=True)
class StrategyFamily:
    """1 つの解法ファミリーの宣言的記述。"""

    name: str
    description: str = ""
    tags: tuple[str, ...] = ()  # e.g. ("symbolic", "z3", "geometric")


@dataclass(frozen=True)
class StrategySwitchEvent:
    """戦略切替の決定論的 audit unit."""

    from_strategy: str
    to_strategy: str
    reason: str
    progress_history: tuple[float, ...]
    timestamp: float = field(default_factory=time.time)

    def to_payload(self) -> dict[str, object]:
        return {
            "from_strategy": self.from_strategy,
            "to_strategy": self.to_strategy,
            "reason": self.reason,
            "progress_history": list(self.progress_history),
            "timestamp": self.timestamp,
        }


class StrategyOrchestrator:
    """戦略ファミリーを保持し、停滞検知で切替を提案する deterministic 層。

    使い方:

    >>> orch = StrategyOrchestrator()
    >>> orch.register(StrategyFamily(name="symbolic", tags=("z3",)))
    >>> orch.register(StrategyFamily(name="geometric"))
    >>> orch.activate("symbolic")
    >>> orch.push_progress(0.1); orch.push_progress(0.1); orch.push_progress(0.1)
    >>> orch.should_switch()  # 停滞検知
    True
    >>> orch.switch_to("geometric", reason="symbolic stalled at 0.1")
    StrategySwitchEvent(from_strategy='symbolic', to_strategy='geometric', ...)
    """

    def __init__(
        self,
        *,
        history_window: int = 5,
        stall_delta: float = 0.02,
        ledger: "BriefLedger | None" = None,
    ) -> None:
        self._families: dict[str, StrategyFamily] = {}
        self._active: str | None = None
        self._progress: Deque[float] = deque(maxlen=history_window)
        self._window = history_window
        self._stall_delta = stall_delta
        self._ledger = ledger
        self._switch_events: list[StrategySwitchEvent] = []

    # -- registration -------------------------------------------------------

    def register(self, family: StrategyFamily) -> None:
        if family.name in self._families:
            raise ValueError(f"duplicate strategy name: {family.name!r}")
        self._families[family.name] = family

    def list_families(self) -> tuple[StrategyFamily, ...]:
        return tuple(self._families.values())

    # -- activation / progress ---------------------------------------------

    def activate(self, name: str) -> None:
        if name not in self._families:
            raise KeyError(f"unknown strategy: {name!r}")
        self._active = name
        self._progress.clear()

    @property
    def active(self) -> str | None:
        return self._active

    def push_progress(self, value: float) -> None:
        """Append a progress score (0.0〜1.0 monotonically increases when healthy)."""
        if not 0.0 <= float(value) <= 1.0:
            raise ValueError(f"progress must be in [0,1], got {value!r}")
        self._progress.append(float(value))

    # -- stall detection / switch ------------------------------------------

    def should_switch(self) -> bool:
        """``True`` if the active strategy's progress is flat over the window.

        Definition: window full AND max-min Δ < ``stall_delta``.
        """
        if len(self._progress) < self._window:
            return False
        return (max(self._progress) - min(self._progress)) < self._stall_delta

    def switch_to(self, name: str, *, reason: str = "") -> StrategySwitchEvent:
        if name not in self._families:
            raise KeyError(f"unknown strategy: {name!r}")
        if name == self._active:
            raise ValueError(f"already on strategy {name!r}")
        from_strat = self._active or ""
        history = tuple(self._progress)
        event = StrategySwitchEvent(
            from_strategy=from_strat,
            to_strategy=name,
            reason=reason or "manual switch",
            progress_history=history,
        )
        self._switch_events.append(event)
        if self._ledger is not None:
            self._ledger.append("oka_strategy_switched", event.to_payload())
        self._active = name
        self._progress.clear()
        return event

    def switch_events(self) -> tuple[StrategySwitchEvent, ...]:
        return tuple(self._switch_events)

    # -- ledger binding ----------------------------------------------------

    def bind_ledger(self, ledger: "BriefLedger | None") -> None:
        self._ledger = ledger
