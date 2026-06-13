# SPDX-License-Identifier: Apache-2.0
"""RUST-15 5× gate measurement (PeerScoreMatrixOps, Python vs Rust)."""

from __future__ import annotations

import time

import numpy as np


def bench(name: str, fn, n_iter: int = 1000) -> float:
    for _ in range(10):
        fn()
    start = time.perf_counter()
    for _ in range(n_iter):
        fn()
    elapsed = time.perf_counter() - start
    per_iter_us = elapsed / n_iter * 1e6
    print(f"{name:50s} {per_iter_us:10.2f} us/iter")
    return per_iter_us


def main() -> int:
    print("=== RUST-15 PeerScoreMatrixOps 5x gate ===\n")
    try:
        import llive_peer_rust_ext as rs
    except ImportError:
        print("ERROR: llive_rust_ext is not installed.")
        return 1

    from llive.perf.evolutionary import PeerEvaluationMatrix

    sizes = [10, 30, 100]
    print(f"{'method':50s} {'us/iter':>10s}")
    print("-" * 62)
    all_results = {}
    for n in sizes:
        rng = np.random.default_rng(42)
        m_arr = rng.uniform(0.0, 1.0, size=(n, n))
        np.fill_diagonal(m_arr, np.nan)
        m = PeerEvaluationMatrix(
            agent_ids=tuple(f"a{i}" for i in range(n)),
            matrix=m_arr,
        )
        py_us = bench(f"[N={n:3d}] Python column_mean", m.column_mean)
        rs_us = bench(
            f"[N={n:3d}] Rust   column_mean",
            lambda mat=m_arr: rs.py_column_mean(mat, True),
        )
        speedup = py_us / rs_us if rs_us > 0 else float("inf")
        gate = "PASS" if speedup >= 5.0 else "FAIL"
        print(f"   speedup x{speedup:.2f} [{gate}]")
        print()
        all_results[n] = (py_us, rs_us)

    avg_speedup = sum(py / rs for py, rs in all_results.values()) / len(all_results)
    print("-" * 62)
    print(f"Average speedup across sizes {sizes}: {avg_speedup:.2f}x")
    if avg_speedup >= 5.0:
        print("Result: 5x gate PASSED")
        return 0
    print("Result: 5x gate FAILED")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
