# SPDX-License-Identifier: Apache-2.0
"""LV × SR-01 demo — 38 dim self-adaptive σSA-ES で llive variant を進化させる.

実行例::

    py -3.11 scripts/demo_self_adaptive_variant.py --size 30 --gens 15 --seed 7

出力: 世代ごとに best / mean / σ 平均を 1 行 print + 最終集団の σ 統計.

mock fitness (credential 不要) なので, ローカル環境のみで完走する.
要件根拠: ``docs/requirements_v0.D_self_referential_and_llm_operators.md`` SR-01.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

from llive.perf.evolutionary import (
    ElitismSelection,
    EvolutionConfig,
    EvolutionLoop,
    Genome,
    Individual,
    Population,
    SegmentCrossover,
    TournamentSelection,
    build_self_adaptive_variant_bounds,
    initialize_self_adaptive_variant_genome_values,
    make_self_adaptive_variant_mutation,
    mock_variant_fitness_factory,
    wrap_fitness_for_extended_genome,
)


def _print_generation_stats(pop: Population, gen: int) -> None:
    scores = np.array([
        ind.fitness.score for ind in pop.individuals if ind.fitness is not None
    ])
    sigmas = np.array([
        list(ind.genome.values[19:]) for ind in pop.individuals
    ])
    print(
        f"[gen {gen:03d}] "
        f"best={scores.max():.4f} mean={scores.mean():.4f} "
        f"sigma_mean={sigmas.mean():.4f} sigma_std={sigmas.std():.4f}"
    )


def _ensure_utf8_stdout() -> None:
    """Force stdout to UTF-8 (Windows cp932 mojibake guard).

    See memory ``feedback_cli_utf8_stdout_pattern`` and llmesh
    commits 11b38e7 / 798bf93 for the rationale.
    """
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):  # pragma: no cover
        pass


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(prog="demo_self_adaptive_variant")
    parser.add_argument("--size", type=int, default=20, help="集団 size")
    parser.add_argument("--gens", type=int, default=12, help="世代数")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sigma-init", type=float, default=0.2)
    parser.add_argument("--out", type=Path, default=None, help="snapshot 出力先")
    args = parser.parse_args(argv)

    rng = np.random.default_rng(args.seed)
    bounds, labels = build_self_adaptive_variant_bounds()

    print(f"=== llive self-adaptive variant demo (v0.D SR-01) ===")
    print(f"size={args.size} gens={args.gens} seed={args.seed} sigma_init={args.sigma_init}")
    print(f"genome dim = {bounds.n_dims} (19 object + 19 sigma)")
    print()

    inds = []
    for _ in range(args.size):
        obj = bounds.sample_uniform(rng)[:19]
        full = initialize_self_adaptive_variant_genome_values(
            obj, sigma_init=args.sigma_init
        )
        inds.append(
            Individual.from_genome(
                Genome.from_values(full, bounds=bounds, labels=labels)
            )
        )
    pop = Population(individuals=inds, bounds=bounds, seed=args.seed)

    fitness = wrap_fitness_for_extended_genome(mock_variant_fitness_factory())
    loop = EvolutionLoop(
        fitness_fn=fitness,
        selection=TournamentSelection(k=3),
        crossover=SegmentCrossover(segments=((0, 19), (19, 38)), p=0.5),
        mutation=make_self_adaptive_variant_mutation(),
        elitism=ElitismSelection(top_n=2),
        on_generation_end=lambda p, s: _print_generation_stats(p, s.generation),
    )
    config = EvolutionConfig(
        max_generations=args.gens,
        patience=999,
        log_progress=False,
        out_dir=args.out,
    )
    result = loop.run(pop, config)

    print()
    print("=== Final ===")
    print(f"best_score: {result.best_score:.4f}")
    print(f"stopped_reason: {result.stopped_reason}")
    final_sigmas = np.array([
        list(ind.genome.values[19:]) for ind in result.final_population.individuals
    ])
    print(
        f"sigma final: mean={final_sigmas.mean():.4f} "
        f"min={final_sigmas.min():.4f} max={final_sigmas.max():.4f}"
    )
    print(
        f"sigma initial: {args.sigma_init:.4f} "
        f"({'shrunk' if final_sigmas.mean() < args.sigma_init else 'grew'})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
