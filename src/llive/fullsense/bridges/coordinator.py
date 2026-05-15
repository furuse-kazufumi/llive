# SPDX-License-Identifier: Apache-2.0
"""Global Coordinator — aggregate score で早期 termination.

各 layer の出力スコアを 1 つの aggregate に集約し、threshold を超えた
時点で残り layer を skip する。Bridge と相補的: Bridge は特定 layer の
条件で skip、Coordinator は全体スコアで skip。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LayerScore:
    """1 layer の評価結果."""

    layer: str
    score: float


@dataclass
class GlobalCoordinator:
    """layer scores の累積で早期 termination を判定."""

    confidence_threshold: float = 0.85
    """累積 score がこの値を超えたら以降の layer を skip."""

    reject_threshold: float = 0.15
    """累積 score がこの値を下回ったら以降の layer を skip (= 早期 reject)."""

    weights: dict[str, float] = field(default_factory=dict)
    """layer 名 → 重み (未指定 = 1.0)."""

    def aggregate(self, scores: list[LayerScore]) -> float:
        if not scores:
            return 0.0
        total = 0.0
        total_w = 0.0
        for s in scores:
            w = self.weights.get(s.layer, 1.0)
            total += w * s.score
            total_w += w
        return total / total_w if total_w > 0 else 0.0

    def should_short_circuit(self, scores: list[LayerScore]) -> tuple[bool, str]:
        """累積 score を見て早期 termination 判定.

        Returns:
            (should_skip_rest, reason)
        """
        if not scores:
            return False, "no_data"
        agg = self.aggregate(scores)
        if agg >= self.confidence_threshold:
            return True, f"high_confidence_accept (agg={agg:.2f})"
        if agg <= self.reject_threshold:
            return True, f"low_confidence_reject (agg={agg:.2f})"
        return False, f"in_band (agg={agg:.2f})"


__all__ = ["GlobalCoordinator", "LayerScore"]
