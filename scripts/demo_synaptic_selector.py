#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Demo: SynapticSelector で「top-K 抽出」の最適 implementation を自動収束させる.

問題設定:
  N 個の整数から上位 K 個を抽出する hot path がある. 候補は 3 つ:

    1. full_sort       — sorted(data, reverse=True)[:K]
    2. partial_sort    — bisect ベースの partial sort
    3. heapq_nlargest  — heapq.nlargest(K, data)

データサイズ・K 比により最良は変動する.

SynapticSelector に 3 variant を載せて, 反復呼出ししながら重みが自動的に
最良候補へ収束する様子を観察する.

実行:
    py -3.11 scripts/demo_synaptic_selector.py
    py -3.11 scripts/demo_synaptic_selector.py --n 10000 --k 50 --iters 500

このデモは llive コア最適化セッション (2026-05-20) の Phase B-1
(`docs/experiments/optimize_core_2026_05_20.md`) の試適用例.
"""
from __future__ import annotations

import argparse
import heapq
import random
import sys
import time
from pathlib import Path

# `pip install -e .` していない環境でも動くように src を path に追加.
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from llive.perf.synaptic_selector import StrategyVariant, SynapticSelector  # noqa: E402


# ---------------------------------------------------------------------------
# 候補 implementations
# ---------------------------------------------------------------------------


def top_k_full_sort(data: list[int], k: int) -> list[int]:
    return sorted(data, reverse=True)[:k]


def top_k_partial_sort(data: list[int], k: int) -> list[int]:
    """heapq.nlargest を partial-sort 相当として使う変種.

    本来は merge-sort ベースの partial sort もありうるが Python stdlib に
    存在しないので, ここは min-heap を経由する亜種を用意 (impl A と差が
    出るかの観察用).
    """
    if k >= len(data):
        return sorted(data, reverse=True)
    # min-heap で k 要素保持 → 最後にソート
    h: list[int] = []
    for x in data:
        if len(h) < k:
            heapq.heappush(h, x)
        elif x > h[0]:
            heapq.heapreplace(h, x)
    return sorted(h, reverse=True)


def top_k_heapq_nlargest(data: list[int], k: int) -> list[int]:
    return heapq.nlargest(k, data)


# ---------------------------------------------------------------------------
# 実験 runner
# ---------------------------------------------------------------------------


def _gen_data(n: int, seed: int = 0) -> list[int]:
    rng = random.Random(seed)
    return [rng.randint(0, 10_000_000) for _ in range(n)]


def run_demo(n: int, k: int, iters: int) -> dict:
    variants = [
        StrategyVariant(name="full_sort", impl=top_k_full_sort),
        StrategyVariant(name="partial_sort_heap", impl=top_k_partial_sort),
        StrategyVariant(name="heapq_nlargest", impl=top_k_heapq_nlargest),
    ]
    selector = SynapticSelector(
        variants=variants,
        learning_rate=0.10,
        exploration_rate=0.15,
        rng=random.Random(2026),
    )

    # 1 回ごとに新規データを生成 (cache を効かせない)
    base_seed = 0
    for i in range(iters):
        data = _gen_data(n, seed=base_seed + i)
        result = selector.call(data, k)
        # 正しさ smoke: 3 variant とも同じ top-K を返すはず
        if i == 0:
            ref = sorted(data, reverse=True)[:k]
            assert result == ref, f"variant returned wrong top-K: {result[:5]} vs {ref[:5]}"

    snapshot = selector.snapshot()
    converged = selector.converge()
    return {
        "n": n,
        "k": k,
        "iters": iters,
        "snapshot": snapshot,
        "converged_to": converged.name,
    }


def _fmt_table(snap: list[dict]) -> str:
    header = "| variant | weight | n_calls | avg_latency_ms |"
    sep = "|---|---:|---:|---:|"
    rows = [header, sep]
    for s in sorted(snap, key=lambda x: -x["weight"]):
        rows.append(
            f"| {s['name']} | {s['weight']:.3f} | {s['n_calls']} | {s['avg_latency_ms']:.3f} |"
        )
    return "\n".join(rows)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--n", type=int, default=10_000, help="データサイズ")
    p.add_argument("--k", type=int, default=10, help="抽出する top-K の K")
    p.add_argument("--iters", type=int, default=300, help="繰返し回数")
    args = p.parse_args()

    print(f"[demo] n={args.n} k={args.k} iters={args.iters}")
    t0 = time.perf_counter()
    result = run_demo(args.n, args.k, args.iters)
    elapsed = time.perf_counter() - t0
    print(f"[demo] elapsed: {elapsed:.2f}s")
    print(f"[demo] converged_to: {result['converged_to']}")
    print()
    print(_fmt_table(result["snapshot"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
