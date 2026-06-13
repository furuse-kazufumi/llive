#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Demo: decay variants を UCBSynapticSelector で自動収束.

B-4 で SynapticSelector (ε-greedy) は微差 latency でも真の最良に収束
しない病理を示した. UCB 版で同じケースを試し, np_inplace に正しく
収束するかを検証.

Phase B-5 (`docs/experiments/optimize_core_2026_05_20.md`).

実行例:
    py -3.11 scripts/demo_synaptic_decay_ucb.py --n 10000 --iters 500
    py -3.11 scripts/demo_synaptic_decay_ucb.py --n 100000 --iters 300
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

from llive.perf.synaptic_selector import (  # noqa: E402
    StrategyVariant,
    UCBSynapticSelector,
)
from llive.perf.variants.decay_variants import ALL_VARIANTS  # noqa: E402


def run_demo(n: int, iters: int, seed: int = 2026) -> dict:
    variants = [StrategyVariant(name=name, impl=fn) for name, fn in ALL_VARIANTS]
    selector = UCBSynapticSelector(
        variants=variants,
        rng=random.Random(seed),
    )

    rng = np.random.default_rng(seed)
    rate = 0.95

    for _ in range(iters):
        weights_np = rng.uniform(0.0, 10.0, size=n)
        weights_py = list(weights_np)
        v = selector.choose()
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
    header = "| variant | reward | n_calls | avg_latency_ms |"
    sep = "|---|---:|---:|---:|"
    rows = [header, sep]
    for s in sorted(snap, key=lambda x: -x["reward"]):
        rows.append(
            f"| {s['name']} | {s['reward']:.4f} | {s['n_calls']} | {s['avg_latency_ms']:.5f} |"
        )
    return "\n".join(rows)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--n", type=int, default=10000, help="edge / weight 数")
    p.add_argument("--iters", type=int, default=500, help="反復回数")
    p.add_argument("--seed", type=int, default=2026, help="乱数シード")
    args = p.parse_args()

    print(f"[demo-ucb] n={args.n} iters={args.iters} seed={args.seed}")
    t0 = time.perf_counter()
    result = run_demo(args.n, args.iters, args.seed)
    elapsed = time.perf_counter() - t0
    print(f"[demo-ucb] elapsed: {elapsed:.2f}s")
    print(f"[demo-ucb] converged_to: {result['converged_to']}")
    print()
    print(_fmt_table(result["snapshot"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
