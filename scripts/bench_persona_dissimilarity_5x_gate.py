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

from llive.rust_ext import (
    HAS_RUST,
    _persona_dissimilarity_py,
    _persona_id_to_u32,
    persona_dissimilarity,
)


def _bench(name: str, fn, n_iter: int = 10000) -> float:
    # warmup
    for _ in range(50):
        fn()
    start = time.perf_counter()
    for _ in range(n_iter):
        fn()
    elapsed = time.perf_counter() - start
    per_iter_us = elapsed / n_iter * 1e6
    print(f"{name:50s} {per_iter_us:10.3f} us/iter")
    return per_iter_us


def main() -> int:
    print("=== RUST-15 persona_dissimilarity 5x gate ===\n")
    print(f"HAS_RUST = {HAS_RUST}\n")

    a_ids = ["newton", "feynman"]
    b_ids = ["kant", "galois"]
    a_aff = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    b_aff = [0.5] * 10

    a_u32 = sorted({_persona_id_to_u32(s) for s in a_ids})
    b_u32 = sorted({_persona_id_to_u32(s) for s in b_ids})

    # 1. Active (Rust if available, else Python fallback inside wrapper)
    active_us = _bench(
        "active (rust if HAS_RUST else py)",
        lambda: persona_dissimilarity(a_ids, b_ids, a_aff, b_aff),
    )

    # 2. Pure Python fallback (direct call, no FFI)
    py_us = _bench(
        "py fallback (direct, no FFI)",
        lambda: _persona_dissimilarity_py(a_u32, b_u32, a_aff, b_aff),
    )

    print()
    if HAS_RUST:
        speedup = py_us / active_us if active_us > 0 else float("inf")
        gate = "PASS" if speedup >= 5.0 else "FAIL"
        print(f"speedup (py/rust): x{speedup:.2f}  [5x gate {gate}]")
        # FFI overhead を含むので, sort/dedup を含む wrapper 全体での比較.
        # 大規模 batch では wrapper 化して Rust 側で sort/dedup する別 kernel
        # が必要 (RUST-NEW-B persona_dissimilarity_batch).
        return 0 if speedup >= 5.0 else 2
    print("HAS_RUST=False — gate check skipped (Rust ext absent)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
