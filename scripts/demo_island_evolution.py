# SPDX-License-Identifier: Apache-2.0
"""Demo — N island × independent EvolutionLoop + periodic migration.

ユーザー提案 (2026-05-23): 「適当なタイミングで同期を取れば母数を増やせる」.
これは Coarse-grained Parallel GA (Cohoon et al. 1987 / Whitley et al. 1999)
の核心で, llive にはすでに ``IslandModel`` が CE-33 として実装済.
本 demo はそれと EvolutionLoop の 1 世代ステップを結合し,
ThreadPoolExecutor で全 island を並列前進させる orchestrator.

JSONL は island ごとに分離し ``migrations.jsonl`` も別途出力するので,
``scripts/evolution_dashboard.py`` で「進化ポートフォリオ」として可視化可能.

使い方::

    py -3.11 scripts/demo_island_evolution.py \\
        --problem sphere \\
        --n-islands 5 --island-size 30 \\
        --migration-interval 5 --migration-size 2 \\
        --max-generations 30 \\
        --max-workers 4 \\
        --out out/island_evolution

ボトル別 honest disclosure:

* migration_interval が小さいほど全島が単一集団化, 大きいほど局所解収束.
  経験則は 5-20 世代に 1 回. 多様性 collapse の予兆は ``diversity_l2`` の
  急減で観察する.
* ThreadPoolExecutor は fitness が numpy / pure-Python なら有効. GIL を
  解放しない pure-Python heavy では process pool (MultiprocessingScheduler)
  に切り替えること.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from llive.perf.evolutionary import (
    BlendCrossover,
    ChainedMutation,
    ElitismSelection,
    Fitness,
    GaussianMutation,
    GenomeBounds,
    Individual,
    IslandModel,
    Population,
    PopulationStats,
    ResetMutation,
    TournamentSelection,
    rosenbrock_fitness,
    sphere_fitness,
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
class IslandConfig:
    n_islands: int
    island_size: int
    migration_interval: int
    migration_size: int
    topology: str
    migration_policy: str
    max_generations: int
    max_workers: int
    out_dir: Path
    seed: int


def _build_problem(
    name: str,
) -> tuple[GenomeBounds, Fitness, tuple[str, ...]]:
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
    raise ValueError(f"unknown problem: {name}")


def _step_island(
    island: Population,
    fitness_fn: Fitness,
    selection: Callable,
    crossover: Callable,
    mutation: Callable,
    elitism: ElitismSelection,
    rng_seed: int,
) -> PopulationStats:
    """1 世代だけ前進: 未評価個体を評価 → 統計算出 → 次世代 breeding."""
    rng = np.random.default_rng(rng_seed)

    for ind in island.individuals:
        if ind.fitness is None:
            ind.record_fitness(fitness_fn(ind.genome))

    stats = island.compute_stats()

    next_gen = island.generation + 1
    next_inds: list[Individual] = []
    for e in elitism.select(island):
        next_inds.append(
            Individual.from_genome(
                e.genome,
                parent_ids=(e.individual_id,),
                birth_generation=next_gen,
            )
        )
    while len(next_inds) < island.size:
        a = selection(island, rng)
        b = selection(island, rng)
        child = crossover(a.genome, b.genome, rng)
        child = mutation(child, rng)
        next_inds.append(
            Individual.from_genome(
                child,
                parent_ids=(a.individual_id, b.individual_id),
                birth_generation=next_gen,
            )
        )
    next_seed = int(rng.integers(0, 2**31 - 1))
    island.replace(next_inds, new_seed=next_seed)
    return stats


def _write_manifest(cfg: IslandConfig, problem: str, started_at: float) -> None:
    """run 開始時に書き出す不変メタデータ. dashboard が max_generations を
    知って進捗率を出すために使う. summary.json は run 終了時のみ書かれる
    ため, 進行中は manifest から max を読む."""
    manifest = {
        "started_at_epoch": float(started_at),
        "problem": problem,
        "n_islands": cfg.n_islands,
        "island_size": cfg.island_size,
        "migration_interval": cfg.migration_interval,
        "migration_size": cfg.migration_size,
        "topology": cfg.topology,
        "migration_policy": cfg.migration_policy,
        "max_generations": cfg.max_generations,
        "max_workers": cfg.max_workers,
        "seed": cfg.seed,
    }
    (cfg.out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def run_island_evolution(cfg: IslandConfig, problem: str = "sphere") -> dict:
    bounds, fitness_fn, labels = _build_problem(problem)
    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    for i in range(cfg.n_islands):
        (cfg.out_dir / f"island_{i:02d}").mkdir(parents=True, exist_ok=True)
    _write_manifest(cfg, problem, started_at=time.time())

    islands = [
        Population.random(
            bounds=bounds,
            size=cfg.island_size,
            seed=cfg.seed + 1000 * i,
            labels=labels,
        )
        for i in range(cfg.n_islands)
    ]
    model = IslandModel(
        islands=islands,
        topology=cfg.topology,  # type: ignore[arg-type]
        migration_size=cfg.migration_size,
        migration_policy=cfg.migration_policy,  # type: ignore[arg-type]
        migration_interval=cfg.migration_interval,
    )

    selection = TournamentSelection(k=3)
    crossover = BlendCrossover(alpha=0.3)
    mutation = ChainedMutation(
        mutations=(GaussianMutation(sigma=0.15, p=0.2), ResetMutation(p=0.02))
    )
    elitism = ElitismSelection(top_n=2)

    migration_rng = np.random.default_rng(cfg.seed + 7919)
    start = time.perf_counter()
    migration_log: list[dict] = []

    def _step_at(idx: int, gen: int) -> tuple[int, PopulationStats]:
        sub_seed = (cfg.seed * 1_000_003 + idx * 31 + gen) & 0x7FFFFFFF
        stats = _step_island(
            model.islands[idx],
            fitness_fn,
            selection,
            crossover,
            mutation,
            elitism,
            sub_seed,
        )
        return idx, stats

    for gen in range(cfg.max_generations):
        indices = list(range(len(model.islands)))
        if cfg.max_workers > 1:
            with ThreadPoolExecutor(max_workers=cfg.max_workers) as pool:
                results = list(pool.map(lambda i: _step_at(i, gen), indices))
        else:
            results = [_step_at(i, gen) for i in indices]

        for idx, stats in sorted(results, key=lambda t: t[0]):
            stats_dict = stats.to_dict()
            stats_dict["island_id"] = idx
            stats_dict["wall_gen"] = gen
            with (cfg.out_dir / f"island_{idx:02d}" / "generations.jsonl").open(
                "a", encoding="utf-8"
            ) as fh:
                fh.write(json.dumps(stats_dict, ensure_ascii=False) + "\n")

        mig_stats = model.migrate(migration_rng)
        if mig_stats["total_migrants"] > 0:
            mig_record = {
                "wall_gen": gen,
                "model_gen_counter": model.generation_counter,
                "total_migrants": mig_stats["total_migrants"],
                "islands_affected": mig_stats["islands_affected"],
                "topology": cfg.topology,
                "policy": cfg.migration_policy,
                "island_sizes": model.island_sizes(),
            }
            migration_log.append(mig_record)
            with (cfg.out_dir / "migrations.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(mig_record, ensure_ascii=False) + "\n")

        # stats から best を取る (replace 後の bests は新個体 = 未評価で -inf になる)
        bests_per_island = [s.best_score for _, s in sorted(results, key=lambda t: t[0])]
        global_best_now = max(bests_per_island) if bests_per_island else float("-inf")
        print(
            f"[gen {gen:03d}] effective_pop={model.total_size()} "
            f"global_best={global_best_now:.4e} "
            f"migrants={mig_stats['total_migrants']} "
            f"sizes={model.island_sizes()}",
            flush=True,
        )

    # final pass: 子世代 (まだ評価されていない) を評価して global best を確定
    for island in model.islands:
        for ind in island.individuals:
            if ind.fitness is None:
                ind.record_fitness(fitness_fn(ind.genome))

    global_best = float("-inf")
    global_best_genome = None
    for island in model.islands:
        for ind in island.individuals:
            if ind.fitness is not None and ind.score > global_best:
                global_best = ind.score
                global_best_genome = ind.genome.as_dict()

    elapsed = time.perf_counter() - start
    summary = {
        "problem": problem,
        "n_islands": cfg.n_islands,
        "island_size": cfg.island_size,
        "effective_pop": model.total_size(),
        "migration_interval": cfg.migration_interval,
        "migration_size": cfg.migration_size,
        "topology": cfg.topology,
        "migration_policy": cfg.migration_policy,
        "max_generations": cfg.max_generations,
        "max_workers": cfg.max_workers,
        "elapsed_seconds": elapsed,
        "global_best_score": global_best,
        "global_best_genome": global_best_genome,
        "n_migration_events": len(migration_log),
        "final_island_sizes": model.island_sizes(),
    }
    (cfg.out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("---")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--problem", default="sphere", choices=["sphere", "rosenbrock"]
    )
    parser.add_argument("--n-islands", type=int, default=5)
    parser.add_argument("--island-size", type=int, default=30)
    parser.add_argument("--migration-interval", type=int, default=5)
    parser.add_argument("--migration-size", type=int, default=2)
    parser.add_argument(
        "--topology", default="ring", choices=["ring", "fully", "star"]
    )
    parser.add_argument(
        "--migration-policy",
        default="best",
        choices=["best", "random", "worst"],
    )
    parser.add_argument("--max-generations", type=int, default=30)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--out", type=Path, default=Path("out/island_evolution")
    )
    args = parser.parse_args()

    cfg = IslandConfig(
        n_islands=args.n_islands,
        island_size=args.island_size,
        migration_interval=args.migration_interval,
        migration_size=args.migration_size,
        topology=args.topology,
        migration_policy=args.migration_policy,
        max_generations=args.max_generations,
        max_workers=args.max_workers,
        out_dir=args.out,
        seed=args.seed,
    )
    run_island_evolution(cfg, problem=args.problem)
    return 0


if __name__ == "__main__":
    sys.exit(main())
