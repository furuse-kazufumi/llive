# SPDX-License-Identifier: Apache-2.0
"""NSGA-II Multi-Objective Fitness (llive v0.E CE-31).

Deb et al. (2002) "A fast and elitist multiobjective genetic algorithm:
NSGA-II". IEEE Trans. on Evolutionary Computation 6(2).

複数 objective (例: peer_score, novelty, persona_diversity) を **同時に**
最大化するための非劣分類 + crowding distance.

設計:

- ``MultiObjectiveScore``: 1 個体の (objective_name → value) dict.
- ``non_dominated_sort(population)``: 集団を rank (front) に分割.
  rank 0 = Pareto front, rank 1 = front 0 を除いた front, ...
- ``crowding_distance(population, rank)``: 同 rank 内で隣接 objective 距離.
  端点は infty (端点保護).
- ``NSGA2Selection``: rank 優先 + 同 rank なら crowding distance 大優先で
  tournament 風 selection.

llive 統合:

- 各 Individual.fitness.breakdown に objective dict を持たせる前提.
- ``objectives`` 引数で参照する key 列を指定.

参照: Deb et al. (2002), Deb (2001) *Multi-Objective Optimization Using
Evolutionary Algorithms*.

要件根拠: ``docs/requirements_v0.E_competitive_coevolution.md`` CE-31.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np

from llive.perf.evolutionary.individual import Individual
from llive.perf.evolutionary.population import Population

# ---------------------------------------------------------------------------
# Non-dominated sort
# ---------------------------------------------------------------------------


def _dominates(
    a: list[float],
    b: list[float],
    higher_is_better: list[bool],
) -> bool:
    """``a`` が ``b`` を pareto-dominate するかを判定.

    a が全 objective で b 以上で, 少なくとも 1 つで真に良い場合 True.
    """
    at_least_one_better = False
    for i, hib in enumerate(higher_is_better):
        if hib:
            if a[i] < b[i]:
                return False
            if a[i] > b[i]:
                at_least_one_better = True
        else:
            if a[i] > b[i]:
                return False
            if a[i] < b[i]:
                at_least_one_better = True
    return at_least_one_better


def non_dominated_sort(
    individuals: Iterable[Individual],
    *,
    objectives: tuple[str, ...],
    higher_is_better: tuple[bool, ...] | None = None,
) -> list[list[Individual]]:
    """個体を Pareto front に分割.

    Parameters
    ----------
    individuals : Iterable[Individual]
    objectives : tuple[str, ...]
        breakdown のキー列. 各 individual.fitness.breakdown[key] が値.
    higher_is_better : tuple[bool, ...] | None
        各 objective が大きい方が良いか. None なら全 True.

    Returns
    -------
    list[list[Individual]]
        rank 0 が Pareto front. rank 1, 2, ... と続く.
    """
    inds = list(individuals)
    n = len(inds)
    if n == 0:
        return []
    if higher_is_better is None:
        higher_is_better = tuple(True for _ in objectives)
    if len(higher_is_better) != len(objectives):
        raise ValueError("higher_is_better length must equal objectives length")

    # 各個体の objective 値 vector
    obj_vectors: list[list[float]] = []
    for ind in inds:
        if ind.fitness is None:
            obj_vectors.append([float("-inf")] * len(objectives))
            continue
        bd = ind.fitness.breakdown
        obj_vectors.append([float(bd.get(k, float("-inf"))) for k in objectives])

    hib = list(higher_is_better)

    # dominate count + dominated set
    n_dominated = [0] * n
    dominates_who: list[list[int]] = [[] for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            if _dominates(obj_vectors[i], obj_vectors[j], hib):
                dominates_who[i].append(j)
            elif _dominates(obj_vectors[j], obj_vectors[i], hib):
                n_dominated[i] += 1

    # rank 0: n_dominated=0
    fronts: list[list[Individual]] = []
    current = [i for i in range(n) if n_dominated[i] == 0]
    fronts.append([inds[i] for i in current])
    while current:
        next_front = []
        for i in current:
            for j in dominates_who[i]:
                n_dominated[j] -= 1
                if n_dominated[j] == 0:
                    next_front.append(j)
        if not next_front:
            break
        fronts.append([inds[i] for i in next_front])
        current = next_front
    return fronts


# ---------------------------------------------------------------------------
# Crowding distance
# ---------------------------------------------------------------------------


def crowding_distance(
    front: list[Individual],
    *,
    objectives: tuple[str, ...],
) -> dict[str, float]:
    """同 rank 内の crowding distance (NSGA-II).

    各 objective ごとに sort し, 隣接距離を集計. 端点は infty.

    Returns
    -------
    dict[individual_id, distance]
    """
    n = len(front)
    if n <= 2:
        return {ind.individual_id: float("inf") for ind in front}
    distances: dict[str, float] = {ind.individual_id: 0.0 for ind in front}
    for key in objectives:
        scored = []
        for ind in front:
            if ind.fitness is None:
                continue
            v = float(ind.fitness.breakdown.get(key, float("-inf")))
            # 非有限 (NaN/Inf) は crowding 計算に使えないため除外。該当個体の
            # distance は初期値 0.0 のまま = 最劣扱いで淘汰されやすい (B-NUM-1).
            if np.isfinite(v):
                scored.append((v, ind.individual_id))
        if len(scored) < 2:
            continue
        scored.sort(key=lambda t: t[0])
        v_min = scored[0][0]
        v_max = scored[-1][0]
        rng_val = v_max - v_min
        # 端点は infty
        distances[scored[0][1]] = float("inf")
        distances[scored[-1][1]] = float("inf")
        if rng_val <= 0:
            continue
        for i in range(1, len(scored) - 1):
            prev_v = scored[i - 1][0]
            next_v = scored[i + 1][0]
            distances[scored[i][1]] += (next_v - prev_v) / rng_val
    return distances


# ---------------------------------------------------------------------------
# NSGA-II Selection
# ---------------------------------------------------------------------------


@dataclass
class NSGA2Selection:
    """NSGA-II crowded tournament selection.

    手順:
    1. 2 個体をランダム選び, **front rank が小さい方** が勝ち
    2. 同 rank なら **crowding distance が大きい方** が勝ち

    Attributes
    ----------
    objectives : tuple[str, ...]
        対象 objective key 列.
    higher_is_better : tuple[bool, ...] | None
        各 objective の方向. None なら全 True.

    Note
    ----
    selection 呼び出しのたびに sort を回すのは O(N²M). 1 世代で 1 回だけ
    sort して selection 多数回繰り返す方が効率的. 本実装は **selection
    呼び出しごとに sort を再計算する設計** (簡素優先). 大集団 (>200) では
    ``compute_ranks_and_crowding(population)`` をキャッシュする option を
    検討 (TODO).
    """

    objectives: tuple[str, ...]
    higher_is_better: tuple[bool, ...] | None = None

    def __post_init__(self) -> None:
        if not self.objectives:
            raise ValueError("objectives must be non-empty")

    def __call__(
        self,
        population: Population,
        rng: np.random.Generator,
    ) -> Individual:
        fronts = non_dominated_sort(
            population.individuals,
            objectives=self.objectives,
            higher_is_better=self.higher_is_better,
        )
        if not fronts:
            raise ValueError("population is empty")
        # 個体 → rank
        rank_of: dict[str, int] = {}
        for r, front in enumerate(fronts):
            for ind in front:
                rank_of[ind.individual_id] = r
        # 個体 → crowding distance
        dist_of: dict[str, float] = {}
        for front in fronts:
            d = crowding_distance(front, objectives=self.objectives)
            dist_of.update(d)

        # 2 個体ランダム選択して勝者
        inds = population.individuals
        if len(inds) == 1:
            return inds[0]
        i, j = rng.choice(len(inds), size=2, replace=False)
        a, b = inds[int(i)], inds[int(j)]
        rank_a = rank_of[a.individual_id]
        rank_b = rank_of[b.individual_id]
        if rank_a < rank_b:
            return a
        if rank_b < rank_a:
            return b
        # 同 rank
        dist_a = dist_of[a.individual_id]
        dist_b = dist_of[b.individual_id]
        if dist_a > dist_b:
            return a
        if dist_b > dist_a:
            return b
        # tie-break: random
        return a if rng.random() < 0.5 else b


__all__ = [
    "NSGA2Selection",
    "crowding_distance",
    "non_dominated_sort",
]
