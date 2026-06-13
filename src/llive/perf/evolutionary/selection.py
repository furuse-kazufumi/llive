# SPDX-License-Identifier: Apache-2.0
"""Selection — 親選択演算子 (llive v0.B EV-03).

3 種: Tournament / Elitism / Roulette. すべて ``(Population, rng) -> Individual``
の callable shape を持つ.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from llive.perf.evolutionary.individual import Individual
from llive.perf.evolutionary.population import Population


@dataclass(frozen=True)
class TournamentSelection:
    """k 体 random pick → best 1 体を親に. k=3 が default."""

    k: int = 3

    def __post_init__(self) -> None:
        if self.k < 1:
            raise ValueError("k must be >= 1")

    def __call__(self, pop: Population, rng: np.random.Generator) -> Individual:
        if pop.size == 0:
            raise ValueError("empty population")
        indices = rng.integers(low=0, high=pop.size, size=self.k)
        contenders = [pop.individuals[int(i)] for i in indices]
        return max(contenders, key=lambda ind: ind.score)


@dataclass(frozen=True)
class RouletteSelection:
    """fitness 比例ルーレット. temperature で softmax を緩和できる."""

    temperature: float = 1.0

    def __post_init__(self) -> None:
        if self.temperature <= 0:
            raise ValueError("temperature must be > 0")

    def __call__(self, pop: Population, rng: np.random.Generator) -> Individual:
        if pop.size == 0:
            raise ValueError("empty population")
        scores = np.asarray([ind.score for ind in pop.individuals], dtype=np.float64)
        # -inf が混じると softmax が破綻するので有限値だけで normalize
        finite_mask = np.isfinite(scores)
        if not finite_mask.any():
            return pop.individuals[int(rng.integers(0, pop.size))]
        # 最大値で shift してから softmax (数値安定)
        scaled = (scores - np.max(scores[finite_mask])) / self.temperature
        weights = np.where(finite_mask, np.exp(scaled), 0.0)
        weights /= weights.sum()
        idx = int(rng.choice(pop.size, p=weights))
        return pop.individuals[idx]


@dataclass(frozen=True)
class ElitismSelection:
    """上位 N 体をそのまま次世代へ. 通常は他 selection と組み合わせて使う."""

    top_n: int = 2

    def __post_init__(self) -> None:
        if self.top_n < 0:
            raise ValueError("top_n must be >= 0")

    def select(self, pop: Population) -> list[Individual]:
        """上位 top_n 体を返す (score 降順)."""
        if pop.size == 0 or self.top_n == 0:
            return []
        return pop.sorted_by_score_desc()[: self.top_n]


__all__ = ["ElitismSelection", "RouletteSelection", "TournamentSelection"]
