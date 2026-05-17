#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""MATH-02 MathVerifier ベンチ — equivalence / implication / satisfiable scale."""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from llive.math import MathVerifier


N = 200  # each kind; z3 calls are heavier so keep modest


def main() -> None:
    out_dir = Path("docs/benchmarks/2026-05-17-full-validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "math_verifier.json"
    v = MathVerifier()

    # equivalence — sympy simplify
    eqv = []
    t0 = time.perf_counter()
    for i in range(N):
        r = v.check_equivalence(f"(x + {i})**2", f"x**2 + 2*{i}*x + {i}**2")
        eqv.append(r.elapsed_s)
    total_eqv = time.perf_counter() - t0
    assert all(r > 0 for r in eqv)

    # implication — z3
    impl = []
    t0 = time.perf_counter()
    for i in range(N):
        r = v.check_implication([f"x > {i}"], f"x > {i - 1}")
        impl.append(r.elapsed_s)
    total_impl = time.perf_counter() - t0

    # satisfiable — z3
    sat = []
    t0 = time.perf_counter()
    for i in range(N):
        r = v.check_satisfiable([f"x > {i}", f"x < {i + 10}"])
        sat.append(r.elapsed_s)
    total_sat = time.perf_counter() - t0

    def _summary(xs):
        s = sorted(xs)
        return {
            "mean_ms": round(statistics.mean(xs) * 1000, 4),
            "median_ms": round(statistics.median(xs) * 1000, 4),
            "p95_ms": round(s[int(len(s) * 0.95)] * 1000, 4),
            "p99_ms": round(s[int(len(s) * 0.99)] * 1000, 4),
            "max_ms": round(max(xs) * 1000, 4),
        }

    report = {
        "n_per_kind": N,
        "equivalence": {
            "wall_total_s": round(total_eqv, 4),
            "throughput_per_s": round(N / total_eqv, 2),
            **_summary(eqv),
        },
        "implication": {
            "wall_total_s": round(total_impl, 4),
            "throughput_per_s": round(N / total_impl, 2),
            **_summary(impl),
        },
        "satisfiable": {
            "wall_total_s": round(total_sat, 4),
            "throughput_per_s": round(N / total_sat, 2),
            **_summary(sat),
        },
    }
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out_path}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
