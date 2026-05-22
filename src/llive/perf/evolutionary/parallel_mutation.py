# SPDX-License-Identifier: Apache-2.0
"""Parallel mutation / parallel multi-task evaluation (llive v0.F EV-17 柱 B).

ユーザー指摘 (2026-05-22 深夜) の **並列処理している進化や突然変異** を skeleton
レベルで実装する. SIMD 風に「1 個体から N 個の独立変異を 1 世代で生成」する
:func:`parallel_mutate` と, 「1 個体を N task で並列評価して集約スコア + 分散を返す」
:func:`evaluate_parallel` の 2 つを提供する.

設計方針:

- :func:`parallel_mutate` は **genome 単体に依存する**. ``sample_neighborhood``
  を持つ任意の chromosome / Genome3D / Genome を引数に取れる. ダックタイピング.
- :func:`evaluate_parallel` は **fitness_fns: dict[str, Callable]** を取り,
  各 task で評価して集約スコア + ばらつき (標準偏差) を返す. fitness_fn は
  ``() -> float`` の zero-arg callable (caller 側で genome を closure 取り込み).
- ``ParallelEvaluationResult`` は frozen / hashable / JSON-serializable.
  ``fitness_per_task`` は dict ではなく tuple-of-tuples で frozen に保つ.

形式化 (詳細は `docs/requirements_v0.F_*.md` §3 柱 B):

| Operator | 入力 | 出力 | 比喩 |
|----------|------|------|------|
| parallel_mutate | 1 genome + N | N independent mutants | 神経 ensemble の同時発火 |
| evaluate_parallel | 1 individual + M tasks | aggregated score + divergence | 多元評価 (lexicase 風) |

References:

- Spector, L. (2012). Lexicase selection (per-task fitness ensemble).
- Brain, M. (2017). Ensemble neural firing patterns.
- llive `docs/requirements_v0.F_genome_two_layer_and_novelty.md` §3 柱 B.

Status (2026-05-22 着地): skeleton. functions + dataclass のみ. 実 SubprocessScheduler /
asyncio 配信は次フェーズ (本 module は **論理的並列** = 同時に複数生成すること
を表現する skeleton であり, 物理的並列実行は scheduler 側が担う).
"""

from __future__ import annotations

import statistics
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar, runtime_checkable

import numpy as np


# ---------------------------------------------------------------------------
# Protocol — sample_neighborhood を持つ任意 genome
# ---------------------------------------------------------------------------


@runtime_checkable
class _HasSampleNeighborhood(Protocol):
    """``sample_neighborhood(rng, step_size) -> Self`` を持つ任意の genome.

    ImplChromosome / PromptChromosome / MetaChromosome / Genome3D / 将来の
    任意 chromosome がここに合致する.
    """

    def sample_neighborhood(
        self,
        rng: np.random.Generator,
        step_size: float = ...,
    ) -> Any:
        ...


_G = TypeVar("_G")


#: 集約戦略の許容値.
KNOWN_AGGREGATIONS: tuple[str, ...] = ("mean", "median", "min")


# ---------------------------------------------------------------------------
# parallel_mutate — SIMD 風 N fork
# ---------------------------------------------------------------------------


def parallel_mutate(
    genome: _G,
    n: int = 8,
    step_size: float = 0.1,
    rng: np.random.Generator | None = None,
) -> tuple[_G, ...]:
    """1 個体から N 個の独立変異を 1 世代で生成 (SIMD 風 / 神経 ensemble 風).

    各 mutation は ``genome.sample_neighborhood(rng, step_size=step_size)`` で
    生成. caller は返り値の tuple を Population に挿入する.

    Args:
        genome: ``sample_neighborhood`` メソッドを持つ任意の genome / chromosome.
        n: 生成する mutant の数. n=1 でも動く.
        step_size: 各 mutation の step size (genome 側が解釈).
        rng: numpy RNG. None なら ``np.random.default_rng()`` で生成.

    Returns:
        Tuple of N mutants. 各々は独立に sample された別 instance.

    Raises:
        ValueError: n < 1 のとき.
        TypeError: genome が ``sample_neighborhood`` を持たないとき.
    """
    if n < 1:
        raise ValueError(f"n {n} < 1 — 並列変異は最低 1 個生成する必要がある")
    if not hasattr(genome, "sample_neighborhood"):
        raise TypeError(
            f"genome {type(genome).__name__} has no 'sample_neighborhood' method"
        )
    if rng is None:
        rng = np.random.default_rng()
    return tuple(
        genome.sample_neighborhood(rng, step_size=step_size)  # type: ignore[attr-defined]
        for _ in range(n)
    )


# ---------------------------------------------------------------------------
# Multi-task evaluation
# ---------------------------------------------------------------------------


#: fitness function 型. zero-arg → float. caller 側で genome を closure に包む.
FitnessTaskFn = Callable[[], float]


@dataclass(frozen=True)
class ParallelEvaluationResult:
    """1 個体を N task で並列評価した結果. frozen / JSON-serializable.

    各 task の score を保持し, 集約スコア (consensus_score) と task 間
    のばらつき (divergence) を併せ持つ. lexicase 選択や robustness 評価で
    使う.
    """

    #: SHA-256 content ID (PhyTree compute_individual_id と整合) または任意の str.
    individual_id: str

    #: (task_name, fitness) の tuple (frozen). dict ではなく tuple-of-tuples.
    fitness_per_task: tuple[tuple[str, float], ...]

    #: 集約値 (mean / median / min を caller が選択).
    consensus_score: float

    #: task 間 fitness の分散指標 (標準偏差). 0 なら全 task 等価.
    divergence: float

    # ----- validation -----------------------------------------------------

    def __post_init__(self) -> None:
        if not isinstance(self.individual_id, str) or not self.individual_id:
            raise ValueError("individual_id must be a non-empty str")
        if not self.fitness_per_task:
            raise ValueError(
                "fitness_per_task is empty — 最低 1 task 評価結果が必要"
            )
        seen_names: set[str] = set()
        for entry in self.fitness_per_task:
            if not (isinstance(entry, tuple) and len(entry) == 2):
                raise ValueError(
                    f"fitness_per_task entry {entry!r} must be (task_name, fitness)"
                )
            name, score = entry
            if not isinstance(name, str) or not name:
                raise ValueError(f"task name {name!r} must be non-empty str")
            if name in seen_names:
                raise ValueError(f"duplicate task name {name!r}")
            seen_names.add(name)
            if not isinstance(score, (int, float)):
                raise ValueError(f"fitness {score!r} for {name!r} not numeric")
            if not np.isfinite(score):
                raise ValueError(f"fitness {score!r} for {name!r} not finite")
        if not np.isfinite(self.consensus_score):
            raise ValueError(
                f"consensus_score {self.consensus_score!r} must be finite"
            )
        if not np.isfinite(self.divergence) or self.divergence < 0.0:
            raise ValueError(
                f"divergence {self.divergence!r} must be finite and >= 0"
            )

    # ----- serialization --------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "individual_id": self.individual_id,
            "fitness_per_task": [
                [name, float(score)] for name, score in self.fitness_per_task
            ],
            "consensus_score": float(self.consensus_score),
            "divergence": float(self.divergence),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ParallelEvaluationResult:
        raw = data["fitness_per_task"]
        return cls(
            individual_id=str(data["individual_id"]),
            fitness_per_task=tuple(
                (str(name), float(score)) for name, score in raw
            ),
            consensus_score=float(data["consensus_score"]),
            divergence=float(data["divergence"]),
        )


# ---------------------------------------------------------------------------
# evaluate_parallel
# ---------------------------------------------------------------------------


def _aggregate(scores: list[float], strategy: str) -> float:
    """集約戦略の dispatcher. mean / median / min."""
    if strategy == "mean":
        return float(statistics.fmean(scores))
    if strategy == "median":
        return float(statistics.median(scores))
    if strategy == "min":
        return float(min(scores))
    raise ValueError(
        f"unknown aggregation '{strategy}' (known={KNOWN_AGGREGATIONS})"
    )


def evaluate_parallel(
    individual_id: str,
    fitness_fns: Mapping[str, FitnessTaskFn],
    aggregation: str = "mean",
) -> ParallelEvaluationResult:
    """1 個体を全 task で評価 → 集約スコア + ばらつき.

    各 fitness_fn は zero-arg callable で float を返す. caller 側で genome を
    closure に包んで渡す前提:

    .. code-block:: python

        result = evaluate_parallel(
            individual_id="abc123",
            fitness_fns={
                "task_a": lambda: sphere_fitness(g).score,
                "task_b": lambda: rosenbrock_fitness(g).score,
            },
            aggregation="mean",
        )

    Args:
        individual_id: SHA-256 ID または任意の str.
        fitness_fns: ``task_name -> zero-arg fitness fn``. 1 件以上必要.
        aggregation: ``"mean"`` / ``"median"`` / ``"min"`` のいずれか.

    Returns:
        :class:`ParallelEvaluationResult` (frozen).

    Raises:
        ValueError: fitness_fns が空 or aggregation が不明.
    """
    if not fitness_fns:
        raise ValueError("fitness_fns is empty — 最低 1 task 必要")
    if aggregation not in KNOWN_AGGREGATIONS:
        raise ValueError(
            f"unknown aggregation '{aggregation}' (known={KNOWN_AGGREGATIONS})"
        )

    scored: list[tuple[str, float]] = []
    raw_scores: list[float] = []
    for name, fn in fitness_fns.items():
        score = float(fn())
        scored.append((name, score))
        raw_scores.append(score)

    consensus = _aggregate(raw_scores, aggregation)
    # divergence: 標準偏差 (n=1 では 0).
    divergence = float(statistics.pstdev(raw_scores)) if len(raw_scores) > 1 else 0.0

    return ParallelEvaluationResult(
        individual_id=individual_id,
        fitness_per_task=tuple(scored),
        consensus_score=consensus,
        divergence=divergence,
    )


__all__ = [
    "KNOWN_AGGREGATIONS",
    "FitnessTaskFn",
    "ParallelEvaluationResult",
    "evaluate_parallel",
    "parallel_mutate",
]
