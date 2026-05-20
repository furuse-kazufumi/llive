#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Demo: edge weight decay の variants を SynapticSelector で自動収束させる.

llive memory tier の edge graph は時間で重みを減衰させる. N (edges 数) に
依存して最良 implementation が変動する:

    N=10        — interpreter overhead が支配的, python listcomp が勝つ可能性
    N=1000      — numpy 化メリットが微妙
    N=100000    — numpy が圧勝

5 variants (`src/llive/perf/variants/decay_variants.py`):
    - py_loop, py_listcomp, py_map           — pure Python
    - np_inplace, np_einsum                  — numpy

Phase B-4 (`docs/experiments/optimize_core_2026_05_20.md`).

実行例:
    py -3.11 scripts/demo_synaptic_decay.py --n 100
    py -3.11 scripts/demo_synaptic_decay.py --n 100000 --iters 500
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from llive.perf.synaptic_selector import StrategyVariant, SynapticSelector  # noqa: E402
from llive.perf.variants.decay_variants import ALL_VARIANTS  # noqa: E402


def run_demo(n: int, iters: int, seed: int = 2026) -> dict:
    variants = [StrategyVariant(name=name, impl=fn) for name, fn in ALL_VARIANTS]
    selector = SynapticSelector(
        variants=variants,
        learning_rate=0.10,
        exploration_rate=0.15,
        rng=random.Random(seed),
    )

    rng = np.random.default_rng(seed)
    rate = 0.95

    for _ in range(iters):
        # input は毎回作って cache 効きを除外
        weights_np = rng.uniform(0.0, 10.0, size=n)
        weights_py = list(weights_np)
        v = selector.choose()
        # variant 名で input 型を切替
        impl_input = weights_np if v.name.startswith("np_") else weights_py
        t0 = time.perf_counter()
        _ = v.impl(impl_input, rate)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        selector.record_result(v, elapsed_ms)

    return {
        "n": n,
        "iters": iters,
        "snapshot": selector.snapshot(),
        "converged_to": selector.converge().name,
    }


def _fmt_table(snap: list[dict]) -> str:
    header = "| variant | weight | n_calls | avg_latency_ms |"
    sep = "|---|---:|---:|---:|"
    rows = [header, sep]
    for s in sorted(snap, key=lambda x: -x["weight"]):
        rows.append(
            f"| {s['name']} | {s['weight']:.3f} | {s['n_calls']} | {s['avg_latency_ms']:.5f} |"
        )
    return "\n".join(rows)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--n", type=int, default=1000, help="edge / weight 数")
    p.add_argument("--iters", type=int, default=300, help="反復回数")
    p.add_argument("--seed", type=int, default=2026, help="乱数シード")
    args = p.parse_args()

    print(f"[demo] n={args.n} iters={args.iters} seed={args.seed}")
    t0 = time.perf_counter()
    result = run_demo(args.n, args.iters, args.seed)
    elapsed = time.perf_counter() - t0
    print(f"[demo] elapsed: {elapsed:.2f}s")
    print(f"[demo] converged_to: {result['converged_to']}")
    print()
    print(_fmt_table(result["snapshot"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
