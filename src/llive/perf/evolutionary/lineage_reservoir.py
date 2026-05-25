# SPDX-License-Identifier: Apache-2.0
"""lldarwin Stage1.5 — lineage-niched 中立貯蔵庫 (neutral reservoir).

novelty / ε-lexicase (lldarwin Stage1) は **行動多様性** を保つが **系統固定
(lineage fixation)** を止められない — 既存個体の保存のみで、絶滅した系統を復活
できないため、系統は中立浮動 (Kimura) で monoculture に向かう (honest 発見:
fullsense ``docs/research/lldarwin_stage1_results_2026_05_26.md``)。

:class:`LineageReservoir` は系統別の **best-ever 個体** を保持し、ある世代で
**絶滅した保護系統** (founders) を貯蔵庫の elite で **re-inject** する。これにより
系統多様性を構造的に保証する (PoC ``scripts/poc_lineage_reservoir.py`` で 8 founders /
150 世代で全系統生存・``lineage_fixation 0.31`` ≪ 0.8 を実証)。

:class:`~llive.perf.evolutionary.loop.EvolutionLoop` の ``on_population_bred`` hook に
そのまま渡せる callable。breed 直後 (評価前) に呼ばれ、親世代の評価済 fitness から
貯蔵庫を更新し、bred 個体の一部を絶滅系統 elite に差し替える。

HONEST: 貯蔵庫は frozen elite を再投入するため、復活系統の「生存」は能動進化でなく
代表の生命維持 (中立貯蔵庫の定義通り)。再結合の素材を残すのが目的で、実 LLM/VLM 能力の
選択圧は Stage2。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from llive.perf.evolutionary.individual import Individual
from llive.perf.evolutionary.population import Population

_UNKNOWN = "(unknown)"


@dataclass
class LineageReservoir:
    """系統別 best-ever を保持し、絶滅した保護系統を再投入する中立貯蔵庫.

    Attributes
    ----------
    lineage_of:
        ``individual_id -> lineage`` の祖先マップ。bred 個体は parent_ids[0] から
        系統を継承する。founder 世代は :meth:`seed_founders` で初期化。
    reservoir:
        ``lineage -> (best_score, genome)``。評価済 population から更新。
    protected_lineages:
        絶滅したら必ず再投入する系統 (通常は founders の persona id 群)。
    max_lineage_map:
        ``lineage_of`` の上限 (超過時は古い非保護エントリを間引く)。
    """

    lineage_of: dict[str, str] = field(default_factory=dict)
    reservoir: dict[str, tuple[float, object]] = field(default_factory=dict)
    protected_lineages: frozenset[str] = frozenset()
    max_lineage_map: int = 200_000
    reinject_interval: int = 1
    """再投入を行う世代間隔。1 = 毎世代 (既定, 系統を最大限保つ)。大きいほど絶滅系統を
    長く放置でき行動多様性を保ちやすいが、系統が長期欠落するリスク。系統保持 vs
    行動多様性のトレードオフ knob (honest 留保: frozen elite 再投入は genome spread を
    やや下げる)。"""

    # -- setup -------------------------------------------------------------

    def seed_founders(
        self, lineage_of: dict[str, str], protected: frozenset[str] | set[str]
    ) -> None:
        """founder 世代の ``id -> lineage`` マップと保護系統集合を初期化."""
        self.lineage_of.update(lineage_of)
        self.protected_lineages = frozenset(protected)

    # -- internals ---------------------------------------------------------

    def lineage(self, ind: Individual) -> str:
        return self.lineage_of.get(ind.individual_id, _UNKNOWN)

    def register(self, individuals: list[Individual]) -> None:
        """bred 個体の系統を parent_ids[0] から継承して記録."""
        for ind in individuals:
            if ind.individual_id in self.lineage_of:
                continue
            parent = ind.parent_ids[0] if ind.parent_ids else None
            self.lineage_of[ind.individual_id] = self.lineage_of.get(parent, _UNKNOWN)
        if len(self.lineage_of) > self.max_lineage_map:
            self._trim()

    def _trim(self) -> None:
        """非保護系統の古いエントリを間引く (dict は挿入順)。保護系統は残す."""
        keep = max(self.max_lineage_map // 2, len(self.protected_lineages) + 1)
        items = list(self.lineage_of.items())
        protected_items = [(k, v) for k, v in items if v in self.protected_lineages]
        recent = [(k, v) for k, v in items if v not in self.protected_lineages][-keep:]
        self.lineage_of = dict(protected_items + recent)

    def update_from_population(self, population: Population) -> None:
        """評価済 population から系統別 best-ever genome を更新."""
        for ind in population.individuals:
            if ind.fitness is None:
                continue
            lin = self.lineage(ind)
            score = float(ind.fitness.score)
            if lin not in self.reservoir or score > self.reservoir[lin][0]:
                self.reservoir[lin] = (score, ind.genome)

    # -- on_population_bred hook -------------------------------------------

    def __call__(
        self,
        bred: list[Individual],
        population: Population,
        rng: np.random.Generator,
    ) -> list[Individual]:
        """EvolutionLoop.on_population_bred として呼ばれ、絶滅保護系統を再投入する.

        手順: ①評価済 親世代から貯蔵庫更新 → ②bred の系統を登録 → ③bred に
        居ない保護系統を抽出 → ④bred のランダム slot を貯蔵庫 elite で置換。
        個体数は不変 (置換のみ)。
        """
        self.update_from_population(population)
        self.register(bred)
        if not bred:
            return bred
        present = {self.lineage(i) for i in bred}
        extinct = [
            lin
            for lin in self.protected_lineages
            if lin not in present and lin in self.reservoir
        ]
        if not extinct:
            return bred
        n = min(len(extinct), len(bred))
        slots = rng.choice(len(bred), size=n, replace=False)
        for slot, lin in zip(slots, extinct[:n]):
            _, genome = self.reservoir[lin]
            revived = Individual.from_genome(
                genome, birth_generation=bred[int(slot)].birth_generation
            )
            self.lineage_of[revived.individual_id] = lin
            bred[int(slot)] = revived
        return bred


__all__ = ["LineageReservoir"]
