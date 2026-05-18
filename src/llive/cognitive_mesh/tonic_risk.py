# SPDX-License-Identifier: Apache-2.0
"""COG-MESH-03 TonicRiskMonitor — 小脳的常時 KYT (危険予測).

requirements_v0.8_cognitive_mesh.md §3 COG-MESH-03 の最小実装.

ユーザ言語化「小脳のような高速応答系。危険予測 KYT を常時繰り返し、
突然の事態に対応する」(user_cognitive_mesh_model §2) を architectural
に反映。

仕様:
- 複数の RiskModel を register。各 model は score(state) -> float (0..1)
- tick() で全 model を評価し、最大 score を返す
- 閾値超のとき alert callback (intervention) を発火
- 連続発火を防ぐ cooldown
- threading は本実装では使わず同期版 (Phase 6 で別スレッド化、エッジ実装は
  別チップ視野)
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

_logger = logging.getLogger("llive.cognitive_mesh.tonic_risk")


@dataclass
class RiskModel:
    """名前付きの risk 評価モデル."""

    name: str
    score_fn: Callable[[dict[str, Any]], float]
    weight: float = 1.0


@dataclass
class RiskAlert:
    """閾値超で発火するアラート."""

    model_name: str
    score: float
    timestamp: datetime
    state_snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass
class TonicRiskMonitor:
    """常時動く危険予測モニタ (同期最小版)."""

    interrupt_threshold: float = 0.7
    cooldown: timedelta = timedelta(seconds=30)
    on_alert: Callable[[RiskAlert], None] | None = None
    state_source: Callable[[], dict[str, Any]] | None = None
    tick_interval_seconds: float = 0.5  # 既定 500ms (小脳的高速 tick)
    _models: dict[str, RiskModel] = field(default_factory=dict)
    _alerts: list[RiskAlert] = field(default_factory=list)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _stopped: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _running: bool = field(default=False, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def register(self, model: RiskModel) -> None:
        if model.name in self._models:
            raise ValueError(f"RiskModel '{model.name}' already registered")
        self._models[model.name] = model

    def models(self) -> list[RiskModel]:
        return list(self._models.values())

    def latest_scores(self, state: dict[str, Any]) -> dict[str, float]:
        return {name: model.score_fn(state) for name, model in self._models.items()}

    # ------------------------------------------------------------------
    # tick
    # ------------------------------------------------------------------

    def tick(
        self,
        state: dict[str, Any],
        now: datetime | None = None,
    ) -> RiskAlert | None:
        if now is None:
            now = datetime.now()
        # cooldown 中ならスキップ
        if self._alerts:
            last = self._alerts[-1].timestamp
            if (now - last) < self.cooldown:
                return None
        # 各 model の重み付け score、最大を取る
        best_name: str | None = None
        best_score = -1.0
        for name, model in self._models.items():
            raw = model.score_fn(state)
            weighted = raw * model.weight
            if weighted > best_score:
                best_score = weighted
                best_name = name
        if best_name is None or best_score < self.interrupt_threshold:
            return None
        alert = RiskAlert(
            model_name=best_name,
            score=best_score,
            timestamp=now,
            state_snapshot=dict(state),
        )
        self._alerts.append(alert)
        if self.on_alert is not None:
            self.on_alert(alert)
        return alert

    def latest_alerts(self, n: int = 10) -> list[RiskAlert]:
        return self._alerts[-n:]

    # ------------------------------------------------------------------
    # 自律 tick (別 daemon thread、小脳的高速)
    # ------------------------------------------------------------------

    def start(self) -> None:
        """別 daemon thread で常時 tick を開始する.

        state_source を呼んで現在の state を取得 → tick(state) → alert
        を `on_alert` callback で外向き emit。state_source 未設定では
        起動できない (RuntimeError)。
        """
        if self.state_source is None:
            raise RuntimeError(
                "TonicRiskMonitor.start: state_source 未設定。"
                "現在 state を返す callable を注入してください"
            )
        with self._lock:
            if self._running:
                raise RuntimeError("TonicRiskMonitor already started")
            self._stopped.clear()
            self._running = True
            thread = threading.Thread(
                target=self._loop,
                daemon=True,
                name="llive.tonic_risk",
            )
            self._thread = thread
        thread.start()

    def stop(self, timeout: float | None = 1.0) -> None:
        """tick を停止する (idempotent)."""
        with self._lock:
            self._stopped.set()
            self._running = False
            thread = self._thread
            self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)

    @property
    def is_running(self) -> bool:
        return self._running

    def _loop(self) -> None:
        """別 thread のメインループ — 例外を握り潰して tick を絶やさない."""
        while not self._stopped.is_set():
            try:
                state = self.state_source() if self.state_source else {}
                self.tick(state=state)
            except Exception:  # noqa: BLE001 — 常時 tick を止めない
                _logger.exception("TonicRiskMonitor tick failed")
            # Event.wait で stopped シグナルを受けたら即座に出る
            if self._stopped.wait(timeout=self.tick_interval_seconds):
                break
