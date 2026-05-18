# SPDX-License-Identifier: Apache-2.0
"""COG-MESH-06 ProactiveLoop — 周期/イベント駆動の能動発話ループ.

requirements_v0.8_cognitive_mesh.md §3 COG-MESH-06 の **skeleton**。
Phase 5 で full 実装する予定 (`project_proactive_llive_demo` Phase 0)。

現状は QuietHoursGuard との接続のみ最小実装し、tick() メソッドは
NotImplementedError を投げる "ready-to-implement" 状態。
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from llive.cognitive_mesh.gift_value import GiftValueEstimator
from llive.cognitive_mesh.quiet_hours import QuietHoursGuard

_logger = logging.getLogger("llive.cognitive_mesh.proactive")

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
    # COG-MESH-06 curiosity モード: 4 層メモリの coverage map を返す callable.
    # キー = memory layer name (semantic / episodic / structural / parameter)、
    # 値 = カバレッジ (0..1, 1 が密)。低い layer に対する質問を発話化する。
    coverage_source: Callable[[], dict[str, float]] | None = None
    # curiosity モードの coverage 閾値 — これ以下なら「埋まっていない領域」
    curiosity_threshold: float = 0.5
    # 自律 tick (_on_timer) から呼ばれる listener_state プロバイダ.
    # 設定されていれば自動的に GiftValueEstimator に渡される。None なら無し。
    listener_state_source: Callable[[], dict] | None = None
    _utterances: list[ProactiveUtterance] = field(default_factory=list)
    _suppressed: list[SuppressedUtterance] = field(default_factory=list)
    _timer: threading.Timer | None = field(default=None, init=False, repr=False)
    _stopped: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _running: bool = field(default=False, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

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

    def tick_curiosity(
        self,
        now: datetime | None = None,
        listener_state: dict | None = None,
    ) -> ProactiveUtterance | None:
        """curiosity モード tick — coverage map が薄い memory layer に対する問いを発話化.

        COG-MESH-06 mode='curiosity' の prototype。Phase 6 M8.7 で本格化。
        本実装は最小: coverage_source から薄い layer を見つけ、固定テンプレで
        質問文を生成 → GiftValueEstimator + Quiet Hours の通常 gate に乗せる。

        - coverage_source 未設定: NotImplementedError
        - 薄い layer 無し (全て >= curiosity_threshold): None
        - Quiet Hours 中: None
        """
        if not self.can_speak_now(now=now):
            return None
        if self.coverage_source is None:
            raise NotImplementedError(
                "ProactiveLoop.tick_curiosity: coverage_source 未設定。"
                "Phase 6 M8.7 で 4 層メモリの coverage map と接続予定"
            )
        coverage = self.coverage_source()
        # 最も薄い layer を選ぶ
        thin = [(layer, c) for layer, c in coverage.items() if c < self.curiosity_threshold]
        if not thin:
            return None
        thin.sort(key=lambda pair: pair[1])
        layer, cov = thin[0]
        candidate = (
            f"{layer} memory のカバレッジが {cov:.2f} と薄いようです。"
            f"最近この領域に新しい知見はありましたか?"
        )
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
            mode="curiosity",
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

    # ------------------------------------------------------------------
    # 自律 tick (threading.Timer ベース、daemon)
    # ------------------------------------------------------------------

    def start(self) -> None:
        """周期 tick を開始する.

        threading.Timer を daemon で起動し、tick_interval_seconds ごとに
        現在の mode に応じた tick (timer/curiosity) を実行する。
        既に起動中なら RuntimeError。
        """
        with self._lock:
            if self._running:
                raise RuntimeError("ProactiveLoop already started")
            self._stopped.clear()
            self._running = True
        self._schedule_next()

    def stop(self) -> None:
        """周期 tick を停止する (3 重停止の 1 つ)."""
        with self._lock:
            self._stopped.set()
            self._running = False
            timer = self._timer
            self._timer = None
        if timer is not None:
            timer.cancel()

    @property
    def is_running(self) -> bool:
        """周期 tick が走っているか."""
        return self._running

    def _schedule_next(self) -> None:
        """次の tick を schedule (Quiet Hours / stopped を尊重)."""
        if self._stopped.is_set():
            return
        timer = threading.Timer(self.tick_interval_seconds, self._on_timer)
        timer.daemon = True
        with self._lock:
            self._timer = timer
        timer.start()

    def _on_timer(self) -> None:
        """Timer firing handler — 例外を握り潰して次回 tick を絶やさない."""
        if self._stopped.is_set():
            return
        try:
            listener_state = (
                self.listener_state_source()
                if self.listener_state_source is not None
                else None
            )
            if self.mode == "curiosity" and self.coverage_source is not None:
                self.tick_curiosity(listener_state=listener_state)
            elif self.mode == "timer" and self.stimulus_source is not None:
                self.tick(listener_state=listener_state)
            else:
                # mode が timer で stimulus_source 未設定 → サイレント skip
                # (next tick で再評価、設定変更を受け入れる)
                _logger.debug("ProactiveLoop._on_timer: nothing to tick (mode=%s)", self.mode)
        except Exception:  # noqa: BLE001 — 自律 tick を止めない
            _logger.exception("ProactiveLoop tick failed (mode=%s)", self.mode)
        if not self._stopped.is_set():
            self._schedule_next()
