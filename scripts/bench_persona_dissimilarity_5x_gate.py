# SPDX-License-Identifier: Apache-2.0
"""RUST-15 persona_dissimilarity 5× gate measurement.

Python fallback (``_persona_dissimilarity_py``) vs Rust kernel
(``llive.rust_ext.persona_dissimilarity``) を同じ入力でループし wall-clock
比を取る. ratio >= 5x なら gate clear.

Usage:
    .venv/Scripts/python.exe scripts/bench_persona_dissimilarity_5x_gate.py
"""

from __future__ import annotations

import time

import random

from llive.rust_ext import (
    HAS_RUST,
    _persona_dissimilarity_pairwise_py,
    _persona_id_to_u32,
    persona_dissimilarity_pairwise,
)


def _bench(name: str, fn, n_iter: int) -> float:
    # warmup
    for _ in range(3):
        fn()
    start = time.perf_counter()
    for _ in range(n_iter):
        fn()
    elapsed = time.perf_counter() - start
    per_iter_us = elapsed / n_iter * 1e6
    print(f"{name:60s} {per_iter_us:12.2f} us/iter")
    return per_iter_us


def _make_corpus(n: int, rng: random.Random) -> tuple[list[list[str]], list[list[float]]]:
    pool = [
        "oka-kiyoshi",
        "grothendieck",
        "feynman",
        "galois",
        "von-neumann",
        "newton",
        "kant",
        "socrates",
        "laozi",
        "sun-tzu",
    ]
    ids_list: list[list[str]] = []
    aff_matrix: list[list[float]] = []
    for _ in range(n):
        k = rng.randint(1, 3)
        ids_list.append(rng.sample(pool, k))
        aff_matrix.append([rng.random() for _ in range(10)])
    return ids_list, aff_matrix


def main() -> int:
    print("=== RUST-15 persona_dissimilarity_pairwise 5x gate ===\n")
    print(f"HAS_RUST = {HAS_RUST}\n")
    rng = random.Random(42)

    sizes = [16, 32, 64]
    speedups: list[float] = []
    print(f"{'method':60s} {'us/iter':>12s}")
    print("-" * 75)
    for n in sizes:
        ids_list, aff_matrix = _make_corpus(n, rng)
        # warmup convert (sort/dedup) は wrapper 内で毎回走る — fair な比較.
        active_us = _bench(
            f"[N={n:3d}] active (rust if HAS_RUST)",
            lambda i=ids_list, a=aff_matrix: persona_dissimilarity_pairwise(i, a),
            n_iter=200,
        )
        # Python fallback baseline: 同 wrapper の py 経路 (sort/dedup を含む).
        sorted_ids = [
            sorted({_persona_id_to_u32(s) for s in ids}) for ids in ids_list
        ]
        aff_list = [[float(x) for x in row] for row in aff_matrix]
        py_us = _bench(
            f"[N={n:3d}] python fallback",
            lambda si=sorted_ids, ai=aff_list: _persona_dissimilarity_pairwise_py(si, ai),
            n_iter=200,
        )
        if HAS_RUST:
            speedup = py_us / active_us if active_us > 0 else float("inf")
            gate = "PASS" if speedup >= 5.0 else "FAIL"
            print(f"  speedup x{speedup:.2f} [{gate}]\n")
            speedups.append(speedup)
        else:
            print()

    if HAS_RUST and speedups:
        avg = sum(speedups) / len(speedups)
        print("-" * 75)
        print(f"Average speedup across {sizes}: x{avg:.2f}")
        if avg >= 5.0:
            print("Result: 5x gate PASSED")
            return 0
        print("Result: 5x gate FAILED")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
