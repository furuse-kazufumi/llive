#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""VRB-02/04/05/06 ベンチ — PromptLint / Premortem / EvalSpec / Render."""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from llive.brief import (
    Brief,
    DualSpecWriter,
    EvalEvaluator,
    EvalSpec,
    Metric,
    PremortemGenerator,
    PromptLinter,
    RenderMode,
    StopCondition,
)


N = 1000


def _b(i: int) -> Brief:
    return Brief(
        brief_id=f"vrb-{i}",
        goal=f"高性能なシステム #{i} を実装し、より良い結果を得る",
        constraints=("p99 < 100ms", "メモリを考慮"),
        success_criteria=("zero data loss",),
    )


def main() -> None:
    out_dir = Path("docs/benchmarks/2026-05-17-full-validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "vrb.json"

    # 1. PromptLint
    linter = PromptLinter()
    times_lint = []
    t0 = time.perf_counter()
    for i in range(N):
        ts = time.perf_counter()
        linter.lint(_b(i))
        times_lint.append(time.perf_counter() - ts)
    total_lint = time.perf_counter() - t0

    # 2. Premortem
    gen = PremortemGenerator()
    times_pm = []
    t0 = time.perf_counter()
    for i in range(N):
        ts = time.perf_counter()
        gen.generate(_b(i))
        times_pm.append(time.perf_counter() - ts)
    total_pm = time.perf_counter() - t0

    # 3. EvalSpec evaluate
    spec = EvalSpec(
        brief_id="x",
        metrics=(
            Metric(name="acc", threshold=0.9),
            Metric(name="latency", threshold=100, lower_is_better=True),
        ),
        stop_conditions=(
            StopCondition(condition_id="cost", metric_name="cost", operator=">", value=10),
        ),
    )
    evaluator = EvalEvaluator()
    times_ev = []
    t0 = time.perf_counter()
    for i in range(N):
        ts = time.perf_counter()
        evaluator.evaluate(spec, {"acc": 0.95, "latency": 50, "cost": i % 20})
        times_ev.append(time.perf_counter() - ts)
    total_ev = time.perf_counter() - t0

    # 4. DualSpecWriter render_all (5 modes per call)
    writer = DualSpecWriter()
    times_render = []
    t0 = time.perf_counter()
    for i in range(N // 5):
        ts = time.perf_counter()
        writer.render_all(_b(i), eval_spec=spec)
        times_render.append(time.perf_counter() - ts)
    total_render = time.perf_counter() - t0

    def _summary(xs, n):
        s = sorted(xs)
        return {
            "n": n,
            "mean_us": round(statistics.mean(xs) * 1e6, 2),
            "median_us": round(statistics.median(xs) * 1e6, 2),
            "p95_us": round(s[int(len(s) * 0.95)] * 1e6, 2),
            "p99_us": round(s[int(len(s) * 0.99)] * 1e6, 2),
            "max_us": round(max(xs) * 1e6, 2),
        }

    report = {
        "prompt_lint": {
            "wall_total_s": round(total_lint, 4),
            "throughput_per_s": round(N / total_lint, 1),
            **_summary(times_lint, N),
        },
        "premortem": {
            "wall_total_s": round(total_pm, 4),
            "throughput_per_s": round(N / total_pm, 1),
            **_summary(times_pm, N),
        },
        "eval_spec_evaluate": {
            "wall_total_s": round(total_ev, 4),
            "throughput_per_s": round(N / total_ev, 1),
            **_summary(times_ev, N),
        },
        "dual_spec_writer_render_all_5modes": {
            "wall_total_s": round(total_render, 4),
            "throughput_per_s": round((N // 5) / total_render, 1),
            **_summary(times_render, N // 5),
        },
    }
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out_path}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
