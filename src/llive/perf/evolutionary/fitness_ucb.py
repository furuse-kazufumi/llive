# SPDX-License-Identifier: Apache-2.0
"""Fitness adapter — UCB selector の hyperparameter を進化対象にする (EV-09).

Phase 4 skeleton. Genome = (exploration_constant, lr, decay) を表現し,
``UCBSynapticSelector`` を spawn して toy variants を回し, latency / quality
の合成 score を fitness とする.

実 LLM 評価 (credential 復旧後) は ``fitness_llm.py`` で別途提供.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

import numpy as np

from llive.benchmark.runtime_metadata import collect_runtime_metadata
from llive.perf.evolutionary.genome import Genome, GenomeBounds
from llive.perf.evolutionary.individual import FitnessReport


# Genome レイアウト規約 (UCB hyperparameter 進化用)
UCB_GENOME_LABELS: tuple[str, str, str] = (
    "exploration_constant",  # UCB1 の c
    "learning_rate",         # weight 更新 lr (将来用, 現状未使用)
    "decay",                 # 報酬の時間 decay (将来用)
)

UCB_GENOME_BOUNDS = GenomeBounds(
    lower=(0.01, 0.001, 0.5),
    upper=(4.0, 1.0, 1.0),
)


@dataclass(frozen=True)
class UcbFitnessConfig:
    """1 個体評価の設定. iters / n_variants は外注 toy 環境のサイズ."""

    iters: int = 200
    n_variants: int = 3
    seed: int = 0


def _toy_variant_latency(variant_id: int, rng: np.random.Generator) -> float:
    """3 variant の合成 latency_ms (decreasing in id). variant_id=2 が真の最良."""
    base = [40.0, 25.0, 12.0][variant_id]
    return float(base + rng.normal(0.0, 1.5))


def ucb_fitness_factory(
    config: UcbFitnessConfig = UcbFitnessConfig(),
) -> Callable[[Genome], FitnessReport]:
    """``Callable[[Genome], FitnessReport]`` を返す factory.

    Genome = (exploration_constant, lr, decay) を受け取り, UCB selector を
    spawn して toy variants を ``config.iters`` 回回す. latency 平均の負数を
    score として返す (大きいほど良い).

    Notes
    -----
    UCBSynapticSelector の現実装は ``c`` を引数で受け取らない場合がある.
    その場合は spawn 時に内部 attribute を上書きする workaround を取る.
    実装の進化に合わせて adapter を update する.
    """

    def _fitness(genome: Genome) -> FitnessReport:
        try:
            from llive.perf.synaptic_selector import (  # type: ignore[import-untyped]
                StrategyVariant,
                UCBSynapticSelector,
            )
        except ImportError:
            # synaptic_selector が無い環境 (B-0 以前) の fallback. 単なる toy.
            return _noop_ucb_fitness(genome, config)

        rng = np.random.default_rng(config.seed)
        variants = [
            StrategyVariant(name=f"toy_v{i}", impl=lambda i=i, rng=rng: _toy_variant_latency(i, rng))
            for i in range(config.n_variants)
        ]
        try:
            selector = UCBSynapticSelector(variants=variants, c=float(genome.values[0]))
        except TypeError:
            # `c` を kwarg で取らない実装の場合: instance 作成後に attribute set
            selector = UCBSynapticSelector(variants=variants)
            setattr(selector, "c", float(genome.values[0]))

        latencies: list[float] = []
        for _ in range(config.iters):
            chosen = selector.choose()
            t0 = time.perf_counter_ns()
            latency_ms = chosen.impl()
            elapsed_ns = time.perf_counter_ns() - t0
            # 報酬は「速いほど良い」: -latency
            try:
                selector.observe(chosen, reward=-latency_ms)
            except (AttributeError, TypeError):
                # API 名が違う場合の fallback (将来 unify)
                pass
            latencies.append(latency_ms + elapsed_ns / 1e6)

        arr = np.asarray(latencies, dtype=np.float64)
        score = float(-arr.mean())  # 大きいほど良い
        md = collect_runtime_metadata()
        return FitnessReport(
            score=score,
            breakdown={
                "mean_latency_ms": float(arr.mean()),
                "p50_latency_ms": float(np.percentile(arr, 50)),
                "p99_latency_ms": float(np.percentile(arr, 99)),
                "exploration_constant": float(genome.values[0]),
            },
            runtime_metadata=dict(md),
            n_samples=config.iters,
            notes="ucb_fitness (toy 3-variant environment)",
        )

    return _fitness


def _noop_ucb_fitness(genome: Genome, config: UcbFitnessConfig) -> FitnessReport:
    """synaptic_selector が import できない環境の fallback. c に近いほど -1 に近づく."""
    c = float(genome.values[0])
    score = -abs(c - 1.4)  # UCB1 標準 c≈sqrt(2)≈1.41 が良いと仮定
    return FitnessReport(
        score=float(score),
        breakdown={"c": c},
        runtime_metadata=dict(collect_runtime_metadata()),
        n_samples=config.iters,
        notes="ucb_fitness fallback (synaptic_selector not available)",
    )


__all__ = ["UCB_GENOME_BOUNDS", "UCB_GENOME_LABELS", "UcbFitnessConfig", "ucb_fitness_factory"]
