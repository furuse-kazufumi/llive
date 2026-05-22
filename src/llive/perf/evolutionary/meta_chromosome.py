# SPDX-License-Identifier: Apache-2.0
"""MetaChromosome — 進化アルゴリズム自体を遺伝対象として保持する chromosome (llive v0.I EV-21).

llive v0.D の MetaMutation ([[meta_mutation.py]] / Promptbreeder Fernando 2023) は
**1 dim の strategy id** を genome 内に埋める段階だった. 本 chromosome は
**進化アルゴリズム全体**:

- 層別突然変異率 (per-layer mutation rate; v0.F C-impl / C-prompt / C-meta)
- crossover strategy (intra / cross / segment / bit)
- selection pressure (truncation top-N 比率)
- novelty weight (M / (N+M); v0.F 柱 B)
- cluster quota (similarity quota; v0.F 柱 D)
- meta mutation decay (メタ層自体の自己制限)
- algorithm_id (skeleton ; 将来 algorithm_encoding bytes に拡張)

を 1 つの frozen dataclass にまとめる. Schmidhuber OOPS (2003) / Hutter AIXI
(2005) / Real et al. AutoML-Zero (2020) / Wang et al. Promptbreeder (2024) の
計算可能近似として gzip ベース Kolmogorov complexity を提供する.

形式化 (詳細は `docs/requirements_v0.I_meta_evolution_and_cross_substrate.md`
§3.2):

```
score(A) = mean_Δ(A) + c · sqrt(2 ln(total_gen) / use_count(A))
```

UCB1 探索 score の `mean_Δ` 部分はループ側 ([[meta_loop.py]]) が保持. 本
chromosome は **state-less な遺伝表現** のみを担当する.

References:

- Schmidhuber, J. (2003). *Gödel Machines: Self-Referential Universal Problem
  Solvers Making Provably Optimal Self-Improvements.*
  https://people.idsia.ch/~juergen/goedelmachine.html
- Hutter, M. (2005). *Universal Artificial Intelligence.* Springer.
- Real, E. et al. (2020). [AutoML-Zero](https://arxiv.org/abs/2003.03384).
- Wang, R. et al. (2024). Promptbreeder ([arXiv:2309.16797](https://arxiv.org/abs/2309.16797)).
- llive `docs/requirements_v0.I_meta_evolution_and_cross_substrate.md`.

Status (2026-05-22 着地): skeleton. データ構造 + バリデーション +
serialization + neighborhood sampling + Kolmogorov proxy のみ. 実 sandbox
AST 実行 + EvolutionLoop 統合は次セッション以降 (EV-22 残 / EV-23 以降).
"""

from __future__ import annotations

import gzip
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: 既知 crossover strategies (skeleton). 将来 v0.F の `C-impl` / `C-prompt`
#: 層内 / 層間 crossover が確定したら拡張.
KNOWN_CROSSOVER_STRATEGIES: tuple[str, ...] = (
    "intra",       # 同層内 crossover
    "cross",       # 層間 crossover
    "segment",     # 染色体内 gene segment swap
    "bit",         # bit-level
    "uniform",     # 一様 (既存 UniformCrossover 互換)
)

#: 既知 algorithm id (skeleton レジストリ). 将来 algorithm_encoding bytes
#: の hash で dispatch する形に置き換わる.
KNOWN_ALGORITHM_IDS: tuple[str, ...] = (
    "tournament_gauss",        # baseline (v0.B 既存)
    "tournament_meta",         # MetaMutation 含む (v0.D)
    "nsga2_novelty",           # 多目的 + novelty (v0.F 柱 B)
    "map_elites_niche",        # niche illumination (Mouret&Clune 2015)
    "self_adaptive_sigma",     # 自己適応 σ (v0.D 既存)
)

#: ループ層 (chromosome name → mutation rate のキー)
LAYER_NAMES: tuple[str, ...] = ("c_impl", "c_prompt", "c_meta")


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MetaChromosome:
    """進化アルゴリズム自体を遺伝対象として保持する frozen chromosome.

    Genome の 3 階目 (v0.I EV-21). v0.F 2 階建てゲノム (C-impl, C-prompt) が
    実装されたら, `Genome = (C-impl, C-prompt, MetaChromosome)` の 3 階建てに
    昇格する.

    Skeleton 段階では既存 v0.B Genome (scalar 19 dim) と **stand-alone** で
    共存し, MetaEvolutionLoop が algorithm dispatch に使う.
    """

    #: 層別突然変異率. dict ではなく tuple (frozen のため). LAYER_NAMES 順.
    mutation_rate_per_layer: tuple[float, float, float]

    #: crossover 戦略名 (KNOWN_CROSSOVER_STRATEGIES のいずれか).
    crossover_strategy: str

    #: truncation top-N 比率 (0.0-1.0). high = 強選択.
    selection_pressure: float

    #: novelty top-M / (top-N + top-M) の M 比率. v0.F 柱 B Multi-Objective.
    novelty_weight: float

    #: similarity quota (1 cluster あたり最大個体数). v0.F 柱 D crowding.
    cluster_quota: int

    #: メタ層自体の自己制限率 (0.0-1.0). high = メタ層変異を抑える.
    meta_mutation_decay: float

    #: algorithm id (KNOWN_ALGORITHM_IDS のいずれか). 将来 AST encoded bytes に拡張.
    algorithm_id: str

    #: (optional) algorithm 固有 hyperparam. JSON 化可能な dict のみ.
    algorithm_params: tuple[tuple[str, float], ...] = field(default_factory=tuple)

    # ----- validation -----------------------------------------------------

    def __post_init__(self) -> None:
        # mutation rates
        if len(self.mutation_rate_per_layer) != len(LAYER_NAMES):
            raise ValueError(
                f"mutation_rate_per_layer len {len(self.mutation_rate_per_layer)} "
                f"!= {len(LAYER_NAMES)} (layers={LAYER_NAMES})"
            )
        for layer, rate in zip(LAYER_NAMES, self.mutation_rate_per_layer, strict=True):
            if not 0.0 <= rate <= 1.0:
                raise ValueError(f"mutation rate for layer '{layer}' = {rate} not in [0,1]")

        # crossover
        if self.crossover_strategy not in KNOWN_CROSSOVER_STRATEGIES:
            raise ValueError(
                f"unknown crossover_strategy '{self.crossover_strategy}' "
                f"(known={KNOWN_CROSSOVER_STRATEGIES})"
            )

        # selection
        if not 0.0 < self.selection_pressure <= 1.0:
            raise ValueError(
                f"selection_pressure {self.selection_pressure} not in (0,1]"
            )

        # novelty
        if not 0.0 <= self.novelty_weight <= 1.0:
            raise ValueError(f"novelty_weight {self.novelty_weight} not in [0,1]")

        # cluster quota
        if self.cluster_quota < 1:
            raise ValueError(f"cluster_quota {self.cluster_quota} must be >= 1")

        # meta decay
        if not 0.0 <= self.meta_mutation_decay <= 1.0:
            raise ValueError(
                f"meta_mutation_decay {self.meta_mutation_decay} not in [0,1]"
            )

        # algorithm id
        if self.algorithm_id not in KNOWN_ALGORITHM_IDS:
            raise ValueError(
                f"unknown algorithm_id '{self.algorithm_id}' "
                f"(known={KNOWN_ALGORITHM_IDS})"
            )

        # algorithm params: JSON 化可能性チェック
        for key, val in self.algorithm_params:
            if not isinstance(key, str):
                raise ValueError(f"algorithm_params key must be str, got {type(key)}")
            if not isinstance(val, (int, float)):
                raise ValueError(
                    f"algorithm_params value for '{key}' must be int/float, got {type(val)}"
                )

    # ----- factories ------------------------------------------------------

    @classmethod
    def default(cls) -> MetaChromosome:
        """v0.B baseline 互換のデフォルト. UCB1 cold start で使う."""
        return cls(
            mutation_rate_per_layer=(0.05, 0.15, 0.02),  # impl 低 / prompt 高 / meta 最低
            crossover_strategy="intra",
            selection_pressure=0.5,
            novelty_weight=0.0,                          # baseline は fitness のみ
            cluster_quota=4,
            meta_mutation_decay=0.5,
            algorithm_id="tournament_gauss",
            algorithm_params=(),
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MetaChromosome:
        return cls(
            mutation_rate_per_layer=tuple(data["mutation_rate_per_layer"]),
            crossover_strategy=str(data["crossover_strategy"]),
            selection_pressure=float(data["selection_pressure"]),
            novelty_weight=float(data["novelty_weight"]),
            cluster_quota=int(data["cluster_quota"]),
            meta_mutation_decay=float(data["meta_mutation_decay"]),
            algorithm_id=str(data["algorithm_id"]),
            algorithm_params=tuple(
                (str(k), float(v)) for k, v in data.get("algorithm_params", [])
            ),
        )

    # ----- serialization --------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "mutation_rate_per_layer": list(self.mutation_rate_per_layer),
            "crossover_strategy": self.crossover_strategy,
            "selection_pressure": self.selection_pressure,
            "novelty_weight": self.novelty_weight,
            "cluster_quota": self.cluster_quota,
            "meta_mutation_decay": self.meta_mutation_decay,
            "algorithm_id": self.algorithm_id,
            "algorithm_params": [list(p) for p in self.algorithm_params],
        }

    def to_json_bytes(self) -> bytes:
        """JSON 化して bytes 化 (Kolmogorov complexity proxy 用)."""
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False).encode(
            "utf-8"
        )

    # ----- Kolmogorov complexity proxy ------------------------------------

    def kolmogorov_proxy(self) -> int:
        """gzip 圧縮後 byte 数. Kolmogorov complexity の計算可能近似.

        Schmidhuber (2003) Gödel Machine では K(A) を直接定義するが計算不能.
        gzip は LZ77 系で実用上 K の上界として機能する (Cilibrasi & Vitanyi
        2005 "Clustering by Compression" 系).
        """
        return len(gzip.compress(self.to_json_bytes()))

    # ----- neighborhood sampling ------------------------------------------

    def sample_neighborhood(
        self,
        rng: np.random.Generator,
        step_size: float = 0.1,
    ) -> MetaChromosome:
        """近傍 chromosome を 1 つ sample. UCB1 探索の候補生成.

        - 連続 field: Gaussian perturbation + clip
        - discrete field (crossover_strategy / algorithm_id): 1/3 確率で switch
        - cluster_quota: ±1
        - meta_mutation_decay により step が dampened (self-limit)

        skeleton 段階では full meta-evolution は実装しない. EvolutionLoop と
        統合された段階 (EV-22 / EV-23) で本格化.
        """
        effective_step = step_size * (1.0 - self.meta_mutation_decay)

        # continuous (clip to [0,1])
        new_rates = tuple(
            float(np.clip(r + rng.normal(0, effective_step), 0.0, 1.0))
            for r in self.mutation_rate_per_layer
        )
        new_sel = float(
            np.clip(self.selection_pressure + rng.normal(0, effective_step), 1e-6, 1.0)
        )
        new_nov = float(
            np.clip(self.novelty_weight + rng.normal(0, effective_step), 0.0, 1.0)
        )
        new_decay = float(
            np.clip(self.meta_mutation_decay + rng.normal(0, effective_step), 0.0, 1.0)
        )

        # discrete: probability 1/3 to switch
        new_cx = (
            str(rng.choice(KNOWN_CROSSOVER_STRATEGIES))
            if rng.random() < 1 / 3
            else self.crossover_strategy
        )
        new_alg = (
            str(rng.choice(KNOWN_ALGORITHM_IDS))
            if rng.random() < 1 / 3
            else self.algorithm_id
        )

        # cluster quota: ±1 with prob 1/2 each (clipped to >=1)
        delta_q = int(rng.choice([-1, 0, 1]))
        new_quota = max(1, self.cluster_quota + delta_q)

        return MetaChromosome(
            mutation_rate_per_layer=new_rates,
            crossover_strategy=new_cx,
            selection_pressure=new_sel,
            novelty_weight=new_nov,
            cluster_quota=new_quota,
            meta_mutation_decay=new_decay,
            algorithm_id=new_alg,
            algorithm_params=self.algorithm_params,  # skeleton では不変
        )


# ---------------------------------------------------------------------------
# UCB1 algorithm selection (state-aware helper)
# ---------------------------------------------------------------------------


def ucb1_score(
    mean_delta: float,
    use_count: int,
    total_gen: int,
    exploration_c: float = math.sqrt(2.0),
) -> float:
    """UCB1 探索 score = mean_Δ + c · sqrt(2 ln N / n_A).

    use_count == 0 の場合は ``+inf`` を返し, cold start を保証する (Auer 2002).

    Args:
        mean_delta: そのアルゴリズム使用時の平均 fitness 改善量.
        use_count: そのアルゴリズムが使われた世代数.
        total_gen: 全 algorithm の合計使用回数 (= 経過世代数).
        exploration_c: 探索定数. デフォルトは Auer 2002 推奨の sqrt(2).

    Returns:
        UCB1 score. higher == より選好される.
    """
    if use_count <= 0:
        return float("inf")
    if total_gen <= 0:
        return mean_delta
    bonus = exploration_c * math.sqrt(2.0 * math.log(total_gen) / use_count)
    return float(mean_delta + bonus)


__all__ = [
    "KNOWN_ALGORITHM_IDS",
    "KNOWN_CROSSOVER_STRATEGIES",
    "LAYER_NAMES",
    "MetaChromosome",
    "ucb1_score",
]
