# SPDX-License-Identifier: Apache-2.0
"""RecursionDepthGene — 個体内 self-refine cycle 回数を遺伝子化 (llive v0.F EV-19).

ユーザー指摘 (2026-05-22 深夜):

    > 重複というのは出力を再帰的に入力として与えるイメージです.
    > その回数を持たせるイメージですね.
    > 次の層や因子に渡す前に深く考えるという個体もあっても良いのかと思った次第です.

→ つまり「重複」は **集団内コピー** (それは [[duplication.py]] が担当) ではなく,
**個体内の出力→入力 再帰回数** を遺伝子化する話. 次の層 (4 層メモリ) や次の因子
(10 思考因子) に渡す前にどれだけ深く self-refine するかを染色体として持たせる.

研究的位置づけ:

| 概念 | 関連 | 本実装の位置づけ |
|------|------|-----------------|
| Chain-of-Thought | Wei et al. 2022 | 1 回限りの reasoning chain |
| Self-Refine | Madaan et al. 2023 (NeurIPS) | LLM が出力 → 自分で批判 → 修正のループ |
| Iterative Deepening | DFS depth control | 探索深度の段階制御 |
| Reverberation (反響活動) | Hebb 1949 / Lorente de Nó 1938 | 神経 ensemble の自己再入力 |
| Neural ODE depth | Chen et al. 2018 | 連続深度 NN. depth を学習対象に |
| Tree of Thoughts | Yao et al. 2023 | 思考分岐の幅 (本実装は深さ) |
| Reflexion | Shinn et al. 2023 | 言語による自己強化学習 |

形式化 (詳細は `docs/requirements_v0.F_genome_two_layer_and_novelty.md` §3 柱 A-19):

```
output_t+1 = inference_fn(output_t)          (recursion)
delta_t    = ||hash(output_t+1) - hash(output_t)||
stop if    delta_t < early_stop_threshold
       or  t >= per_layer[layer]
       or  total_recursion_count >= max_total_recursion
```

各 iteration で適用される refine 戦略は :class:`RefineStrategy` の 6 種:

- ``SELF_CRITIQUE`` — 自分の出力に批判 → 修正 (Self-Refine 系)
- ``PERSPECTIVE_SHIFT`` — 視点を変えて再考 (ToT branch)
- ``CONSTRAINT_TIGHTEN`` — 制約を強めて refine (constraint propagation)
- ``EVIDENCE_SEEK`` — 裏付け取得 → 補強 (Reflexion retrieval)
- ``ABSTRACTION_LIFT`` — 抽象度を上げて再考 (Polya generalization)
- ``DETAIL_DRILL`` — 詳細に降りて再考 (Polya specialization)

References:

- Madaan, A. et al. (2023). [Self-Refine: Iterative Refinement with Self-Feedback](https://arxiv.org/abs/2303.17651).
- Shinn, N. et al. (2023). [Reflexion: Language Agents with Verbal Reinforcement Learning](https://arxiv.org/abs/2303.11366).
- Yao, S. et al. (2023). [Tree of Thoughts](https://arxiv.org/abs/2305.10601).
- Wei, J. et al. (2022). [Chain-of-Thought Prompting](https://arxiv.org/abs/2201.11903).
- Chen, R. T. Q. et al. (2018). Neural ODE ([arXiv:1806.07366](https://arxiv.org/abs/1806.07366)).
- Lorente de Nó, R. (1938). Reverberation in neuron ensembles.
- llive `docs/requirements_v0.F_genome_two_layer_and_novelty.md` §3 柱 A-19.

Status (2026-05-22 着地): skeleton. データ構造 + バリデーション + serialization +
neighborhood sampling + Kolmogorov proxy のみ. 実 inference_fn 統合 (LLM backend
経由) は次フェーズ.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import numpy as np

from llive.perf.evolutionary.persona import THOUGHT_FACTORS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: max_total_recursion のデフォルト. recursion 爆発防止上限.
DEFAULT_MAX_TOTAL_RECURSION: int = 50

#: early_stop_threshold のデフォルト. 差分 (delta) がこの値未満なら停止.
DEFAULT_EARLY_STOP_THRESHOLD: float = 0.01

#: layer 数 (4 層メモリ間の 3 境界).
#: sensory→episodic / episodic→semantic / semantic→parameter.
NUM_LAYER_BOUNDARIES: int = 3

#: per_factor のキー (思考因子名). persona.THOUGHT_FACTORS を SSoT とする.
EXPECTED_THOUGHT_FACTORS: tuple[str, ...] = tuple(THOUGHT_FACTORS)


# ---------------------------------------------------------------------------
# RefineStrategy
# ---------------------------------------------------------------------------


class RefineStrategy(str, Enum):
    """各 recursion iteration で適用される refine 戦略 (6 種).

    str を mixin することで JSON 直接 serialize 可能 / pytest assert で読みやすい
    形にしている.
    """

    SELF_CRITIQUE = "self_critique"
    """自分の出力に批判 → 修正 (Madaan et al. 2023 Self-Refine 系)."""

    PERSPECTIVE_SHIFT = "perspective_shift"
    """視点を変えて再考 (Yao 2023 ToT branching の縦軸版)."""

    CONSTRAINT_TIGHTEN = "constraint_tighten"
    """制約を強めて refine (constraint propagation)."""

    EVIDENCE_SEEK = "evidence_seek"
    """裏付け取得 → 補強 (Shinn 2023 Reflexion 系)."""

    ABSTRACTION_LIFT = "abstraction_lift"
    """抽象度を上げて再考 (Polya generalization)."""

    DETAIL_DRILL = "detail_drill"
    """詳細に降りて再考 (Polya specialization)."""


#: 既知 RefineStrategy 値. validation / export 用.
KNOWN_REFINE_STRATEGIES: tuple[str, ...] = tuple(s.value for s in RefineStrategy)


# ---------------------------------------------------------------------------
# RecursionDepthGene
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecursionDepthGene:
    """個体が「次の層 / 次の因子に渡す前に出力→入力で再考する回数」を遺伝子化.

    Skeleton 段階では既存 v0.B Genome / v0.D MetaChromosome と **stand-alone** で
    共存し, 後続フェーズで Genome3D の第 4 染色体 (または ImplChromosome の
    sub-field) として組み込む.

    Attributes:
        per_layer: 4 層メモリ間 3 境界での再帰回数. >=1.
            (sensory→episodic, episodic→semantic, semantic→parameter).
        per_factor: 10 思考因子それぞれの再帰回数. frozen tuple of (name, count).
            count は 0 (= 因子適用しない) 〜 max_total_recursion.
        max_total_recursion: 全体上限 (爆発防止). >=1, default 50.
        refine_strategy: 各 recursion で何を refine するか.
        early_stop_threshold: 差分 (delta) がこの値未満になったら停止.
            0.0 (= 完全一致でのみ停止) 〜 1.0.
    """

    per_layer: tuple[int, int, int]
    per_factor: tuple[tuple[str, int], ...]
    max_total_recursion: int
    refine_strategy: RefineStrategy
    early_stop_threshold: float

    # ----- validation -----------------------------------------------------

    def __post_init__(self) -> None:
        # per_layer: 3 要素, 各 >=1
        if len(self.per_layer) != NUM_LAYER_BOUNDARIES:
            raise ValueError(
                f"per_layer len {len(self.per_layer)} != {NUM_LAYER_BOUNDARIES} "
                f"(sensory→episodic, episodic→semantic, semantic→parameter)"
            )
        for idx, depth in enumerate(self.per_layer):
            if not isinstance(depth, int):
                raise ValueError(
                    f"per_layer[{idx}] must be int, got {type(depth).__name__}"
                )
            if depth < 1:
                raise ValueError(
                    f"per_layer[{idx}] = {depth} must be >= 1 "
                    f"(at least 1 pass-through is required)"
                )

        # per_factor: 各 (name, count) で name is str, count >= 0
        seen_factors: set[str] = set()
        for entry in self.per_factor:
            if not (isinstance(entry, tuple) and len(entry) == 2):
                raise ValueError(
                    f"per_factor entry {entry!r} must be (name, count) tuple"
                )
            name, count = entry
            if not isinstance(name, str):
                raise ValueError(
                    f"per_factor entry name must be str, got {type(name).__name__}"
                )
            if not isinstance(count, int):
                raise ValueError(
                    f"per_factor[{name}] count must be int, got {type(count).__name__}"
                )
            if count < 0:
                raise ValueError(
                    f"per_factor[{name}] count = {count} must be >= 0"
                )
            if name in seen_factors:
                raise ValueError(f"per_factor duplicate name: '{name}'")
            seen_factors.add(name)

        # max_total_recursion
        if not isinstance(self.max_total_recursion, int):
            raise ValueError(
                f"max_total_recursion must be int, got {type(self.max_total_recursion).__name__}"
            )
        if self.max_total_recursion < 1:
            raise ValueError(
                f"max_total_recursion {self.max_total_recursion} must be >= 1"
            )

        # refine_strategy: enum なら OK, str なら convert 試行
        if not isinstance(self.refine_strategy, RefineStrategy):
            raise ValueError(
                f"refine_strategy must be RefineStrategy enum, "
                f"got {type(self.refine_strategy).__name__}"
            )

        # early_stop_threshold
        if not isinstance(self.early_stop_threshold, (int, float)):
            raise ValueError(
                f"early_stop_threshold must be float, "
                f"got {type(self.early_stop_threshold).__name__}"
            )
        if not 0.0 <= self.early_stop_threshold <= 1.0:
            raise ValueError(
                f"early_stop_threshold {self.early_stop_threshold} not in [0,1]"
            )

    # ----- factories ------------------------------------------------------

    @classmethod
    def default(cls) -> RecursionDepthGene:
        """v0.B baseline 互換のデフォルト (1 = 通常, recursion しない).

        全 layer / 全 factor で count=1 → identity に近い挙動になり,
        既存 EvolutionLoop と stand-alone で共存できる.
        """
        return cls(
            per_layer=(1, 1, 1),
            per_factor=tuple((f, 1) for f in EXPECTED_THOUGHT_FACTORS),
            max_total_recursion=DEFAULT_MAX_TOTAL_RECURSION,
            refine_strategy=RefineStrategy.SELF_CRITIQUE,
            early_stop_threshold=DEFAULT_EARLY_STOP_THRESHOLD,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RecursionDepthGene:
        """JSON dict から復元. per_factor は tuple-of-tuple に正規化."""
        per_layer_raw = data["per_layer"]
        if len(per_layer_raw) != NUM_LAYER_BOUNDARIES:
            raise ValueError(
                f"per_layer len {len(per_layer_raw)} != {NUM_LAYER_BOUNDARIES}"
            )
        per_layer = (
            int(per_layer_raw[0]),
            int(per_layer_raw[1]),
            int(per_layer_raw[2]),
        )
        per_factor = tuple(
            (str(name), int(count)) for name, count in data["per_factor"]
        )
        strategy_raw = data["refine_strategy"]
        if isinstance(strategy_raw, RefineStrategy):
            refine_strategy = strategy_raw
        else:
            refine_strategy = RefineStrategy(str(strategy_raw))
        return cls(
            per_layer=per_layer,
            per_factor=per_factor,
            max_total_recursion=int(data["max_total_recursion"]),
            refine_strategy=refine_strategy,
            early_stop_threshold=float(data["early_stop_threshold"]),
        )

    # ----- serialization --------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "per_layer": list(self.per_layer),
            "per_factor": [[name, count] for name, count in self.per_factor],
            "max_total_recursion": self.max_total_recursion,
            "refine_strategy": self.refine_strategy.value,
            "early_stop_threshold": self.early_stop_threshold,
        }

    def to_json_bytes(self) -> bytes:
        """JSON 化して bytes 化 (Kolmogorov complexity proxy 用)."""
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False).encode(
            "utf-8"
        )

    # ----- Kolmogorov complexity proxy ------------------------------------

    def kolmogorov_proxy(self) -> int:
        """gzip 圧縮後 byte 数. Kolmogorov complexity の計算可能近似.

        MetaChromosome と同様, gzip (LZ77 系) を K の実用的上界として利用
        (Cilibrasi & Vitanyi 2005 "Clustering by Compression").
        """
        return len(gzip.compress(self.to_json_bytes()))

    # ----- aggregation helpers --------------------------------------------

    def total_expected_recursion(self) -> int:
        """全層 + 全因子の単純和 (debug 用 / budget 試算用).

        ※ max_total_recursion とは別概念. 実際の実行は max_total_recursion で
        クリップされうる. これは「もし上限が無ければ何回回るか」の予算試算.
        """
        return sum(self.per_layer) + sum(count for _, count in self.per_factor)

    # ----- neighborhood sampling ------------------------------------------

    def sample_neighborhood(
        self,
        rng: np.random.Generator,
        step_size: float = 0.1,
    ) -> RecursionDepthGene:
        """近傍 chromosome を 1 つ sample. EvolutionLoop 探索の候補生成.

        操作:

        - per_layer: 各 layer で 1/3 確率で ±1 (>=1 にクリップ).
        - per_factor: 各 factor で 1/3 確率で ±1 (>=0 にクリップ).
        - max_total_recursion: 1/3 確率で ±5 step (>=1 にクリップ).
        - refine_strategy: step_size に応じた確率で 6 種から再抽選.
        - early_stop_threshold: Gaussian perturbation + clip [0,1].

        step_size は離散 fields の switch 確率を増幅 (大きいほど飛びやすい).
        """
        # per_layer: ±1 step
        new_layer = tuple(
            max(1, depth + int(rng.choice([-1, 0, 0, 1])))
            for depth in self.per_layer
        )
        # mypy の static 長さ要求 (3-tuple)
        new_per_layer: tuple[int, int, int] = (
            new_layer[0],
            new_layer[1],
            new_layer[2],
        )

        # per_factor: ±1 step (>=0)
        new_per_factor = tuple(
            (name, max(0, count + int(rng.choice([-1, 0, 0, 1]))))
            for name, count in self.per_factor
        )

        # max_total_recursion: ±5
        delta_max = int(rng.choice([-5, 0, 0, 5]))
        new_max = max(1, self.max_total_recursion + delta_max)

        # refine_strategy: step_size に応じた確率で switch
        switch_prob = min(1.0, max(0.0, step_size))
        if rng.random() < switch_prob:
            new_strategy = RefineStrategy(str(rng.choice(KNOWN_REFINE_STRATEGIES)))
        else:
            new_strategy = self.refine_strategy

        # early_stop_threshold: Gaussian
        new_threshold = float(
            np.clip(
                self.early_stop_threshold + rng.normal(0, step_size * 0.1),
                0.0,
                1.0,
            )
        )

        return RecursionDepthGene(
            per_layer=new_per_layer,
            per_factor=new_per_factor,
            max_total_recursion=new_max,
            refine_strategy=new_strategy,
            early_stop_threshold=new_threshold,
        )


__all__ = [
    "DEFAULT_EARLY_STOP_THRESHOLD",
    "DEFAULT_MAX_TOTAL_RECURSION",
    "EXPECTED_THOUGHT_FACTORS",
    "KNOWN_REFINE_STRATEGIES",
    "NUM_LAYER_BOUNDARIES",
    "RecursionDepthGene",
    "RefineStrategy",
]
