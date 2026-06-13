# SPDX-License-Identifier: Apache-2.0
"""Genome3D 4 階建て進化 demo (smoke).

ユーザー指示 (2026-05-23): Genome3D に c_factors を統合した後の
「実際に 4 階建てが進化するか」smoke. mock fitness で c_factors の特定 pattern を
探索する. dashboard 互換 JSONL を出すので, ``scripts/evolution_dashboard.py``
でそのまま観察可能.

# 何を進化させるか

c_factors (10 因子 × 4 メモリ層 = 40 cell 2D matrix) が target 値の uniform
matrix に近づくほど高 score, という mock 探索問題:

    score = -L2( c_factors.as_array() - target * ones(10, 4) )

* target=0.7 なら, default (uniform 0.5) からの最適化を観察できる.
* c_impl / c_prompt / c_meta も crossover で混ざるが, fitness には c_factors のみが
  寄与する設計 (4 階建てが破壊なく動くことの smoke が目的).

# 使い方

```
py -3.11 scripts/demo_genome3d_evolution.py \\
    --size 30 --gens 30 --target 0.7 --crossover intra \\
    --out out/genome3d_demo
```

dashboard 表示:

```
py -3.11 scripts/evolution_dashboard.py out/genome3d_demo --plain
```
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from llive.perf.evolutionary import (
    Genome3D,
    cross_layer_crossover,
    intra_layer_crossover,
)
from llive.perf.evolutionary.impl_chromosome import ImplChromosome
from llive.perf.evolutionary.meta_chromosome import MetaChromosome
from llive.perf.evolutionary.prompt_chromosome import PromptChromosome
from llive.perf.evolutionary.thought_factor_per_layer import (
    ThoughtFactorPerLayerChromosome,
)


def _ensure_utf8_stdout() -> None:
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


@dataclass
class Genome3DConfig:
    size: int
    max_generations: int
    target_value: float
    crossover_kind: str  # "intra" / "cross"
    elite_top: int
    tournament_k: int
    mutation_step: float
    out_dir: Path
    seed: int


def fitness_c_factors_target(genome: Genome3D, target: float) -> float:
    """c_factors の全 cell が target 値に近いほど高 score (max 0)."""
    arr = genome.c_factors.as_array()
    diff = arr - target
    return -float(np.sqrt(np.sum(diff * diff)))


def initial_population(rng: np.random.Generator, size: int) -> list[Genome3D]:
    """size 体 Genome3D を生成. c_factors のみ random で多様性確保, 他層は default."""
    return [
        Genome3D(
            c_impl=ImplChromosome.default(),
            c_prompt=PromptChromosome.default(),
            c_meta=MetaChromosome.default(),
            c_factors=ThoughtFactorPerLayerChromosome.random(rng),
        )
        for _ in range(size)
    ]


def _tournament_select(
    pop: list[Genome3D],
    scores: list[float],
    k: int,
    rng: np.random.Generator,
) -> Genome3D:
    indices = rng.choice(len(pop), size=k, replace=False)
    best_i = max(indices, key=lambda i: scores[int(i)])
    return pop[int(best_i)]


def _diversity_c_factors(pop: list[Genome3D]) -> float:
    """c_factors の pairwise L2 距離平均 (40-dim flatten)."""
    if len(pop) < 2:
        return 0.0
    flat = np.stack([g.c_factors.as_flat() for g in pop])
    diff = flat[:, None, :] - flat[None, :, :]
    dists = np.sqrt(np.sum(diff * diff, axis=-1))
    mask = ~np.eye(len(pop), dtype=bool)
    return float(dists[mask].mean())


def _write_manifest(cfg: Genome3DConfig) -> None:
    manifest = {
        "started_at_epoch": float(time.time()),
        "problem": "genome3d_c_factors_target",
        "n_islands": 1,
        "island_size": cfg.size,
        "migration_interval": 0,
        "migration_size": 0,
        "topology": "single",
        "migration_policy": "n/a",
        "max_generations": cfg.max_generations,
        "max_workers": 1,
        "seed": cfg.seed,
        "target_value": cfg.target_value,
        "crossover_kind": cfg.crossover_kind,
    }
    (cfg.out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def run_genome3d_evolution(cfg: Genome3DConfig) -> dict:
    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    island_dir = cfg.out_dir / "island_00"
    island_dir.mkdir(exist_ok=True)
    _write_manifest(cfg)

    rng = np.random.default_rng(cfg.seed)
    pop = initial_population(rng, cfg.size)
    crossover_fn: Callable = (
        intra_layer_crossover
        if cfg.crossover_kind == "intra"
        else cross_layer_crossover
    )

    start = time.perf_counter()

    for gen in range(cfg.max_generations):
        scores = [fitness_c_factors_target(g, cfg.target_value) for g in pop]
        score_arr = np.asarray(scores)
        diversity = _diversity_c_factors(pop)

        stats_dict = {
            "generation": gen,
            "n_individuals": len(pop),
            "best_score": float(score_arr.max()),
            "mean_score": float(score_arr.mean()),
            "std_score": float(score_arr.std()),
            "median_score": float(np.median(score_arr)),
            "diversity_l2": diversity,
            "seed": int(rng.integers(0, 2**31 - 1)),
            "island_id": 0,
            "wall_gen": gen,
        }
        with (island_dir / "generations.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(stats_dict, ensure_ascii=False) + "\n")
        print(
            f"[gen {gen:03d}] best={score_arr.max():+.4f} "
            f"mean={score_arr.mean():+.4f} "
            f"std={score_arr.std():.4f} "
            f"diversity={diversity:.4f}",
            flush=True,
        )

        # 次世代生成
        next_pop: list[Genome3D] = []
        sorted_idx = np.argsort(score_arr)[::-1]
        for i in sorted_idx[: cfg.elite_top]:
            next_pop.append(pop[int(i)])
        while len(next_pop) < cfg.size:
            a = _tournament_select(pop, scores, cfg.tournament_k, rng)
            b = _tournament_select(pop, scores, cfg.tournament_k, rng)
            child = crossover_fn(a, b, rng)
            child = child.sample_neighborhood(rng, step_size=cfg.mutation_step)
            next_pop.append(child)
        pop = next_pop

    elapsed = time.perf_counter() - start

    # 最終評価
    scores = [fitness_c_factors_target(g, cfg.target_value) for g in pop]
    score_arr = np.asarray(scores)
    best_idx = int(score_arr.argmax())
    best_g = pop[best_idx]

    summary = {
        "problem": "genome3d_c_factors_target",
        "target_value": cfg.target_value,
        "crossover_kind": cfg.crossover_kind,
        "n_islands": 1,
        "island_size": cfg.size,
        "effective_pop": cfg.size,
        "max_generations": cfg.max_generations,
        "max_workers": 1,
        "elapsed_seconds": elapsed,
        "global_best_score": float(score_arr.max()),
        "global_best_c_factors_mean": float(best_g.c_factors.as_array().mean()),
        "global_best_c_factors_std": float(best_g.c_factors.as_array().std()),
        "n_migration_events": 0,
        "final_island_sizes": [cfg.size],
    }
    (cfg.out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("---")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=30)
    parser.add_argument("--gens", type=int, default=30, dest="max_generations")
    parser.add_argument(
        "--target", type=float, default=0.7, dest="target_value"
    )
    parser.add_argument(
        "--crossover",
        default="intra",
        choices=["intra", "cross"],
        dest="crossover_kind",
    )
    parser.add_argument("--elite", type=int, default=2, dest="elite_top")
    parser.add_argument("--tournament-k", type=int, default=3)
    parser.add_argument("--mutation-step", type=float, default=0.1)
    parser.add_argument(
        "--out", type=Path, default=Path("out/genome3d_demo")
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    cfg = Genome3DConfig(
        size=args.size,
        max_generations=args.max_generations,
        target_value=args.target_value,
        crossover_kind=args.crossover_kind,
        elite_top=args.elite_top,
        tournament_k=args.tournament_k,
        mutation_step=args.mutation_step,
        out_dir=args.out,
        seed=args.seed,
    )
    run_genome3d_evolution(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
