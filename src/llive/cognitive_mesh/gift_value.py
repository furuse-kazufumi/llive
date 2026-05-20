# SPDX-License-Identifier: Apache-2.0
"""COG-MESH-05 GiftValueEstimator — 能動発話の価値見積もり gate.

requirements_v0.8_cognitive_mesh.md §3 COG-MESH-05 の最小実装。

「プレゼンテーション = プレゼント、価値を提供しないといけない」
(user_cognitive_mesh_model §14) を architectural に反映。発話前に
価値を見積もり、閾値未満なら **黙る**。

4 因子:
- novelty: 新規性 (既出発話との重複度の逆)
- relevance: 現在 brief / 主セッションへの関連性
- risk_avoidance: KYT 由来の重要度
- cost_to_listener: 時刻 / 集中度合 / Quiet Hours 等の負荷

aggregate は重み付き平均、既定閾値 0.6。
"""

from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta

# 4 因子の既定重み (合計 1.0)
DEFAULT_WEIGHTS: dict[str, float] = {
    "novelty": 0.30,
    "relevance": 0.30,
    "risk_avoidance": 0.25,
    "cost_to_listener": 0.15,
}

DEFAULT_THRESHOLD = 0.6


@dataclass(frozen=True)
class GiftValue:
    """発話前の価値見積もり結果."""

    novelty: float
    relevance: float
    risk_avoidance: float
    cost_to_listener: float  # 高いほど listener 負荷大、aggregate に減点として反映
    aggregate: float

    @property
    def should_speak(self) -> bool:
        return self.aggregate >= DEFAULT_THRESHOLD


@dataclass
class _UtteranceHistoryEntry:
    hash: str
    timestamp: datetime


class GiftValueEstimator:
    """能動発話の価値見積もり.

    naive な特徴量計算 (Phase 5 最小実装):
    - novelty: 過去 N 分以内に同一発話 hash が出ていなければ 1.0、出ていれば 0.0
    - relevance: listener_state['current_topic'] が候補発話に含まれていれば 1.0
    - risk_avoidance: listener_state['risk_score'] (0..1) をそのまま
    - cost_to_listener: listener_state['focus_level'] (0..1) と quiet_hours flag
    """

    def __init__(
        self,
        threshold: float = DEFAULT_THRESHOLD,
        weights: dict[str, float] | None = None,
        cooldown: timedelta = timedelta(minutes=30),
    ) -> None:
        self.threshold = threshold
        self.weights = weights or DEFAULT_WEIGHTS
        self.cooldown = cooldown
        # B-9-b sliding-window deque: 古い entry を commit 時に popleft で
        # 自動 evict し、_compute_novelty の走査範囲を cooldown 内に抑える.
        self._history: deque[_UtteranceHistoryEntry] = deque()

    def estimate(
        self,
        candidate_utterance: str,
        listener_state: dict | None = None,
        now: datetime | None = None,
    ) -> GiftValue:
        listener_state = listener_state or {}
        if now is None:
            now = datetime.now()
        novelty = self._compute_novelty(candidate_utterance, now)
        relevance = self._compute_relevance(candidate_utterance, listener_state)
        risk_avoidance = float(listener_state.get("risk_score", 0.5))
        cost_to_listener = self._compute_cost(listener_state)
        aggregate = self._aggregate(
            novelty=novelty,
            relevance=relevance,
            risk_avoidance=risk_avoidance,
            cost_to_listener=cost_to_listener,
        )
        return GiftValue(
            novelty=novelty,
            relevance=relevance,
            risk_avoidance=risk_avoidance,
            cost_to_listener=cost_to_listener,
            aggregate=aggregate,
        )

    def commit(self, utterance: str, now: datetime | None = None) -> None:
        """発話を実際に行ったら履歴に記録 (次回 novelty 計算に使う).

        cooldown を 2 倍以上超過した entry は自動 evict する (sliding window).
        """
        if now is None:
            now = datetime.now()
        evict_threshold = self.cooldown * 2
        while self._history and (now - self._history[0].timestamp) > evict_threshold:
            self._history.popleft()
        self._history.append(
            _UtteranceHistoryEntry(hash=self._hash(utterance), timestamp=now)
        )

    # ------------------------------------------------------------------
    # 特徴量計算
    # ------------------------------------------------------------------

    def _compute_novelty(self, utterance: str, now: datetime) -> float:
        utt_hash = self._hash(utterance)
        for entry in self._history:
            if entry.hash == utt_hash and (now - entry.timestamp) < self.cooldown:
                return 0.0
        return 1.0

    def _compute_relevance(self, utterance: str, listener_state: dict) -> float:
        topic = listener_state.get("current_topic")
        if topic is None:
            return 0.5  # neutral
        if isinstance(topic, str) and topic and topic.lower() in utterance.lower():
            return 1.0
        return 0.2

    def _compute_cost(self, listener_state: dict) -> float:
        """負荷 (0..1)。focus_level 高 + quiet_hours で負荷大."""
        focus = float(listener_state.get("focus_level", 0.5))
        quiet = bool(listener_state.get("in_quiet_hours", False))
        base = focus
        if quiet:
            base = max(base, 0.9)  # Quiet Hours では負荷を 0.9 以上に
        return min(1.0, base)

    def _aggregate(
        self,
        novelty: float,
        relevance: float,
        risk_avoidance: float,
        cost_to_listener: float,
    ) -> float:
        """重み付き平均。cost は減点として反映."""
        w = self.weights
        positive = (
            w["novelty"] * novelty
            + w["relevance"] * relevance
            + w["risk_avoidance"] * risk_avoidance
        )
        # cost は減点 (重み 0.15 * cost を引く)
        return max(0.0, min(1.0, positive - w["cost_to_listener"] * cost_to_listener))

    @staticmethod
    def _hash(utterance: str) -> str:
        return hashlib.sha256(utterance.encode("utf-8")).hexdigest()
