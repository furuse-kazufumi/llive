# SPDX-License-Identifier: Apache-2.0
"""Fitness 関数の抽象 + toy / mock 実装 (llive v0.B EV-02).

公開 API: ``Fitness = Callable[[Genome], FitnessReport]`` の型. UCB selector
連携や実 LLM 評価は別 module (``fitness_ucb.py`` / ``fitness_llm.py``) で
adapter として提供する.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import numpy as np

from llive.benchmark.runtime_metadata import collect_runtime_metadata
from llive.perf.evolutionary.genome import Genome
from llive.perf.evolutionary.individual import FitnessReport


class FitnessFn(Protocol):
    """``__call__(genome) -> FitnessReport`` を持つ callable の型 protocol."""

    def __call__(self, genome: Genome) -> FitnessReport:
        ...


Fitness = Callable[[Genome], FitnessReport]


def sphere_fitness(genome: Genome) -> FitnessReport:
    """sphere function (最小化問題): - sum(x^2). 0 ベクトルで最大.

    GA の単体テストに使う toy fitness. runtime metadata は必須 (EV-02).
    """
    arr = genome.as_array()
    score = float(-np.sum(arr * arr))
    md = collect_runtime_metadata()
    return FitnessReport(
        score=score,
        breakdown={"sum_sq": float(np.sum(arr * arr))},
        runtime_metadata=dict(md),
        n_samples=1,
        notes="sphere_fitness (toy)",
    )


def rosenbrock_fitness(genome: Genome) -> FitnessReport:
    """Rosenbrock function (難しめ toy): -sum(100*(x_{i+1} - x_i^2)^2 + (1 - x_i)^2).

    すべての dim が 1 のとき最大. valley が狭い non-convex 問題.
    """
    arr = genome.as_array()
    if arr.size == 0:
        # 空 genome は評価対象がない → neutral (0.0). IndexError 回避 (B-EDGE-1).
        score = 0.0
    elif arr.size < 2:
        score = -float((1 - arr[0]) ** 2)
    else:
        score = -float(
            np.sum(100 * (arr[1:] - arr[:-1] ** 2) ** 2 + (1 - arr[:-1]) ** 2)
        )
    md = collect_runtime_metadata()
    return FitnessReport(
        score=score,
        breakdown={"raw_loss": -score},
        runtime_metadata=dict(md),
        n_samples=1,
        notes="rosenbrock_fitness (toy)",
    )


__all__ = ["Fitness", "FitnessFn", "rosenbrock_fitness", "sphere_fitness"]
