# SPDX-License-Identifier: Apache-2.0
"""IslandModel — 集団を N island に分割して独立進化 + migration (v0.E CE-33).

Cohoon et al. (1987) "A multi-population genetic algorithm for solving
the K-partition problem on hypercubes". GECCO.

設計:

- ``IslandPopulation``: 1 island = 1 Population (independent evolution).
- ``IslandTopology``: migration の隣接関係. ``ring`` (環状) / ``fully``
  (全結合) / ``star`` (中心 island に集約).
- ``IslandModel.migrate(rng)``: 各 island から ``migration_size`` 個体を
  選んで隣接 island に転送. 元 island から **削除**.
- migration policy: ``best`` (上位 K) / ``random`` (uniform) / ``worst``
  (難民送り).

llive 統合:

- 1 IslandModel = N Population. 各 island で EvolutionLoop を独立に回す.
- 各世代終了時に IslandModel.migrate(rng) を呼ぶことで島間遺伝子流入.

参照: Cohoon (1987), Tanese (1989), Whitley et al. (1999) Island Model GA.

要件根拠: ``docs/requirements_v0.E_competitive_coevolution.md`` CE-33.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from llive.perf.evolutionary.individual import Individual
from llive.perf.evolutionary.population import Population

Topology = Literal["ring", "fully", "star"]
MigrationPolicy = Literal["best", "random", "worst"]


@dataclass
class IslandModel:
    """N island の集団進化モデル.

    Attributes
    ----------
    islands : list[Population]
        各 island は独立 Population. 1 islad = 1 sub-population.
    topology : Topology
        migration の隣接関係.
    migration_size : int
        1 回の migration で各 island から送り出す個体数.
    migration_policy : MigrationPolicy
        誰を送るか.
    migration_interval : int
        N 世代ごとに 1 回 migrate. default 1 (毎世代).
    generation_counter : int
        内部 counter (migrate ごとに +1).
    """

    islands: list[Population]
    topology: Topology = "ring"
    migration_size: int = 1
    migration_policy: MigrationPolicy = "best"
    migration_interval: int = 1
    generation_counter: int = 0

    def __post_init__(self) -> None:
        if not self.islands:
            raise ValueError("islands must be non-empty")
        if len(self.islands) < 2 and self.topology != "star":
            # 1 island では migration 不要 (no-op になる)
            pass
        if self.migration_size < 0:
            raise ValueError("migration_size must be >= 0")
        if self.migration_interval < 1:
            raise ValueError("migration_interval must be >= 1")
        if self.topology not in ("ring", "fully", "star"):
            raise ValueError(f"unknown topology: {self.topology!r}")
        if self.migration_policy not in ("best", "random", "worst"):
            raise ValueError(f"unknown migration_policy: {self.migration_policy!r}")

    # ---------- public API ----------------------------------------------

    @property
    def n_islands(self) -> int:
        return len(self.islands)

    def total_size(self) -> int:
        return sum(pop.size for pop in self.islands)

    def neighbors(self, idx: int) -> list[int]:
        """idx 番目 island の migration 送信先 index 一覧."""
        n = self.n_islands
        if self.topology == "ring":
            return [(idx + 1) % n] if n > 1 else []
        if self.topology == "fully":
            return [j for j in range(n) if j != idx]
        if self.topology == "star":
            # idx==0 が中心. 周辺は中心と双方向.
            if idx == 0:
                return list(range(1, n))
            return [0]
        return []

    def select_emigrants(
        self,
        island_idx: int,
        rng: np.random.Generator,
    ) -> list[Individual]:
        """1 island から emigrant を選ぶ. migration_policy に従う."""
        pop = self.islands[island_idx]
        if self.migration_size <= 0 or pop.size == 0:
            return []
        k = min(self.migration_size, pop.size)
        inds = pop.individuals
        if self.migration_policy == "random":
            chosen_idx = rng.choice(pop.size, size=k, replace=False)
            return [inds[int(i)] for i in chosen_idx]
        scores = [
            (ind.fitness.score if ind.fitness is not None else float("-inf"), ind)
            for ind in inds
        ]
        if self.migration_policy == "best":
            scores.sort(key=lambda t: t[0], reverse=True)
        else:  # worst
            scores.sort(key=lambda t: t[0])
        return [ind for _, ind in scores[:k]]

    def migrate(self, rng: np.random.Generator) -> dict[str, int]:
        """1 回の migration を実行.

        各 island の neighbors に emigrant を送り, 元 island から削除して
        receiver に追加する.

        ``migration_interval > 1`` の場合, generation_counter を check して
        条件を満たさないなら no-op.

        Returns
        -------
        dict[str, int]
            migration 統計 (例: total_migrants=N, islands_affected=M).
        """
        self.generation_counter += 1
        if self.generation_counter % self.migration_interval != 0:
            return {"total_migrants": 0, "islands_affected": 0}

        # まず全 island から emigrant を抽出 (移送計画)
        plan: list[tuple[int, int, list[Individual]]] = []
        for src_idx, _pop in enumerate(self.islands):
            neighbors = self.neighbors(src_idx)
            if not neighbors:
                continue
            emigrants = self.select_emigrants(src_idx, rng)
            if not emigrants:
                continue
            # 各 neighbor に均等分配 (端数は最初の neighbor)
            n_neigh = len(neighbors)
            chunk = len(emigrants) // n_neigh
            extra = len(emigrants) % n_neigh
            cursor = 0
            for ni, dst_idx in enumerate(neighbors):
                size = chunk + (1 if ni < extra else 0)
                if size > 0:
                    plan.append((src_idx, dst_idx, emigrants[cursor : cursor + size]))
                    cursor += size

        # 計画を実行
        affected_islands: set[int] = set()
        total_migrants = 0
        for src_idx, dst_idx, ems in plan:
            src_pop = self.islands[src_idx]
            dst_pop = self.islands[dst_idx]
            # 削除
            keep_ids = {ind.individual_id for ind in src_pop.individuals}
            for em in ems:
                keep_ids.discard(em.individual_id)
            src_pop.individuals = [
                ind for ind in src_pop.individuals if ind.individual_id in keep_ids
            ]
            # 追加
            dst_pop.individuals.extend(ems)
            affected_islands.add(src_idx)
            affected_islands.add(dst_idx)
            total_migrants += len(ems)
        return {
            "total_migrants": total_migrants,
            "islands_affected": len(affected_islands),
        }

    def island_sizes(self) -> list[int]:
        return [pop.size for pop in self.islands]


__all__ = [
    "IslandModel",
    "MigrationPolicy",
    "Topology",
]
