# SPDX-License-Identifier: Apache-2.0
"""Mutual-score pairing + Lexicase selection (v0.E CE-30/CE-34, 洞察 7 直接対応).

ユーザー洞察 (2026-05-21):
    「互いの採点結果が高いものはゲノム交配で子が残せる形にすると良い.
    一つの評価指標だけで子が残る形にすると単純な収束で新しい種が
    生まれない.」

= assortative mating (Darwin's sexual selection の数式化) + Lexicase selection
(単一 fitness 収束回避).

設計:

- ``MutualScorePairSelector``: PeerEvaluationMatrix から
  ``mutual_score(i,j) = M[i,j] + M[j,i]`` を計算し, 親 pair を softmax / top-k
  確率分布で sampling する.
- ``LexicaseSelection``: FitnessReport.breakdown の複数 criterion を random
  order で試し, 各 step で worst を脱落させる. 単一 score での収束を避ける.

参照:
- Helmuth et al. (2014). Solving uncompromising problems with lexicase selection.
- Deb, K. (2002). NSGA-II.
- Stanley & Miikkulainen (2002). NEAT speciation.

要件根拠: ``docs/requirements_v0.E_competitive_coevolution.md`` 0.9 節 CE-30/34.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np

from llive.perf.evolutionary.individual import Individual
from llive.perf.evolutionary.peer_evaluation import PeerEvaluationMatrix
from llive.perf.evolutionary.population import Population


# ---------------------------------------------------------------------------
# CE-30 — MutualScoreBasedPairing
# ---------------------------------------------------------------------------


@dataclass
class MutualScorePairSelector:
    """peer evaluation matrix から **互いに高得点を付け合う pair** を選ぶ.

    ``mutual_score(i, j) = (M[i, j] + M[j, i]) / 2``
    (NaN は 0 として扱う). 全 pair の score から softmax で確率分布を構成し
    sampling する.

    Attributes
    ----------
    matrix : PeerEvaluationMatrix
        最新世代の peer 採点行列.
    temperature : float
        softmax 温度. 低いほど高 score pair に集中. default 1.0.
    min_mutual : float
        ``mutual_score`` の下限. 下回る pair は確率 0.
    rng_fallback_uniform : bool
        全 pair が min_mutual を下回ったときに uniform random を返すか.
        default True.
    """

    matrix: PeerEvaluationMatrix
    temperature: float = 1.0
    min_mutual: float = 0.0
    rng_fallback_uniform: bool = True

    def __post_init__(self) -> None:
        if self.temperature <= 0:
            raise ValueError("temperature must be > 0")

    # ---------- public API ----------------------------------------------

    def mutual_score_matrix(self) -> np.ndarray:
        """``(N, N)`` の mutual_score matrix を返す. NaN は 0 扱い."""
        m = np.nan_to_num(self.matrix.matrix, nan=0.0)
        return (m + m.T) / 2.0

    def select_pair(
        self,
        population: Population,
        rng: np.random.Generator,
    ) -> tuple[Individual, Individual]:
        """親 pair を 1 組返す.

        確率は softmax(mutual_score / temperature) で構成. self-pair (i==j) は
        確率 0.
        """
        agents = self.matrix.agent_ids
        n = len(agents)
        if n < 2:
            raise ValueError("need at least 2 individuals to form a pair")
        ms = self.mutual_score_matrix()
        # i==j を排除 + min_mutual 未満を排除
        mask = np.ones_like(ms, dtype=bool)
        np.fill_diagonal(mask, False)
        mask &= ms >= self.min_mutual

        if not mask.any():
            if not self.rng_fallback_uniform:
                raise ValueError("no pair satisfies min_mutual threshold")
            # uniform fallback
            idx_i = int(rng.integers(0, n))
            idx_j = int(rng.integers(0, n))
            while idx_j == idx_i:
                idx_j = int(rng.integers(0, n))
        else:
            # softmax over masked pairs
            flat_scores = ms.flatten()
            flat_mask = mask.flatten()
            logits = (flat_scores - flat_scores[flat_mask].max()) / self.temperature
            probs = np.where(flat_mask, np.exp(logits), 0.0)
            probs /= probs.sum()
            choice = int(rng.choice(n * n, p=probs))
            idx_i, idx_j = divmod(choice, n)

        # agent_id → Individual を逆引き
        id_to_ind = {ind.individual_id: ind for ind in population.individuals}
        return id_to_ind[agents[idx_i]], id_to_ind[agents[idx_j]]

    def select_pairs(
        self,
        population: Population,
        rng: np.random.Generator,
        *,
        n_pairs: int,
    ) -> list[tuple[Individual, Individual]]:
        """n_pairs 個の親 pair を返す."""
        return [self.select_pair(population, rng) for _ in range(n_pairs)]


# ---------------------------------------------------------------------------
# CE-34 — Lexicase Selection
# ---------------------------------------------------------------------------


@dataclass
class LexicaseSelection:
    """Lexicase Selection (Helmuth et al. 2014).

    FitnessReport.breakdown の複数 criterion を **random order** で試し,
    各 step で その criterion における worst を脱落させる. 単一 fitness では
    無視される minority criterion でも勝ち抜くチャンスがあるため
    **diversity preservation 効果**が高い.

    Attributes
    ----------
    criteria : tuple[str, ...]
        評価するブレイクダウンキー (例: ("peer_score", "novelty",
        "factor_coverage")). 各 individual.fitness.breakdown に該当キーが
        無ければそのキーはその individual で skip.
    epsilon : float
        「同点扱い」する許容範囲. 0 なら厳密 best, 0.01 なら 1% 以内を残す.
        default 1e-6.
    higher_is_better : bool
        True (default) なら大きいほど良い. False なら逆.
    """

    criteria: tuple[str, ...]
    epsilon: float = 1e-6
    higher_is_better: bool = True

    def __post_init__(self) -> None:
        if not self.criteria:
            raise ValueError("criteria must be non-empty")
        if self.epsilon < 0:
            raise ValueError("epsilon must be >= 0")

    # ---------- public API ----------------------------------------------

    def __call__(
        self,
        population: Population,
        rng: np.random.Generator,
    ) -> Individual:
        """1 個体を Lexicase で選ぶ.

        手順:
        1. criteria を random shuffle
        2. 候補集合 = 全個体
        3. 各 criterion で候補集合から `best ± epsilon` 以外を脱落
        4. 候補集合が 1 個になれば return, 全 criterion 試して複数残ったら random
        """
        candidates = list(population.individuals)
        if not candidates:
            raise ValueError("population is empty")
        order = list(self.criteria)
        rng.shuffle(order)
        for criterion in order:
            if len(candidates) <= 1:
                break
            scores: list[tuple[float, Individual]] = []
            for ind in candidates:
                if ind.fitness is None or criterion not in ind.fitness.breakdown:
                    continue
                scores.append((float(ind.fitness.breakdown[criterion]), ind))
            if not scores:
                continue
            if self.higher_is_better:
                best = max(s for s, _ in scores)
                candidates = [ind for s, ind in scores if s >= best - self.epsilon]
            else:
                best = min(s for s, _ in scores)
                candidates = [ind for s, ind in scores if s <= best + self.epsilon]
            if not candidates:
                candidates = [ind for _, ind in scores]
        if len(candidates) == 1:
            return candidates[0]
        return candidates[int(rng.integers(0, len(candidates)))]


__all__ = [
    "LexicaseSelection",
    "MutualScorePairSelector",
]
