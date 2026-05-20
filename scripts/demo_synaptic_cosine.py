#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Demo: cosine 類似度を SynapticSelector で「次元別の最良 variant」に自動収束させる.

候補 (`src/llive/perf/variants/cosine_variants.py`):
    1. pure_python       — math + zip + sum
    2. numpy_dot         — np.dot + np.linalg.norm (既存 production と同等)
    3. numpy_einsum      — np.einsum("i,i->", ...) で内積
    4. numpy_normalized  — 事前 L2 normalize 済 input 前提の高速版

ベクトル次元による最良候補が変動するはず:

    小次元 (~16)   → numpy overhead が支配的, pure_python が勝つことあり
    中次元 (~128)  → numpy_dot / einsum が拮抗
    大次元 (~768)  → numpy_dot or einsum が勝つ

実行例:
    py -3.11 scripts/demo_synaptic_cosine.py --dim 16   --iters 500
    py -3.11 scripts/demo_synaptic_cosine.py --dim 768  --iters 500

このデモは llive コア最適化セッション (2026-05-20) の Phase B-2 として
`docs/experiments/optimize_core_2026_05_20.md` に結果を残す.
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
from llive.perf.variants.cosine_variants import ALL_VARIANTS  # noqa: E402


def _gen_pair(dim: int, rng: np.random.Generator):
    a = rng.normal(size=dim).astype(np.float64)
    b = rng.normal(size=dim).astype(np.float64)
    # numpy_normalized 用に L2 normalize したペアも用意
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na > 0:
        a_n = a / na
    else:
        a_n = a
    if nb > 0:
        b_n = b / nb
    else:
        b_n = b
    return a, b, a_n, b_n


def run_demo(dim: int, iters: int, seed: int = 2026) -> dict:
    # SynapticSelector に load.
    variants = [StrategyVariant(name=name, impl=fn) for name, fn in ALL_VARIANTS]
    selector = SynapticSelector(
        variants=variants,
        learning_rate=0.10,
        exploration_rate=0.15,
        rng=random.Random(seed),
    )

    rng = np.random.default_rng(seed)
    for _ in range(iters):
        a, b, a_n, b_n = _gen_pair(dim, rng)
        # SynapticSelector.choose() → impl を直接呼ぶ (call() は kwargs 固定).
        # variant 名で normalized 用か通常用かを分岐.
        v = selector.choose()
        t0 = time.perf_counter()
        if v.name == "numpy_normalized":
            v.impl(a_n, b_n)
        else:
            v.impl(a, b)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        selector.record_result(v, elapsed_ms)

    return {
        "dim": dim,
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
    p.add_argument("--dim", type=int, default=128, help="ベクトル次元")
    p.add_argument("--iters", type=int, default=500, help="反復回数")
    p.add_argument("--seed", type=int, default=2026, help="乱数シード")
    args = p.parse_args()

    print(f"[demo] dim={args.dim} iters={args.iters} seed={args.seed}")
    t0 = time.perf_counter()
    result = run_demo(args.dim, args.iters, args.seed)
    elapsed = time.perf_counter() - t0
    print(f"[demo] elapsed: {elapsed:.2f}s")
    print(f"[demo] converged_to: {result['converged_to']}")
    print()
    print(_fmt_table(result["snapshot"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
