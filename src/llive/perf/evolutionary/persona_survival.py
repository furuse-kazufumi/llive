# SPDX-License-Identifier: Apache-2.0
"""PersonaSurvivalAnalysis (v0.E CE-22 / Phase E.11).

ユーザー指示 (2026-05-21):
    「どの persona 組合せが世代を生き残ったか統計を取りたい。SurvivalRateTracker
     と同じ思想で persona 専用版が要る」

CE-22 = どの persona 組合せが世代を生き残ったか統計.

設計:
- composition signature = ``"|".join(sorted(persona_ids))``.
  pure exclusive persona は ``"newton"``, hybrid は ``"feynman|newton"``.
- 既存 ``SurvivalRateTracker`` (expert_evolution.py) を internal に持ち,
  observe_generation で signature を投入して streak / appearance を集計.
- additional metric:
  - ``hybrid_distribution()`` — signature の persona 数別出現分布
  - ``persona_appearance_count()`` — 個別 persona_id ごとの累計出現回数
  - ``hybrid_ratio()`` — n_personas >= 2 の signature 割合 (hybrid 優位仮説 H8 検証用)

要件根拠: ``docs/requirements_v0.E_competitive_coevolution.md`` 0.7 節
CE-22 + Phase E.11 + 仮説 H8 (hybrid persona の優位性).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from llive.perf.evolutionary.expert_evolution import (
    CompositionStat,
    SurvivalRateTracker,
)
from llive.perf.evolutionary.persona import PersonaComposition


@dataclass
class PersonaSurvivalAnalysis:
    """派生集団内の persona 組合せ生存統計.

    Attributes
    ----------
    tracker : SurvivalRateTracker
        内部の generic survival tracker (signature ベース).
    """

    tracker: SurvivalRateTracker = field(default_factory=SurvivalRateTracker)

    # ---------- signature helper -----------------------------------------

    @staticmethod
    def composition_signature(comp: PersonaComposition) -> str:
        """PersonaComposition から canonical signature を作る.

        sorted(persona_ids) → ``"|".join(...)``. weights / import_policy は
        signature には反映しない (集合としての persona 組合せが本質).
        """
        return "|".join(sorted(comp.persona_ids))

    # ---------- observation ----------------------------------------------

    def observe_generation(
        self,
        generation: int,
        compositions: Iterable[PersonaComposition],
        scores: Iterable[float] | None = None,
    ) -> None:
        """1 世代の compositions と (optional) scores を記録する."""
        comp_list = list(compositions)
        sigs = [self.composition_signature(c) for c in comp_list]
        self.tracker.observe(generation, sigs, scores=scores)

    # ---------- queries --------------------------------------------------

    def top_signatures(
        self,
        *,
        k: int = 5,
        by: str = "survived_generations",
    ) -> list[CompositionStat]:
        """上位 k 件の signature を返す.

        by: ``survived_generations`` / ``appearances`` / ``mean_score``.
        """
        return self.tracker.top_signatures(k=k, by=by)

    def hybrid_distribution(self) -> dict[int, int]:
        """signature の persona 数 → ユニーク signature 数 dict.

        Returns
        -------
        dict[int, int]
            e.g. {1: 5, 2: 12, 3: 3} は「単独 persona 5 種, 2 名 hybrid 12 種,
            3 名 hybrid 3 種」.
        """
        dist: defaultdict[int, int] = defaultdict(int)
        for sig in self.tracker.stats:
            n = len(sig.split("|")) if sig else 0
            dist[n] += 1
        return dict(dist)

    def persona_appearance_count(self) -> dict[str, int]:
        """個別 persona_id ごとの累計出現回数 (hybrid signature を unpack)."""
        counts: defaultdict[str, int] = defaultdict(int)
        for sig, stat in self.tracker.stats.items():
            if not sig:
                continue
            for pid in sig.split("|"):
                counts[pid] += stat.appearances
        return dict(counts)

    def hybrid_ratio(self) -> float:
        """signature 全体に占める「複数 persona」 signature の割合.

        H8 (hybrid persona 優位仮説) の定量指標. 0.0〜1.0.
        """
        total = len(self.tracker.stats)
        if total == 0:
            return 0.0
        hybrid = sum(
            1 for sig in self.tracker.stats if sig and len(sig.split("|")) >= 2
        )
        return float(hybrid / total)

    def survival_by_size(self) -> dict[int, float]:
        """persona 数別 平均 survived_generations.

        H8 verification: hybrid (>= 2) が単独 (1) より長く生存するか.
        """
        by_size: defaultdict[int, list[int]] = defaultdict(list)
        for sig, stat in self.tracker.stats.items():
            if not sig:
                continue
            n = len(sig.split("|"))
            by_size[n].append(stat.survived_generations)
        return {n: float(sum(v) / len(v)) for n, v in by_size.items() if v}

    # ---------- serialization --------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "tracker": self.tracker.to_dict(),
            "hybrid_distribution": self.hybrid_distribution(),
            "persona_appearance_count": self.persona_appearance_count(),
            "hybrid_ratio": self.hybrid_ratio(),
            "survival_by_size": self.survival_by_size(),
        }


__all__ = ["PersonaSurvivalAnalysis"]
