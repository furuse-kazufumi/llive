# SPDX-License-Identifier: Apache-2.0
"""MetaEvolutionLoop — 進化アルゴリズム自体を UCB1 で選択する skeleton (llive v0.I EV-22).

[[meta_chromosome.py]] の `MetaChromosome` を **state-aware に運用** するための
ループ skeleton. 各世代で:

1. **algorithm selection**: 登録された候補 `MetaChromosome` を UCB1 score で 1 つ選ぶ
2. **(sandbox) apply**: 選ばれた chromosome の `algorithm_id` で集団を 1 世代進める
   - skeleton では実 dispatch は **保留** (callable レジストリで mock)
3. **delta record**: fitness 改善量を chromosome 別 history に記録
4. **(option) neighborhood expansion**: 高 score chromosome の近傍を新 candidate として追加

形式化 (`docs/requirements_v0.I_meta_evolution_and_cross_substrate.md` §3.2):

```
P_{t+1}    = A_t(P_t)
Δ_t        = F(P_{t+1}) - F(P_t)
score(A)   = mean_Δ(A) + c · sqrt(2 ln N / n_A)
P(A'|A_t)  ∝ exp(-(K(A')-K(A_t))/T) · max(Δ_{t-N..t}, ε)
```

Status (2026-05-22 着地): **skeleton**. 以下を実装:

- ✅ MetaLoopState (use_count + cum_delta + history)
- ✅ register_chromosome (cold start で +inf UCB)
- ✅ select_next (UCB1 score 計算 + 引き)
- ✅ record_delta (delta 蓄積)
- ✅ kolmogorov_proxy
- ✅ expand_neighborhood (高 score 候補の近傍追加)
- 🚧 apply (callable dispatch — skeleton では mock-only)
- 🚧 EvolutionLoop 統合 (EV-22 残)
- 🚧 sandbox AST 実行 (EV-23 以降, subprocess + timeout + memory limit)

References:

- Auer, P., Cesa-Bianchi, N., Fischer, P. (2002). *Finite-time Analysis of the
  Multiarmed Bandit Problem.* Machine Learning 47.
- Schmidhuber (2003) Gödel Machines.
- Cilibrasi, R., Vitanyi, P. (2005). *Clustering by Compression.* IEEE Trans.
  Info. Theory 51 (gzip-based K proxy の基礎).
- llive `docs/requirements_v0.I_meta_evolution_and_cross_substrate.md` §3.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from llive.perf.evolutionary.meta_chromosome import (
    KNOWN_ALGORITHM_IDS,
    MetaChromosome,
    ucb1_score,
)

# ---------------------------------------------------------------------------
# State per chromosome
# ---------------------------------------------------------------------------


@dataclass
class _ChromosomeStats:
    """UCB1 state per candidate chromosome (mutable, internal)."""

    use_count: int = 0
    cum_delta: float = 0.0
    deltas: list[float] = field(default_factory=list)
    last_used_gen: int = -1

    @property
    def mean_delta(self) -> float:
        if self.use_count == 0:
            return 0.0
        return self.cum_delta / self.use_count

    def record(self, delta: float, generation: int) -> None:
        self.use_count += 1
        self.cum_delta += float(delta)
        self.deltas.append(float(delta))
        self.last_used_gen = int(generation)

    def recent_mean_delta(self, window: int) -> float:
        """直近 window 世代の平均 delta. window が deltas より長ければ全体平均."""
        if not self.deltas:
            return 0.0
        slice_ = self.deltas[-window:] if window > 0 else self.deltas
        return float(np.mean(slice_))


# ---------------------------------------------------------------------------
# Loop state
# ---------------------------------------------------------------------------


@dataclass
class MetaLoopState:
    """MetaEvolutionLoop の internal state.

    chromosome key は `MetaChromosome` の hash (frozen dataclass なので hashable).
    """

    candidates: dict[MetaChromosome, _ChromosomeStats] = field(default_factory=dict)
    generation: int = 0
    exploration_c: float = math.sqrt(2.0)
    recent_window: int = 10  # UCB の mean に直近 N 世代の窓を使う場合

    # ----- registry -----

    def register(self, chromosome: MetaChromosome) -> None:
        """chromosome を candidate 集合に追加. 既存なら no-op."""
        if chromosome not in self.candidates:
            self.candidates[chromosome] = _ChromosomeStats()

    def register_all(self, chromosomes: Iterable[MetaChromosome]) -> None:
        for c in chromosomes:
            self.register(c)

    # ----- query -----

    @property
    def total_use_count(self) -> int:
        return sum(s.use_count for s in self.candidates.values())

    def stats(self, chromosome: MetaChromosome) -> _ChromosomeStats:
        return self.candidates[chromosome]

    def scores(self) -> dict[MetaChromosome, float]:
        """全 candidate の UCB1 score (use_count == 0 は +inf)."""
        total = self.total_use_count
        return {
            c: ucb1_score(
                mean_delta=s.recent_mean_delta(self.recent_window),
                use_count=s.use_count,
                total_gen=total,
                exploration_c=self.exploration_c,
            )
            for c, s in self.candidates.items()
        }


# ---------------------------------------------------------------------------
# Loop
# ---------------------------------------------------------------------------

#: アルゴリズム実体. (chromosome, rng) → fitness_delta (1 世代の改善量).
#: skeleton では mock を渡せる形で抽象化.
AlgorithmFn = Callable[[MetaChromosome, np.random.Generator], float]


@dataclass
class MetaEvolutionLoop:
    """進化アルゴリズム自体を UCB1 で選ぶ skeleton loop.

    使い方 (skeleton):

    >>> import numpy as np
    >>> from llive.perf.evolutionary import MetaChromosome, MetaEvolutionLoop
    >>> rng = np.random.default_rng(0)
    >>> loop = MetaEvolutionLoop()
    >>> loop.register(MetaChromosome.default())
    >>> chosen = loop.select_next(rng)
    >>> # apply chosen.algorithm_id ... then:
    >>> loop.record_delta(chosen, fitness_delta=0.05)

    実 dispatch (EvolutionLoop に各 algorithm_id を渡す部分) は EV-22 残.
    sandbox AST 実行は EV-23 以降.
    """

    state: MetaLoopState = field(default_factory=MetaLoopState)
    algorithm_dispatch: dict[str, AlgorithmFn] = field(default_factory=dict)
    expansion_threshold: float = 0.0  # mean_Δ >= this → 近傍 expand

    # ----- registry passthrough -----

    def register(self, chromosome: MetaChromosome) -> None:
        self.state.register(chromosome)

    def register_dispatch(self, algorithm_id: str, fn: AlgorithmFn) -> None:
        """algorithm_id に対する callable を登録. mock も実装も同形式."""
        if algorithm_id not in KNOWN_ALGORITHM_IDS:
            raise ValueError(
                f"unknown algorithm_id '{algorithm_id}' "
                f"(known={KNOWN_ALGORITHM_IDS})"
            )
        self.algorithm_dispatch[algorithm_id] = fn

    # ----- selection -----

    def select_next(self, rng: np.random.Generator | None = None) -> MetaChromosome:
        """UCB1 score 最大 chromosome を選ぶ. tie は rng で uniform 引き.

        Args:
            rng: tie-breaking 用. None なら最初に見つかった max を選ぶ.

        Returns:
            選ばれた `MetaChromosome`.

        Raises:
            RuntimeError: candidates が空のとき.
        """
        if not self.state.candidates:
            raise RuntimeError("no candidate chromosomes registered")

        scores = self.state.scores()
        # +inf を含むため math.isinf 対応
        max_score = max(scores.values())
        winners = [c for c, s in scores.items() if s == max_score or (
            math.isinf(s) and math.isinf(max_score)
        )]
        if len(winners) == 1:
            return winners[0]
        if rng is None:
            return winners[0]
        idx = int(rng.integers(0, len(winners)))
        return winners[idx]

    # ----- record -----

    def record_delta(self, chromosome: MetaChromosome, fitness_delta: float) -> None:
        """1 世代分の fitness 改善量を記録."""
        if chromosome not in self.state.candidates:
            raise RuntimeError(f"chromosome not registered: {chromosome}")
        self.state.candidates[chromosome].record(fitness_delta, self.state.generation)
        self.state.generation += 1

    # ----- neighborhood expansion -----

    def expand_neighborhood(
        self,
        rng: np.random.Generator,
        max_new: int = 1,
        step_size: float = 0.1,
    ) -> list[MetaChromosome]:
        """高 score (mean_Δ >= expansion_threshold) chromosome の近傍を candidate 化.

        ループが進むにつれ algorithm 空間を **能動的に拡張** する.
        Schmidhuber 風 self-improvement のための skeleton.

        Returns:
            新規追加された chromosome list (空なら expand 不要).
        """
        eligible = [
            c
            for c, s in self.state.candidates.items()
            if s.recent_mean_delta(self.state.recent_window) >= self.expansion_threshold
            and s.use_count > 0
        ]
        if not eligible:
            return []
        new_candidates: list[MetaChromosome] = []
        # rng で eligible から選択 → 近傍生成
        for _ in range(max_new):
            parent = eligible[int(rng.integers(0, len(eligible)))]
            neighbor = parent.sample_neighborhood(rng, step_size=step_size)
            if neighbor not in self.state.candidates:
                self.state.candidates[neighbor] = _ChromosomeStats()
                new_candidates.append(neighbor)
        return new_candidates

    # ----- apply (skeleton: callable dispatch) -----

    def apply(
        self,
        chromosome: MetaChromosome,
        rng: np.random.Generator,
    ) -> float:
        """algorithm_id に対応する callable を呼んで 1 世代分の delta を返す.

        skeleton では実 population を持たない. 将来 EvolutionLoop と統合
        した段階で population → fitness 計算 → delta を返す本格 dispatch
        になる. 現状は mock を `register_dispatch` で登録して run.

        Raises:
            RuntimeError: algorithm_id に dispatch が登録されていない.
        """
        fn = self.algorithm_dispatch.get(chromosome.algorithm_id)
        if fn is None:
            raise RuntimeError(
                f"no dispatch registered for algorithm_id '{chromosome.algorithm_id}'. "
                f"register via register_dispatch()."
            )
        delta = float(fn(chromosome, rng))
        self.record_delta(chromosome, delta)
        return delta

    # ----- snapshot / inspection -----

    def snapshot(self) -> dict[str, Any]:
        """state を JSON 化可能な dict に. observability / 再現性のため."""
        return {
            "generation": self.state.generation,
            "exploration_c": self.state.exploration_c,
            "recent_window": self.state.recent_window,
            "candidates": [
                {
                    "chromosome": c.to_dict(),
                    "use_count": s.use_count,
                    "cum_delta": s.cum_delta,
                    "deltas": list(s.deltas),
                    "last_used_gen": s.last_used_gen,
                    "k_proxy": c.kolmogorov_proxy(),
                }
                for c, s in self.state.candidates.items()
            ],
        }


__all__ = [
    "AlgorithmFn",
    "MetaEvolutionLoop",
    "MetaLoopState",
]
