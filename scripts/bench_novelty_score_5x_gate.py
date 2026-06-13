# SPDX-License-Identifier: Apache-2.0
"""RUST-17 novelty_score_batch 5× gate (Python numpy vs Rust pyo3).

Hot path: NoveltyScorer.novelty_batch(pop). 集団 N (≈ 64) × archive A
(≈ 1000) × D (≈ 19) で L2 + top-k sort.

Usage:
    .venv/Scripts/python.exe scripts/bench_novelty_score_5x_gate.py
"""

from __future__ import annotations

import time

import numpy as np

from llive.rust_ext import (
    HAS_RUST,
    _novelty_score_batch_py,
    novelty_score_batch,
)


def _bench(name: str, fn, n_iter: int) -> float:
    for _ in range(3):
        fn()
    start = time.perf_counter()
    for _ in range(n_iter):
        fn()
    elapsed = time.perf_counter() - start
    per_iter_us = elapsed / n_iter * 1e6
    print(f"{name:60s} {per_iter_us:12.2f} us/iter")
    return per_iter_us


def main() -> int:
    print("=== RUST-17 novelty_score_batch 5x gate (Python numpy vs Rust pyo3) ===\n")
    print(f"HAS_RUST = {HAS_RUST}\n")
    rng = np.random.default_rng(42)

    # 派生集団進化 typical scale: D=19 (Genome dim), N=64 (集団), A varies.
    D = 19
    N = 64
    archive_sizes = [50, 200, 1000]
    speedups: list[float] = []
    print(f"{'method':60s} {'us/iter':>12s}")
    print("-" * 75)
    for A in archive_sizes:
        values = rng.uniform(0.0, 1.0, size=(N, D))
        archive = rng.uniform(0.0, 1.0, size=(A, D))
        py_us = _bench(
            f"[A={A:4d}] python (numpy fallback)",
            lambda v=values, a=archive: _novelty_score_batch_py(v, a, 5),
            n_iter=50,
        )
        rust_us = _bench(
            f"[A={A:4d}] rust pyo3 (zero-copy)",
            lambda v=values, a=archive: novelty_score_batch(v, a, 5),
            n_iter=50,
        )
        if HAS_RUST:
            speedup = py_us / rust_us if rust_us > 0 else float("inf")
            gate = "PASS" if speedup >= 5.0 else "FAIL"
            print(f"  speedup x{speedup:.2f} [{gate}]\n")
            speedups.append(speedup)
        else:
            print()

    if HAS_RUST and speedups:
        avg = sum(speedups) / len(speedups)
        print("-" * 75)
        print(f"Average speedup across A={archive_sizes}: x{avg:.2f}")
        if avg >= 5.0:
            print("Result: 5x gate PASSED")
            return 0
        print("Result: 5x gate FAILED")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
