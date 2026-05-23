# SPDX-License-Identifier: Apache-2.0
"""migration_interval が探索性能にどう影響するか比較する小実験.

ユーザー (2026-05-23): "適当なタイミングで同期を取れば母数を増やせる. そこから
何か発見があるかもしれない". → migration_interval を {1, 5, 1000} で振って,
5 islands × 30 個体 (effective_pop=150) 構成で sphere/rosenbrock を解く.

interval=1000 は実質 migration なし (= 5 完全独立 sub-population),
interval=1 は毎世代同期 (= 単一巨大集団に近い), interval=5 は中間.

ベースラインとして 1 island × 150 (= effective_pop 同じ, 同期も migration も
無い完全単集団) も並べる. 5 seed の平均 / std で robust 比較.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean, stdev

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import demo_island_evolution as die  # noqa: E402


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


VARIANTS: list[tuple[str, dict]] = [
    ("single_pop_150", dict(n_islands=1, island_size=150, migration_interval=1)),
    ("islands_5x30_int1", dict(n_islands=5, island_size=30, migration_interval=1)),
    ("islands_5x30_int5", dict(n_islands=5, island_size=30, migration_interval=5)),
    ("islands_5x30_int1000", dict(n_islands=5, island_size=30, migration_interval=1000)),
]


def run_one(
    *,
    variant_name: str,
    variant_kwargs: dict,
    problem: str,
    seed: int,
    max_generations: int,
    base_out: Path,
) -> dict:
    out_dir = base_out / problem / variant_name / f"seed_{seed}"
    cfg = die.IslandConfig(
        n_islands=variant_kwargs["n_islands"],
        island_size=variant_kwargs["island_size"],
        migration_interval=variant_kwargs["migration_interval"],
        migration_size=2,
        topology="ring",
        migration_policy="best",
        max_generations=max_generations,
        max_workers=1,  # serial for honest per-seed comparison
        out_dir=out_dir,
        seed=seed,
    )
    return die.run_island_evolution(cfg, problem=problem)


def main() -> int:
    _ensure_utf8_stdout()
    base_out = Path("out/migration_interval_comparison")
    base_out.mkdir(parents=True, exist_ok=True)
    seeds = [42, 7, 123, 2024, 31415]
    max_generations = 40
    problems = ["sphere", "rosenbrock"]

    results: dict[str, dict[str, list[float]]] = {}
    for problem in problems:
        results[problem] = {}
        for variant_name, kwargs in VARIANTS:
            scores: list[float] = []
            elapsed: list[float] = []
            for seed in seeds:
                summary = run_one(
                    variant_name=variant_name,
                    variant_kwargs=kwargs,
                    problem=problem,
                    seed=seed,
                    max_generations=max_generations,
                    base_out=base_out,
                )
                scores.append(summary["global_best_score"])
                elapsed.append(summary["elapsed_seconds"])
            results[problem][variant_name] = {
                "scores": scores,
                "mean": mean(scores),
                "std": stdev(scores) if len(scores) > 1 else 0.0,
                "best": max(scores),
                "worst": min(scores),
                "mean_elapsed_sec": mean(elapsed),
            }

    aggregate_path = base_out / "aggregate.json"
    aggregate_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print()
    print("=" * 88)
    print(
        f"{'problem':<11} {'variant':<22} {'mean':>14} {'std':>13} {'best':>14} {'wall':>8}"
    )
    print("-" * 88)
    for problem, by_variant in results.items():
        for variant_name, stats in by_variant.items():
            print(
                f"{problem:<11} {variant_name:<22} "
                f"{stats['mean']:>14.4e} {stats['std']:>13.4e} "
                f"{stats['best']:>14.4e} {stats['mean_elapsed_sec']:>7.2f}s"
            )
    print("=" * 88)
    print(f"detail: {aggregate_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
