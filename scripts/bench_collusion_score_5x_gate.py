# SPDX-License-Identifier: Apache-2.0
"""RUST-16 collusion_score 5× gate measurement (Python numpy vs Rust pyo3).

Cython 経路は本来 3 way 比較の予定だったが, Windows + MSVC build tools 不在
+ mingw が MSVC Python と incompatible で build 不可能. honest disclosure
として「Cython は scratch 比較から脱落」を記録 ([[feedback_rust_usage_matters]]).

Usage:
    .venv/Scripts/python.exe scripts/bench_collusion_score_5x_gate.py
"""

from __future__ import annotations

import time

import numpy as np

from llive.perf.evolutionary import PeerEvaluationMatrix
from llive.rust_ext import (
    HAS_RUST,
    _collusion_score_kernel_py,
    collusion_score_kernel,
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


def _make_matrix(n: int, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    m = rng.uniform(0.0, 1.0, size=(n, n))
    np.fill_diagonal(m, np.nan)
    return m


def main() -> int:
    print("=== RUST-16 collusion_score 5x gate (Python numpy vs Rust pyo3) ===\n")
    print(f"HAS_RUST = {HAS_RUST}\n")

    sizes = [8, 16, 32, 64]
    speedups_rust_vs_py: list[float] = []
    speedups_rust_vs_peer: list[float] = []
    print(f"{'method':60s} {'us/iter':>12s}")
    print("-" * 75)
    for n in sizes:
        m = _make_matrix(n)
        # bind matrix into ids for PeerEvaluationMatrix path
        agent_ids = tuple(f"a{i}" for i in range(n))
        # PeerEvaluationMatrix expects raw matrix; pass copy as it mutates internally
        # via collusion_score (np.fill_diagonal copy inside).
        peer = PeerEvaluationMatrix(agent_ids=agent_ids, matrix=m.copy())

        peer_us = _bench(
            f"[N={n:3d}] PeerEvaluationMatrix.collusion_score (existing numpy)",
            peer.collusion_score,
            n_iter=200,
        )
        py_us = _bench(
            f"[N={n:3d}] _collusion_score_kernel_py (numpy fallback)",
            lambda mm=m: _collusion_score_kernel_py(mm),
            n_iter=200,
        )
        rust_us = _bench(
            f"[N={n:3d}] collusion_score_kernel (rust pyo3 zero-copy)",
            lambda mm=m: collusion_score_kernel(mm),
            n_iter=200,
        )
        if HAS_RUST:
            speedup_vs_py = py_us / rust_us if rust_us > 0 else float("inf")
            speedup_vs_peer = peer_us / rust_us if rust_us > 0 else float("inf")
            gate_py = "PASS" if speedup_vs_py >= 5.0 else "FAIL"
            gate_peer = "PASS" if speedup_vs_peer >= 5.0 else "FAIL"
            print(
                f"  speedup vs numpy-fallback: x{speedup_vs_py:.2f} [{gate_py}]"
            )
            print(
                f"  speedup vs PeerEvaluationMatrix (existing): "
                f"x{speedup_vs_peer:.2f} [{gate_peer}]\n"
            )
            speedups_rust_vs_py.append(speedup_vs_py)
            speedups_rust_vs_peer.append(speedup_vs_peer)
        else:
            print()

    if HAS_RUST and speedups_rust_vs_peer:
        avg_py = sum(speedups_rust_vs_py) / len(speedups_rust_vs_py)
        avg_peer = sum(speedups_rust_vs_peer) / len(speedups_rust_vs_peer)
        print("-" * 75)
        print(f"Average speedup vs numpy fallback:   x{avg_py:.2f}")
        print(f"Average speedup vs PeerEvaluationMatrix: x{avg_peer:.2f}")
        if avg_peer >= 5.0:
            print("Result: 5x gate PASSED (vs existing PeerEvaluationMatrix path)")
            return 0
        print("Result: 5x gate FAILED")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
