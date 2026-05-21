# SPDX-License-Identifier: Apache-2.0
"""SpeciationLayer — NEAT 流動的種分け (llive v0.E CE-32).

Stanley & Miikkulainen (2002) の NEAT speciation を数値 genome に翻案.
集団を **genome 距離閾値 ε** で動的に種 (species) に分割し, 各 species で
**独立に selection を回す**. これにより:

- 1 種が集団全体を支配するのを防ぐ (niche preservation)
- **fitness sharing**: 同 species 内で fitness を平均化 → 大規模 species の
  優位性を緩和
- 異 species 間の interaction は **migration / inter-species crossover** で
  別途扱う (E.33 IslandModelMigration と協調)

設計:

- ``Species`` dataclass: 1 種は (id, representative_genome,
  member_individual_ids).
- ``SpeciationLayer.assign(population)``: 各個体を最も近い representative
  の種に割り振り. ε を超える個体は新種.
- ``Speciation 内 fitness sharing``: ``shared_fitness(i) = fitness(i) / size(species(i))``.
- ``SpeciatedTournamentSelection``: 同 species 内で tournament.

参照: Stanley & Miikkulainen (2002) "Evolving Neural Networks through
Augmenting Topologies", Evolutionary Computation 10(2).

要件根拠: ``docs/requirements_v0.E_competitive_coevolution.md`` CE-32.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import numpy as np

from llive.perf.evolutionary.individual import Individual
from llive.perf.evolutionary.population import Population


@dataclass
class Species:
    """1 種 (species). representative を持ち, 同種員の id を抱える.

    Attributes
    ----------
    species_id : str
        kebab-case slug or UUID hex.
    representative : np.ndarray
        この種の代表 genome (1D float array). 次世代でも近い個体を判定する基準.
    member_ids : list[str]
        現世代の所属個体 id.
    age : int
        この種が存続した世代数 (0 から始まる).
    """

    species_id: str
    representative: np.ndarray
    member_ids: list[str] = field(default_factory=list)
    age: int = 0

    def size(self) -> int:
        return len(self.member_ids)


@dataclass
class SpeciationLayer:
    """動的種分けレイヤ.

    Attributes
    ----------
    epsilon : float
        genome L2 距離の閾値. 同種判定はこれ以下.
    species : dict[str, Species]
        現在の種一覧. species_id → Species.
    min_species_size : int
        この値未満の種は merge or 削除候補.
    """

    epsilon: float = 1.0
    species: dict[str, Species] = field(default_factory=dict)
    min_species_size: int = 1

    def __post_init__(self) -> None:
        if self.epsilon <= 0:
            raise ValueError("epsilon must be > 0")
        if self.min_species_size < 1:
            raise ValueError("min_species_size must be >= 1")

    # ---------- public API ----------------------------------------------

    def assign(self, pop: Population) -> dict[str, list[Individual]]:
        """各個体を最も近い representative の種に割り振り (or 新種).

        前世代の representative は残し, 新世代は最も近い種に合流. 1 個体も
        合流できなければ新 species を作る.

        Returns
        -------
        dict[species_id, list[Individual]]
            各種に属する Individual list.
        """
        # 各 species の member_ids を一旦クリア (新世代を入れ直す)
        for sp in self.species.values():
            sp.member_ids = []

        assignments: dict[str, list[Individual]] = {sid: [] for sid in self.species}

        for ind in pop.individuals:
            values = ind.genome.as_array()
            best_sid: str | None = None
            best_dist = float("inf")
            for sid, sp in self.species.items():
                d = float(np.linalg.norm(values - sp.representative))
                if d < best_dist:
                    best_dist = d
                    best_sid = sid
            if best_sid is not None and best_dist <= self.epsilon:
                self.species[best_sid].member_ids.append(ind.individual_id)
                assignments[best_sid].append(ind)
            else:
                # 新種
                new_sid = uuid.uuid4().hex[:8]
                self.species[new_sid] = Species(
                    species_id=new_sid,
                    representative=values.copy(),
                    member_ids=[ind.individual_id],
                    age=0,
                )
                assignments[new_sid] = [ind]

        # 全 species の age を増やす (新規以外)
        for sid, sp in self.species.items():
            if sp.member_ids:  # 残った species
                sp.age += 1

        # 空 species を削除
        self.species = {sid: sp for sid, sp in self.species.items() if sp.member_ids}
        # min_species_size 未満は留保 (将来 merge オプション), ここでは削除しない.
        assignments = {sid: inds for sid, inds in assignments.items() if inds}
        return assignments

    def update_representatives(
        self,
        pop: Population,
        rng: np.random.Generator,
    ) -> None:
        """各 species の representative を, その種から **random に 1 体** 選んで更新.

        NEAT 標準では representative は random member. 安定性を上げたい場合は
        species 内 best member を使う variant も可.
        """
        id_to_ind = {ind.individual_id: ind for ind in pop.individuals}
        for sp in list(self.species.values()):
            if not sp.member_ids:
                continue
            chosen = sp.member_ids[int(rng.integers(0, len(sp.member_ids)))]
            sp.representative = id_to_ind[chosen].genome.as_array().copy()

    def shared_fitness(self, ind: Individual) -> float:
        """個体の shared fitness を返す (NEAT 標準 fitness sharing).

        ``shared = score / size(species(ind))``.

        未割り当ての個体は元 score をそのまま返す.
        """
        if ind.fitness is None:
            return float("-inf")
        for sp in self.species.values():
            if ind.individual_id in sp.member_ids:
                return float(ind.fitness.score / max(1, sp.size()))
        return float(ind.fitness.score)

    def n_species(self) -> int:
        return len(self.species)

    def species_sizes(self) -> dict[str, int]:
        return {sid: sp.size() for sid, sp in self.species.items()}


# ---------------------------------------------------------------------------
# SpeciatedTournamentSelection — species 内で tournament
# ---------------------------------------------------------------------------


@dataclass
class SpeciatedTournamentSelection:
    """1 species 内で k-tournament selection.

    各 selection 呼び出しでまず species をランダム選択 (size 重み付け) し,
    その species 内で k-tournament で勝者を返す.

    Attributes
    ----------
    layer : SpeciationLayer
    k : int
        tournament size. default 3.
    use_shared_fitness : bool
        True (default) なら shared_fitness で比較.
    """

    layer: SpeciationLayer
    k: int = 3
    use_shared_fitness: bool = True

    def __post_init__(self) -> None:
        if self.k < 1:
            raise ValueError("k must be >= 1")

    def __call__(
        self,
        pop: Population,
        rng: np.random.Generator,
    ) -> Individual:
        if not self.layer.species:
            # speciation 未走行: 全体から tournament
            candidates = list(rng.choice(pop.individuals, size=min(self.k, pop.size), replace=False))
        else:
            # species を size 重み付けで選ぶ
            sids = list(self.layer.species.keys())
            sizes = np.array(
                [self.layer.species[s].size() for s in sids], dtype=np.float64
            )
            if sizes.sum() <= 0:
                # fallback: 全体 tournament
                candidates = list(rng.choice(pop.individuals, size=min(self.k, pop.size), replace=False))
            else:
                probs = sizes / sizes.sum()
                chosen_sid = sids[int(rng.choice(len(sids), p=probs))]
                member_ids = self.layer.species[chosen_sid].member_ids
                id_to_ind = {i.individual_id: i for i in pop.individuals}
                candidates_pool = [id_to_ind[mid] for mid in member_ids if mid in id_to_ind]
                if not candidates_pool:
                    candidates = list(rng.choice(pop.individuals, size=min(self.k, pop.size), replace=False))
                else:
                    k_use = min(self.k, len(candidates_pool))
                    candidates = list(
                        rng.choice(candidates_pool, size=k_use, replace=False)
                    )

        def _score(ind: Individual) -> float:
            if self.use_shared_fitness:
                return self.layer.shared_fitness(ind)
            return ind.score

        return max(candidates, key=_score)


__all__ = [
    "SpeciatedTournamentSelection",
    "Speciation",
    "SpeciationLayer",
    "Species",
]


# Backward-compat alias (シンプル名で import 可能)
Speciation = SpeciationLayer
