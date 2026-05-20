# SPDX-License-Identifier: Apache-2.0
"""Demo — 進化型最適化ループ (llive v0.B EV-06).

ROS の歩行進化と同じ形 = 個体集団 → 評価 → 選別 → 交配 → 突然変異 → 次世代.

使い方::

    py -3.11 scripts/demo_evolutionary_loop.py --problem sphere --size 30 --gens 50
    py -3.11 scripts/demo_evolutionary_loop.py --problem rosenbrock --size 50 --gens 80 --parallel

problem:
* sphere      — 3 dim, 真の最適 = (0, 0, 0). 易しい.
* rosenbrock  — 2 dim, 真の最適 = (1, 1). valley が狭い.
* ucb_hparam  — UCB selector の exploration_constant を進化. EV-09 連携.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from llive.perf.evolutionary import (
    BlendCrossover,
    ChainedMutation,
    ElitismSelection,
    EvolutionConfig,
    EvolutionLoop,
    GaussianMutation,
    GenomeBounds,
    LLM_GENOME_BOUNDS,
    LLM_GENOME_LABELS,
    LlmFitnessConfig,
    MultiprocessingScheduler,
    Population,
    ResetMutation,
    TournamentSelection,
    UCB_GENOME_BOUNDS,
    UCB_GENOME_LABELS,
    UcbFitnessConfig,
    llm_fitness_factory,
    rosenbrock_fitness,
    sphere_fitness,
    ucb_fitness_factory,
)


def _build_problem(name: str) -> tuple[GenomeBounds, callable, tuple[str, ...]]:
    if name == "sphere":
        return (
            GenomeBounds(lower=(-5.0, -5.0, -5.0), upper=(5.0, 5.0, 5.0)),
            sphere_fitness,
            ("x", "y", "z"),
        )
    if name == "rosenbrock":
        return (
            GenomeBounds(lower=(-2.0, -2.0), upper=(2.0, 2.0)),
            rosenbrock_fitness,
            ("x", "y"),
        )
    if name == "ucb_hparam":
        return (
            UCB_GENOME_BOUNDS,
            ucb_fitness_factory(UcbFitnessConfig(iters=120, n_variants=3, seed=0)),
            UCB_GENOME_LABELS,
        )
    raise ValueError(f"unknown problem: {name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--problem", default="sphere", choices=["sphere", "rosenbrock", "ucb_hparam"])
    parser.add_argument("--size", type=int, default=30, help="population size")
    parser.add_argument("--gens", type=int, default=40, help="max generations")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="MultiprocessingScheduler を使う (CPU-bound fitness 向け)",
    )
    parser.add_argument("--workers", type=int, default=0, help="0 で auto (cpu_count)")
    parser.add_argument("--out", type=Path, default=None, help="JSONL 出力先 dir")
    args = parser.parse_args()

    bounds, fitness_fn, labels = _build_problem(args.problem)
    pop = Population.random(bounds=bounds, size=args.size, seed=args.seed, labels=labels)

    scheduler = (
        MultiprocessingScheduler(n_workers=args.workers)
        if args.parallel
        else None  # default = serial
    )

    loop_kwargs = {
        "fitness_fn": fitness_fn,
        "selection": TournamentSelection(k=3),
        "crossover": BlendCrossover(alpha=0.3),
        "mutation": ChainedMutation(
            mutations=(
                GaussianMutation(sigma=0.15, p=0.2),
                ResetMutation(p=0.02),
            )
        ),
        "elitism": ElitismSelection(top_n=2),
    }
    if scheduler is not None:
        loop_kwargs["scheduler"] = scheduler

    loop = EvolutionLoop(**loop_kwargs)
    config = EvolutionConfig(
        max_generations=args.gens,
        patience=max(10, args.gens // 3),
        diversity_floor=1e-6,
        out_dir=args.out,
        log_progress=True,
    )
    print(
        f"[demo_evolutionary_loop] problem={args.problem} size={args.size} "
        f"gens={args.gens} parallel={args.parallel} workers={args.workers}",
        flush=True,
    )
    result = loop.run(pop, config)

    print("---")
    print(f"stopped_reason: {result.stopped_reason}")
    print(f"best_score:     {result.best_score:.6f}")
    print(f"best_values:    {result.best_individual.genome.as_dict()}")
    print(f"elapsed:        {result.elapsed_seconds:.2f}s")
    print(f"generations:    {result.final_population.generation}")
    print(f"final_diversity: {result.stats_history[-1].diversity_l2:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
