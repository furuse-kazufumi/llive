# SPDX-License-Identifier: Apache-2.0
"""Population — 個体集団 + 世代管理 + RNG seed (llive v0.B EV-01).

thread-safe (RLock) — 並列評価で aggregate するため. 再現性のために RNG seed
を必ず明示的に渡す.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from llive.perf.evolutionary.genome import Genome, GenomeBounds
from llive.perf.evolutionary.individual import Individual


@dataclass
class PopulationStats:
    """1 世代の集約統計."""

    generation: int
    n_individuals: int
    best_score: float
    mean_score: float
    std_score: float
    median_score: float
    diversity_l2: float  # pairwise L2 distance mean (多様性指標)
    seed: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "generation": int(self.generation),
            "n_individuals": int(self.n_individuals),
            "best_score": float(self.best_score),
            "mean_score": float(self.mean_score),
            "std_score": float(self.std_score),
            "median_score": float(self.median_score),
            "diversity_l2": float(self.diversity_l2),
            "seed": int(self.seed),
        }


@dataclass
class Population:
    """個体の集団 + 世代管理 + RNG seed.

    各世代の RNG seed が ``self.generation_seeds`` に蓄積されるので,
    後から完全再現できる.
    """

    individuals: list[Individual]
    bounds: GenomeBounds
    generation: int = 0
    seed: int = 0
    generation_seeds: list[int] = field(default_factory=list)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)

    # -- factories ---------------------------------------------------------

    @classmethod
    def random(
        cls,
        bounds: GenomeBounds,
        size: int,
        seed: int,
        labels: tuple[str, ...] = (),
    ) -> Population:
        """size 個体を bounds 内 uniform random で生成."""
        if size <= 0:
            raise ValueError("size must be > 0")
        rng = np.random.default_rng(seed)
        individuals = [
            Individual.from_genome(Genome.random(bounds, rng, labels=labels), birth_generation=0)
            for _ in range(size)
        ]
        return cls(
            individuals=individuals,
            bounds=bounds,
            generation=0,
            seed=seed,
            generation_seeds=[seed],
        )

    # -- view --------------------------------------------------------------

    @property
    def size(self) -> int:
        return len(self.individuals)

    def best(self) -> Individual:
        """現世代の best 個体. 全員未評価なら最初の個体を返す."""
        with self._lock:
            evaluated = [ind for ind in self.individuals if ind.fitness is not None]
            if not evaluated:
                return self.individuals[0]
            return max(evaluated, key=lambda ind: ind.score)

    def sorted_by_score_desc(self) -> list[Individual]:
        """score 降順 sort された個体 list (新 list)."""
        with self._lock:
            return sorted(self.individuals, key=lambda ind: ind.score, reverse=True)

    # -- stats -------------------------------------------------------------

    def compute_stats(self) -> PopulationStats:
        with self._lock:
            scores = np.asarray(
                [ind.score for ind in self.individuals if ind.fitness is not None],
                dtype=np.float64,
            )
            if scores.size == 0:
                best_s = mean_s = std_s = med_s = float("-inf")
            else:
                best_s = float(scores.max())
                mean_s = float(scores.mean())
                std_s = float(scores.std())
                med_s = float(np.median(scores))
            diversity = self._diversity_l2_locked()
            seed = self.generation_seeds[-1] if self.generation_seeds else self.seed
            return PopulationStats(
                generation=self.generation,
                n_individuals=len(self.individuals),
                best_score=best_s,
                mean_score=mean_s,
                std_score=std_s,
                median_score=med_s,
                diversity_l2=diversity,
                seed=seed,
            )

    def _diversity_l2_locked(self) -> float:
        """全 pair の L2 距離の平均. O(N^2 * D) のため大集団では sub-sample 推奨."""
        n = len(self.individuals)
        if n < 2:
            return 0.0
        vectors = np.stack([ind.genome.as_array() for ind in self.individuals], axis=0)
        # pairwise L2: ((v_i - v_j)^2).sum(-1)
        diff = vectors[:, None, :] - vectors[None, :, :]
        dists = np.sqrt(np.sum(diff * diff, axis=-1))
        # 対角を除いた平均
        mask = ~np.eye(n, dtype=bool)
        return float(dists[mask].mean()) if mask.any() else 0.0

    # -- mutation: 次世代へ ---------------------------------------------

    def replace(self, new_individuals: list[Individual], new_seed: int) -> None:
        """次世代の個体で in-place 置換. generation を +1, seed を append."""
        with self._lock:
            self.individuals = list(new_individuals)
            self.generation += 1
            self.seed = new_seed
            self.generation_seeds.append(new_seed)

    # -- serialize ---------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "individuals": [ind.to_dict() for ind in self.individuals],
            "bounds": self.bounds.to_dict(),
            "generation": int(self.generation),
            "seed": int(self.seed),
            "generation_seeds": list(self.generation_seeds),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Population:
        return cls(
            individuals=[Individual.from_dict(d) for d in data["individuals"]],
            bounds=GenomeBounds.from_dict(data["bounds"]),
            generation=int(data.get("generation", 0)),
            seed=int(data.get("seed", 0)),
            generation_seeds=[int(s) for s in data.get("generation_seeds", [])],
        )


__all__ = ["Population", "PopulationStats"]
