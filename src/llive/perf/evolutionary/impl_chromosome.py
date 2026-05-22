# SPDX-License-Identifier: Apache-2.0
"""ImplChromosome — 実装的選択を遺伝対象とする chromosome (llive v0.F EV-13 柱 A-1).

v0.B Genome (scalar 19 dim) は数値 hyperparam のみを遺伝対象としていたが,
本 chromosome は **実装方法・アルゴリズム・並列度・実装言語・オーケストレーション
方式** といった構造的選択を遺伝対象に持ち上げる. 同じ実装方針を遺伝した個体集団
だけだと進化空間が狭い (v0.F 要件 §2 柱 A-1 限界 1) ため, "実装そのもの" を遺伝
対象に格上げするのが本 chromosome の役割.

形式化 (詳細は `docs/requirements_v0.F_genome_two_layer_and_novelty.md` §2 柱 A-1):

| Gene | 値域 | 例 |
|------|------|----|
| impl_language | enum | python / rust / cython / typescript |
| algorithm_family | enum | greedy / genetic / mcts / bayesian / random_restart |
| parallel_strategy | enum | single / thread / process / asyncio / distributed |
| agi_usage_ratio | float [0,1] | LLM 委任比率 |
| orchestration_mode | enum | sequential / pipeline / pubsub / actor_model |
| memory_backend | enum | dict / sqlite / pickle / lmdb / redis |
| selector_class | enum | UCB1 / Thompson / EpsilonGreedy / SynapticSelector |
| judge_model | enum | self / peer / external / mixed |

API は :class:`llive.perf.evolutionary.meta_chromosome.MetaChromosome` と
**完全に同型**: default() / to_dict() / from_dict() / kolmogorov_proxy() /
sample_neighborhood().

References:

- llive `docs/requirements_v0.F_genome_two_layer_and_novelty.md` §2 柱 A-1.
- Real, E. et al. (2020). [AutoML-Zero](https://arxiv.org/abs/2003.03384).
- Wang, R. et al. (2024). Promptbreeder ([arXiv:2309.16797](https://arxiv.org/abs/2309.16797)).

Status (2026-05-22 着地): skeleton. データ構造 + バリデーション + serialization +
neighborhood sampling + Kolmogorov proxy のみ. 実 EvolutionLoop 統合は
EV-14 以降.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Constants — known enum values per gene
# ---------------------------------------------------------------------------

#: 既知 impl_language 値. 将来 (zig, go, kotlin 等) 追加可.
KNOWN_IMPL_LANGUAGES: tuple[str, ...] = (
    "python",
    "rust",
    "cython",
    "typescript",
)

#: 既知 algorithm_family 値. v0.B EV-01 tournament 系 + 探索系を統合.
KNOWN_IMPL_ALGORITHM_FAMILIES: tuple[str, ...] = (
    "greedy",
    "genetic",
    "mcts",
    "bayesian",
    "random_restart",
)

#: 既知 parallel_strategy 値. v0.B scheduler 系 (serial/asyncio/multiproc) 互換 +
#: 将来分散実行用に "distributed" を予約.
KNOWN_IMPL_PARALLEL_STRATEGIES: tuple[str, ...] = (
    "single",
    "thread",
    "process",
    "asyncio",
    "distributed",
)

#: 既知 orchestration_mode 値. llive COG-MESH の portal pattern と整合.
KNOWN_IMPL_ORCHESTRATION_MODES: tuple[str, ...] = (
    "sequential",
    "pipeline",
    "pubsub",
    "actor_model",
)

#: 既知 memory_backend 値. v0.B Ledger (sqlite) + dict baseline + 永続化系.
KNOWN_IMPL_MEMORY_BACKENDS: tuple[str, ...] = (
    "dict",
    "sqlite",
    "pickle",
    "lmdb",
    "redis",
)

#: 既知 selector_class 値. v0.B SynapticSelector + 多腕バンディット系.
KNOWN_IMPL_SELECTOR_CLASSES: tuple[str, ...] = (
    "UCB1",
    "Thompson",
    "EpsilonGreedy",
    "SynapticSelector",
)

#: 既知 judge_model 値. v0.E peer evaluation + 自己/外部 evaluator.
KNOWN_IMPL_JUDGE_MODELS: tuple[str, ...] = (
    "self",
    "peer",
    "external",
    "mixed",
)


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImplChromosome:
    """実装的選択 (コード層) を遺伝対象とする frozen chromosome.

    v0.F 2 階建てゲノムの 1 階目 (要件 §2 柱 A-1). 将来
    ``Genome3D = (ImplChromosome, PromptChromosome, MetaChromosome)`` の 1 階目
    として組み込まれる. skeleton 段階では既存 Genome / MetaChromosome と
    **stand-alone** で共存する.
    """

    #: 実装言語 (KNOWN_IMPL_LANGUAGES のいずれか).
    impl_language: str

    #: アルゴリズム系統 (KNOWN_IMPL_ALGORITHM_FAMILIES のいずれか).
    algorithm_family: str

    #: 並列戦略 (KNOWN_IMPL_PARALLEL_STRATEGIES のいずれか).
    parallel_strategy: str

    #: AGI (LLM) 委任比率 [0.0, 1.0]. 1.0 = 完全 LLM 依存, 0.0 = symbolic only.
    agi_usage_ratio: float

    #: オーケストレーション方式 (KNOWN_IMPL_ORCHESTRATION_MODES のいずれか).
    orchestration_mode: str

    #: メモリバックエンド (KNOWN_IMPL_MEMORY_BACKENDS のいずれか).
    memory_backend: str

    #: バンディット選択器クラス (KNOWN_IMPL_SELECTOR_CLASSES のいずれか).
    selector_class: str

    #: 評価モデル (KNOWN_IMPL_JUDGE_MODELS のいずれか).
    judge_model: str

    # ----- validation -----------------------------------------------------

    def __post_init__(self) -> None:
        if self.impl_language not in KNOWN_IMPL_LANGUAGES:
            raise ValueError(
                f"unknown impl_language '{self.impl_language}' "
                f"(known={KNOWN_IMPL_LANGUAGES})"
            )
        if self.algorithm_family not in KNOWN_IMPL_ALGORITHM_FAMILIES:
            raise ValueError(
                f"unknown algorithm_family '{self.algorithm_family}' "
                f"(known={KNOWN_IMPL_ALGORITHM_FAMILIES})"
            )
        if self.parallel_strategy not in KNOWN_IMPL_PARALLEL_STRATEGIES:
            raise ValueError(
                f"unknown parallel_strategy '{self.parallel_strategy}' "
                f"(known={KNOWN_IMPL_PARALLEL_STRATEGIES})"
            )
        if not 0.0 <= self.agi_usage_ratio <= 1.0:
            raise ValueError(
                f"agi_usage_ratio {self.agi_usage_ratio} not in [0,1]"
            )
        if self.orchestration_mode not in KNOWN_IMPL_ORCHESTRATION_MODES:
            raise ValueError(
                f"unknown orchestration_mode '{self.orchestration_mode}' "
                f"(known={KNOWN_IMPL_ORCHESTRATION_MODES})"
            )
        if self.memory_backend not in KNOWN_IMPL_MEMORY_BACKENDS:
            raise ValueError(
                f"unknown memory_backend '{self.memory_backend}' "
                f"(known={KNOWN_IMPL_MEMORY_BACKENDS})"
            )
        if self.selector_class not in KNOWN_IMPL_SELECTOR_CLASSES:
            raise ValueError(
                f"unknown selector_class '{self.selector_class}' "
                f"(known={KNOWN_IMPL_SELECTOR_CLASSES})"
            )
        if self.judge_model not in KNOWN_IMPL_JUDGE_MODELS:
            raise ValueError(
                f"unknown judge_model '{self.judge_model}' "
                f"(known={KNOWN_IMPL_JUDGE_MODELS})"
            )

    # ----- factories ------------------------------------------------------

    @classmethod
    def default(cls) -> ImplChromosome:
        """v0.B baseline 互換のデフォルト. python + genetic + serial 系."""
        return cls(
            impl_language="python",
            algorithm_family="genetic",
            parallel_strategy="single",
            agi_usage_ratio=0.0,
            orchestration_mode="sequential",
            memory_backend="dict",
            selector_class="UCB1",
            judge_model="self",
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ImplChromosome:
        return cls(
            impl_language=str(data["impl_language"]),
            algorithm_family=str(data["algorithm_family"]),
            parallel_strategy=str(data["parallel_strategy"]),
            agi_usage_ratio=float(data["agi_usage_ratio"]),
            orchestration_mode=str(data["orchestration_mode"]),
            memory_backend=str(data["memory_backend"]),
            selector_class=str(data["selector_class"]),
            judge_model=str(data["judge_model"]),
        )

    # ----- serialization --------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "impl_language": self.impl_language,
            "algorithm_family": self.algorithm_family,
            "parallel_strategy": self.parallel_strategy,
            "agi_usage_ratio": self.agi_usage_ratio,
            "orchestration_mode": self.orchestration_mode,
            "memory_backend": self.memory_backend,
            "selector_class": self.selector_class,
            "judge_model": self.judge_model,
        }

    def to_json_bytes(self) -> bytes:
        """JSON 化して bytes 化 (Kolmogorov complexity proxy 用)."""
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False).encode(
            "utf-8"
        )

    # ----- Kolmogorov complexity proxy ------------------------------------

    def kolmogorov_proxy(self) -> int:
        """gzip 圧縮後 byte 数. Kolmogorov complexity の計算可能近似.

        MetaChromosome.kolmogorov_proxy と同様に gzip ベース. 染色体が複雑
        (= enum field の多様性が高い + json key が長い) ほど proxy 値が増える.
        """
        return len(gzip.compress(self.to_json_bytes()))

    # ----- neighborhood sampling ------------------------------------------

    def sample_neighborhood(
        self,
        rng: np.random.Generator,
        step_size: float = 0.1,
    ) -> ImplChromosome:
        """近傍 chromosome を 1 つ sample.

        - discrete enum field: 確率 ``step_size`` で別の候補へ switch
          (step_size=0.0 なら完全に不変, step_size=1.0 なら必ず再抽選)
        - continuous (agi_usage_ratio): Gaussian perturbation + clip to [0,1]

        skeleton 段階では full evolution は実装しない. EvolutionLoop と
        統合された段階 (EV-14 以降) で本格化.
        """
        switch_prob = float(np.clip(step_size, 0.0, 1.0))

        new_lang = (
            str(rng.choice(KNOWN_IMPL_LANGUAGES))
            if rng.random() < switch_prob
            else self.impl_language
        )
        new_alg = (
            str(rng.choice(KNOWN_IMPL_ALGORITHM_FAMILIES))
            if rng.random() < switch_prob
            else self.algorithm_family
        )
        new_par = (
            str(rng.choice(KNOWN_IMPL_PARALLEL_STRATEGIES))
            if rng.random() < switch_prob
            else self.parallel_strategy
        )
        new_orc = (
            str(rng.choice(KNOWN_IMPL_ORCHESTRATION_MODES))
            if rng.random() < switch_prob
            else self.orchestration_mode
        )
        new_mem = (
            str(rng.choice(KNOWN_IMPL_MEMORY_BACKENDS))
            if rng.random() < switch_prob
            else self.memory_backend
        )
        new_sel = (
            str(rng.choice(KNOWN_IMPL_SELECTOR_CLASSES))
            if rng.random() < switch_prob
            else self.selector_class
        )
        new_jud = (
            str(rng.choice(KNOWN_IMPL_JUDGE_MODELS))
            if rng.random() < switch_prob
            else self.judge_model
        )

        # continuous: Gaussian perturbation
        new_agi = float(
            np.clip(self.agi_usage_ratio + rng.normal(0, step_size), 0.0, 1.0)
        )

        return ImplChromosome(
            impl_language=new_lang,
            algorithm_family=new_alg,
            parallel_strategy=new_par,
            agi_usage_ratio=new_agi,
            orchestration_mode=new_orc,
            memory_backend=new_mem,
            selector_class=new_sel,
            judge_model=new_jud,
        )


__all__ = [
    "KNOWN_IMPL_ALGORITHM_FAMILIES",
    "KNOWN_IMPL_JUDGE_MODELS",
    "KNOWN_IMPL_LANGUAGES",
    "KNOWN_IMPL_MEMORY_BACKENDS",
    "KNOWN_IMPL_ORCHESTRATION_MODES",
    "KNOWN_IMPL_PARALLEL_STRATEGIES",
    "KNOWN_IMPL_SELECTOR_CLASSES",
    "ImplChromosome",
]
