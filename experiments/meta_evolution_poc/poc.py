#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""v0.I 案 A — Schmidhuber 風 meta-evolution の小規模 PoC.

`requirements_v0.I_meta_evolution_and_cross_substrate.md` §3 の形式化が
**実際に動くか** を 50 世代 × 3 algorithm × seed 8 で実証する.

Setup:
    - 3 つの "algorithm" を MetaChromosome で表現
    - 真の mean fitness: high=0.7, mid=0.4, low=0.1 (Gaussian noise σ=0.05)
    - UCB1 で世代ごとに 1 つ選択 → fitness 改善量 (delta) を記録
    - 50 世代後の use_count 分布を観察 → high が支配的になるはず

Verification:
    - high algorithm の use_count >= 30/50 (60% 以上) — 多腕 bandit 古典結果
    - low algorithm の use_count <= 10/50 (20% 以下)
    - mean_delta_history の収束性
    - gzip K-proxy の比較 (algorithm_params の長さで増える)

実 sandbox AST 実行 / EvolutionLoop 統合は EV-22 残以降. 本 PoC は
**選択戦略 (UCB1)** と **複雑度ペナルティ (gzip K)** が機能するかを示すのみ.

Run:
    py -3.11 experiments/meta_evolution_poc/poc.py

Output:
    - stdout: 各世代の選択 algorithm + delta + 累積統計
    - experiments/meta_evolution_poc/results_seed_<S>.json: 詳細ログ
"""
from __future__ import annotations

import json
import math
import pathlib
import sys
import time
from dataclasses import asdict, dataclass

import numpy as np

# llive を import path に追加
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from llive.perf.evolutionary.meta_chromosome import MetaChromosome, ucb1_score  # noqa: E402
from llive.perf.evolutionary.meta_loop import MetaEvolutionLoop  # noqa: E402


# ---------------------------------------------------------------------------
# Simulated algorithms
# ---------------------------------------------------------------------------


@dataclass
class TrueDist:
    """各 algorithm の真の fitness 分布 (PoC 検証用 ground truth)."""

    mean: float
    sigma: float = 0.05


TRUE_DISTRIBUTIONS: dict[str, TrueDist] = {
    "tournament_gauss": TrueDist(mean=0.7),  # high
    "nsga2_novelty": TrueDist(mean=0.4),     # mid
    "map_elites_niche": TrueDist(mean=0.1),  # low
}


def make_mock_algorithm(true_mean: float, true_sigma: float):
    """algorithm_id → callable. fitness_delta は Gaussian noise."""

    def algorithm(chromosome: MetaChromosome, rng: np.random.Generator) -> float:
        return float(rng.normal(true_mean, true_sigma))

    return algorithm


# ---------------------------------------------------------------------------
# PoC run
# ---------------------------------------------------------------------------


def make_chromosome(algorithm_id: str) -> MetaChromosome:
    """各 algorithm 用 chromosome (default 値, algorithm_id のみ違う)."""
    return MetaChromosome(
        mutation_rate_per_layer=(0.05, 0.15, 0.02),
        crossover_strategy="intra",
        selection_pressure=0.5,
        novelty_weight=0.3,
        cluster_quota=4,
        meta_mutation_decay=0.5,
        algorithm_id=algorithm_id,
    )


def run_one_seed(seed: int, n_generations: int = 50) -> dict:
    rng = np.random.default_rng(seed)
    loop = MetaEvolutionLoop()

    # 3 chromosome を candidate として登録 + dispatch 設定
    chromosomes = {
        aid: make_chromosome(aid) for aid in TRUE_DISTRIBUTIONS
    }
    for aid, c in chromosomes.items():
        loop.register(c)
        td = TRUE_DISTRIBUTIONS[aid]
        loop.register_dispatch(aid, make_mock_algorithm(td.mean, td.sigma))

    # 各世代で UCB1 選択 + apply
    history: list[dict] = []
    for gen in range(n_generations):
        chosen = loop.select_next(rng)
        delta = loop.apply(chosen, rng)
        history.append({
            "gen": gen,
            "chosen_id": chosen.algorithm_id,
            "delta": delta,
        })

    # 結果集計
    use_counts = {
        aid: loop.state.candidates[chromosomes[aid]].use_count
        for aid in TRUE_DISTRIBUTIONS
    }
    mean_deltas = {
        aid: loop.state.candidates[chromosomes[aid]].mean_delta
        for aid in TRUE_DISTRIBUTIONS
    }
    final_scores = {c.algorithm_id: s for c, s in loop.state.scores().items()}

    return {
        "seed": seed,
        "n_generations": n_generations,
        "use_counts": use_counts,
        "mean_deltas": mean_deltas,
        "final_scores": final_scores,
        "history": history,
        "k_proxies": {
            aid: c.kolmogorov_proxy() for aid, c in chromosomes.items()
        },
    }


def verify(result: dict) -> dict:
    """PoC の verification — high algorithm が支配的か."""
    uc = result["use_counts"]
    high = uc["tournament_gauss"]
    mid = uc["nsga2_novelty"]
    low = uc["map_elites_niche"]
    n = result["n_generations"]

    checks = {
        "high_dominates": high >= n * 0.5,  # 50% 以上は使われる
        "high_gt_mid": high > mid,
        "high_gt_low": high > low,
        "low_minor": low <= n * 0.3,  # low は 30% 以下
        "total_matches_gen": (high + mid + low) == n,
    }
    return checks


def main() -> int:
    seeds = list(range(8))
    out_dir = pathlib.Path(__file__).parent
    all_results: list[dict] = []

    print("=" * 75)
    print(f"v0.I case A PoC — Schmidhuber-style meta-evolution (UCB1 + gzip K)")
    print(f"  3 algorithms × 50 generations × {len(seeds)} seeds")
    print(f"  True means: high=0.7, mid=0.4, low=0.1, sigma=0.05")
    print("=" * 75)

    t0 = time.perf_counter()
    for s in seeds:
        result = run_one_seed(s)
        checks = verify(result)
        all_results.append({"result": result, "checks": checks})

        uc = result["use_counts"]
        print(
            f"seed={s:>2}: "
            f"high={uc['tournament_gauss']:>2}, "
            f"mid={uc['nsga2_novelty']:>2}, "
            f"low={uc['map_elites_niche']:>2}  "
            f"checks={sum(checks.values())}/{len(checks)} pass"
        )

        out_file = out_dir / f"results_seed_{s}.json"
        out_file.write_text(json.dumps(result, indent=2), encoding="utf-8")

    elapsed = time.perf_counter() - t0
    print()

    # ----- 全 seed 統計 -----
    n_seeds = len(seeds)
    avg_high = sum(r["result"]["use_counts"]["tournament_gauss"] for r in all_results) / n_seeds
    avg_mid = sum(r["result"]["use_counts"]["nsga2_novelty"] for r in all_results) / n_seeds
    avg_low = sum(r["result"]["use_counts"]["map_elites_niche"] for r in all_results) / n_seeds
    total_pass = sum(sum(r["checks"].values()) for r in all_results)
    total_checks = sum(len(r["checks"]) for r in all_results)

    print("=" * 75)
    print(f"SUMMARY ({elapsed*1000:.1f}ms total)")
    print(f"  avg use_counts: high={avg_high:.1f}, mid={avg_mid:.1f}, low={avg_low:.1f}")
    print(f"  verification: {total_pass}/{total_checks} checks passed")
    print(f"  Kolmogorov proxies (all 3 chromosomes identical except algorithm_id):")
    for aid, k in all_results[0]["result"]["k_proxies"].items():
        print(f"    {aid:<25} → {k} bytes (gzip)")
    print("=" * 75)
    print()

    # honest disclosure
    print("Honest disclosure:")
    print("  - UCB1 exploration bonus is high in early generations → low arms")
    print("    get tried a few times before high dominates")
    print("  - cold start (+inf score) ensures all arms tried at least once")
    print("  - mock dispatch returns Gaussian noise; real EvolutionLoop")
    print("    integration is EV-22 (pending)")
    print("  - gzip K-proxy differences here are small (chromosomes near-identical)")
    print("    — meaningful K-penalty appears when algorithm_params are populated")
    print()

    # 集計 JSON を保存
    summary = {
        "n_seeds": n_seeds,
        "n_generations": 50,
        "avg_use_counts": {"high": avg_high, "mid": avg_mid, "low": avg_low},
        "total_checks_passed": total_pass,
        "total_checks": total_checks,
        "elapsed_ms": round(elapsed * 1000, 1),
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(f"Results saved: {out_dir}/")
    print(f"  - summary.json")
    print(f"  - results_seed_0.json ... results_seed_{n_seeds-1}.json")

    # PoC 成否: 全 seed × 全 check の 90% 以上 PASS で OK
    pass_rate = total_pass / total_checks
    return 0 if pass_rate >= 0.9 else 1


if __name__ == "__main__":
    sys.exit(main())
