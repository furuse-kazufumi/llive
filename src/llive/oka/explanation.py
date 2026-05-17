# SPDX-License-Identifier: Apache-2.0
"""OKA-06 — Explanation Alignment Layer.

岡潔の言う「数学は説明できなければ伝わらない」を実装に置き換えた、
解答 + 「なぜその見方が自然か」テンプレ生成 + 納得感 score (heuristic) の
最小プロト。

設計:

* :class:`ExplanationDraft` — 解答 + naturalness rationale + comparison_note
* :class:`ExplanationAligner` — 解答テキストと参考視点 (essence / TRIZ / etc.) を
  受け取り、説明を組み立てる。score は deterministic な heuristic で初期実装

ledger 連動: `explanation_aligned` event。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llive.brief.ledger import BriefLedger
    from llive.oka.essence import CoreEssence


@dataclass(frozen=True)
class ExplanationDraft:
    """1 件の説明草案。"""

    answer: str
    naturalness_rationale: str
    comparison_note: str
    resonance_score: float   # 0.0〜1.0 deterministic heuristic

    def to_payload(self) -> dict[str, object]:
        return {
            "answer": self.answer,
            "naturalness_rationale": self.naturalness_rationale,
            "comparison_note": self.comparison_note,
            "resonance_score": self.resonance_score,
        }


class ExplanationAligner:
    """Deterministic explanation aligner.

    Strategy 注入点は無いが、LLM lens 化するときは :meth:`align` を override すれば
    十分。score は (a) essence と answer の共通語数、(b) comparison_note 文長、
    (c) naturalness_rationale 文長を組み合わせた heuristic。
    """

    def __init__(self, *, ledger: "BriefLedger | None" = None) -> None:
        self._ledger = ledger

    def bind_ledger(self, ledger: "BriefLedger | None") -> None:
        self._ledger = ledger

    def align(
        self,
        answer: str,
        *,
        essence: "CoreEssence | None" = None,
        alternative_descriptions: tuple[str, ...] = (),
    ) -> ExplanationDraft:
        """組み立ては deterministic — 入力に応じてテンプレを差し込む。"""
        rationale_parts: list[str] = []
        if essence is not None:
            rationale_parts.append(
                f"核心 ({essence.essence_summary}) と整合する見方を採った"
            )
            if essence.invariants:
                rationale_parts.append(
                    f"保存量 {essence.invariants[0]} を中心に据えると自然に従う"
                )
            if essence.symmetries:
                rationale_parts.append(
                    f"対称性 {essence.symmetries[0]} を活かすと操作回数が減る"
                )
        if not rationale_parts:
            rationale_parts.append("入力からは特に強い見方候補がないため、最短で答えを記述")

        if alternative_descriptions:
            comparison = (
                "他法と比べ: "
                + "; ".join(f"({i+1}) {d}" for i, d in enumerate(alternative_descriptions))
            )
        else:
            comparison = "他法との比較は未収集 — 後続で比較推奨"

        score = self._score(answer, essence, alternative_descriptions, rationale_parts)
        draft = ExplanationDraft(
            answer=answer,
            naturalness_rationale=" / ".join(rationale_parts),
            comparison_note=comparison,
            resonance_score=score,
        )
        if self._ledger is not None:
            self._ledger.append("explanation_aligned", draft.to_payload())
        return draft

    @staticmethod
    def _score(
        answer: str,
        essence: "CoreEssence | None",
        alts: tuple[str, ...],
        rationale_parts: list[str],
    ) -> float:
        # baseline 0.4; reward grounding + comparison + non-trivial rationale
        score = 0.4
        if essence is not None:
            ess_tokens = set(essence.essence_summary.split())
            ans_tokens = set(answer.split())
            common = ess_tokens & ans_tokens
            if common:
                score += min(0.3, 0.05 * len(common))
        if alts:
            score += min(0.2, 0.05 * len(alts))
        if len(rationale_parts) >= 2:
            score += 0.1
        return max(0.0, min(1.0, score))


__all__ = [
    "ExplanationAligner",
    "ExplanationDraft",
]
