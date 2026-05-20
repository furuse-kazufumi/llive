#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Demo: sliding window container を UCBSynapticSelector で自動収束.

操作: 「先頭 pop + 末尾 push を N 回連続で行う」 sliding window.
候補:
    - list_popzero  : list.pop(0) + append (O(N) pop)
    - list_slice    : lst[1:] + [x] (O(N) copy)
    - deque         : collections.deque(maxlen=N) (O(1))

理論的には deque が圧勝するはず. UCB で自動確認.

Phase B-6 (`docs/experiments/optimize_core_2026_05_20.md`).

実行例:
    py -3.11 scripts/demo_synaptic_sliding_window.py --maxlen 100 --pushes 5000
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from llive.perf.synaptic_selector import (  # noqa: E402
    StrategyVariant,
    UCBSynapticSelector,
)
from llive.perf.variants.sliding_window_variants import ALL_VARIANTS  # noqa: E402


def run_demo(maxlen: int, pushes: int, iters: int, seed: int = 2026) -> dict:
    variants = [StrategyVariant(name=name, impl=fn) for name, fn in ALL_VARIANTS]
    selector = UCBSynapticSelector(variants=variants, rng=random.Random(seed))

    rng = random.Random(seed)
    initial = [rng.randint(0, 1000) for _ in range(maxlen)]

    for _ in range(iters):
        new_items = [rng.randint(0, 1000) for _ in range(pushes)]
        v = selector.choose()
        t0 = time.perf_counter()
        _ = v.impl(initial, new_items, maxlen)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        selector.record_result(v, elapsed_ms)

    return {
        "maxlen": maxlen,
        "pushes": pushes,
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
    p.add_argument("--maxlen", type=int, default=100, help="window 最大長 N")
    p.add_argument("--pushes", type=int, default=5000, help="1 iter あたり push 数")
    p.add_argument("--iters", type=int, default=200, help="反復回数")
    p.add_argument("--seed", type=int, default=2026, help="乱数シード")
    args = p.parse_args()

    print(f"[demo-ucb] maxlen={args.maxlen} pushes={args.pushes} iters={args.iters}")
    t0 = time.perf_counter()
    result = run_demo(args.maxlen, args.pushes, args.iters, args.seed)
    elapsed = time.perf_counter() - t0
    print(f"[demo-ucb] elapsed: {elapsed:.2f}s")
    print(f"[demo-ucb] converged_to: {result['converged_to']}")
    print()
    print(_fmt_table(result["snapshot"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
