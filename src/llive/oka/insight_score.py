# SPDX-License-Identifier: Apache-2.0
"""OKA-07 — Insight Score 評価フレーム.

CoreEssence (OKA-02 出力) と ground-truth essence を deterministic に
比較し insight quality を 0.0〜1.0 で数値化する。

3 軸 score:

* **coverage** — ground-truth invariants / symmetries / mystery を CoreEssence が
  どれだけ拾えたか
* **succinctness** — essence_summary が ground-truth より短いか (短いほど高得点)
* **alignment** — ground-truth との token overlap (Jaccard 系)

総合 ``insight_score`` は重み付き平均。Strategy 注入点なし (deterministic) だが、
LLM judge 版に置き換えるなら :class:`InsightScorer` を継承して :meth:`score` を override。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    from llive.brief.ledger import BriefLedger
    from llive.oka.essence import CoreEssence


_TOKEN_RE = re.compile(r"[A-Za-z0-9_ぁ-ゟ゠-ヿ一-鿿]+", re.UNICODE)


@dataclass(frozen=True)
class GroundTruthEssence:
    """ground-truth essence — annotator が用意した正解 essence."""

    essence_summary: str
    mystery: str = ""
    invariants: tuple[str, ...] = ()
    symmetries: tuple[str, ...] = ()

    def all_terms(self) -> set[str]:
        bag = " ".join((self.essence_summary, self.mystery, *self.invariants, *self.symmetries))
        return {t.lower() for t in _TOKEN_RE.findall(bag)}


@dataclass(frozen=True)
class InsightScore:
    coverage: float
    succinctness: float
    alignment: float
    insight_score: float
    diagnostics: Mapping[str, str] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        return {
            "coverage": self.coverage,
            "succinctness": self.succinctness,
            "alignment": self.alignment,
            "insight_score": self.insight_score,
            "diagnostics": dict(self.diagnostics),
        }


_DEFAULT_WEIGHTS: dict[str, float] = {
    "coverage": 0.45,
    "succinctness": 0.20,
    "alignment": 0.35,
}


class InsightScorer:
    """Deterministic insight scorer."""

    def __init__(
        self,
        *,
        weights: Mapping[str, float] | None = None,
        ledger: "BriefLedger | None" = None,
    ) -> None:
        self._weights = dict(weights) if weights is not None else dict(_DEFAULT_WEIGHTS)
        self._ledger = ledger

    def bind_ledger(self, ledger: "BriefLedger | None") -> None:
        self._ledger = ledger

    def score(self, candidate: "CoreEssence", ground_truth: GroundTruthEssence) -> InsightScore:
        cand_terms = self._terms(candidate)
        gt_terms = ground_truth.all_terms()
        if not gt_terms:
            coverage = 1.0
        else:
            coverage = len(cand_terms & gt_terms) / len(gt_terms)
        cand_len = max(1, len(candidate.essence_summary))
        gt_len = max(1, len(ground_truth.essence_summary))
        if cand_len <= gt_len:
            succinctness = 1.0
        else:
            ratio = gt_len / cand_len
            succinctness = max(0.0, min(1.0, ratio))
        union = cand_terms | gt_terms
        alignment = (len(cand_terms & gt_terms) / len(union)) if union else 1.0
        weighted = (
            self._weights.get("coverage", 0.0) * coverage
            + self._weights.get("succinctness", 0.0) * succinctness
            + self._weights.get("alignment", 0.0) * alignment
        )
        diagnostics = {
            "cand_terms": str(len(cand_terms)),
            "gt_terms": str(len(gt_terms)),
            "common_terms": str(len(cand_terms & gt_terms)),
            "cand_len_chars": str(cand_len),
            "gt_len_chars": str(gt_len),
        }
        result = InsightScore(
            coverage=coverage,
            succinctness=succinctness,
            alignment=alignment,
            insight_score=max(0.0, min(1.0, weighted)),
            diagnostics=diagnostics,
        )
        if self._ledger is not None:
            self._ledger.append("insight_score_recorded", result.to_payload())
        return result

    @staticmethod
    def _terms(essence: "CoreEssence") -> set[str]:
        bag = " ".join((
            essence.essence_summary,
            essence.mystery,
            *essence.invariants,
            *essence.symmetries,
        ))
        return {t.lower() for t in _TOKEN_RE.findall(bag)}


__all__ = [
    "GroundTruthEssence",
    "InsightScore",
    "InsightScorer",
]
