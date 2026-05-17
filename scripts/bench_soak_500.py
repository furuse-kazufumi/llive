#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""500-Brief soak test with tracemalloc memory tracking."""

from __future__ import annotations

import gc
import json
import os
import statistics
import tempfile
import time
import tracemalloc
from pathlib import Path

os.environ.setdefault("LLIVE_DISABLE_RAD_GROUNDING", "1")

from llive.approval.bus import ApprovalBus, ApprovalRequest, Verdict
from llive.brief import (
    Brief, BriefRunner,
    GovernanceScorer, RoleBasedMultiTrack, PromptLinter,
    BriefGrounder, GroundingConfig,
)
from llive.fullsense.loop import FullSenseResult
from llive.fullsense.types import ActionDecision, ActionPlan, Thought, Stimulus
from llive.math import MathVerifier
from llive.oka import CoreEssenceExtractor, ReflectiveNotebook, StrategyFamily, StrategyOrchestrator

N = 500
SAMPLE_EVERY = 50


class _AutoApprove:
    def evaluate(self, request: ApprovalRequest):
        return Verdict.APPROVED


class _MockLoop:
    def process(self, stim: Stimulus) -> FullSenseResult:
        return FullSenseResult(
            stim=stim,
            plan=ActionPlan(
                decision=ActionDecision.PROPOSE,
                rationale="soak decision rationale",
                thought=Thought(text="t", confidence=0.85, triz_principles=[1]),
            ),
            stages={"tools": [{"name": "echo", "args": {"x": 1}}]},
        )


class _Principle:
    def __init__(self, pid, name):
        self.id, self.name = pid, name
        self.description = ""
        self.examples = []


def main() -> None:
    out_dir = Path("docs/benchmarks/2026-05-17-full-validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "soak_500.json"

    tmpdir = Path(tempfile.mkdtemp(prefix="llive-soak-"))

    tracemalloc.start()
    baseline_size, baseline_peak = tracemalloc.get_traced_memory()

    grounder = BriefGrounder(principles={1: _Principle(1, "Segmentation")}, config=GroundingConfig(max_triz=1))
    notebook = ReflectiveNotebook(tmpdir / "_nb.jsonl")
    orch = StrategyOrchestrator()
    orch.register(StrategyFamily(name="symbolic"))
    orch.activate("symbolic")

    runner = BriefRunner(
        loop=_MockLoop(),  # type: ignore[arg-type]
        approval_bus=ApprovalBus(policy=_AutoApprove()),
        tools={"echo": lambda a: {"ok": True}},
        grounder=grounder,
        governance_scorer=GovernanceScorer(),
        perspectives=RoleBasedMultiTrack(),
        math_verifier=MathVerifier(),
        essence_extractor=CoreEssenceExtractor(),
        notebook=notebook,
        strategy_orchestrator=orch,
        prompt_linter=PromptLinter(),
    )

    durations: list[float] = []
    rss_samples: list[dict] = []
    completed = 0

    t_start = time.perf_counter()
    for i in range(N):
        brief = Brief(
            brief_id=f"soak-{i:04d}",
            goal=f"soak goal #{i} segmentation",
            constraints=("p99 < 100ms",),
            tools=("echo",),
            success_criteria=("zero loss",),
            approval_required=True,
            ledger_path=tmpdir / f"b-{i:04d}.jsonl",
        )
        t0 = time.perf_counter()
        r = runner.submit(brief)
        durations.append(time.perf_counter() - t0)
        if r.status.value == "completed":
            completed += 1
        if i % SAMPLE_EVERY == 0:
            gc.collect()
            cur, peak = tracemalloc.get_traced_memory()
            rss_samples.append({
                "after_brief": i,
                "traced_kb": round(cur / 1024, 1),
                "peak_kb": round(peak / 1024, 1),
            })
    total_wall = time.perf_counter() - t_start
    end_size, end_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    def _p(xs, q):
        s = sorted(xs)
        return s[int(len(s) * q)] if s else 0.0

    leak_kb = (end_size - baseline_size) / 1024
    leak_per_brief_b = (end_size - baseline_size) / N

    report = {
        "n_briefs": N,
        "completed": completed,
        "all_completed": completed == N,
        "total_wall_s": round(total_wall, 3),
        "throughput_per_s": round(N / total_wall, 2),
        "per_brief_s": {
            "mean": round(statistics.mean(durations), 6),
            "median": round(statistics.median(durations), 6),
            "p95": round(_p(durations, 0.95), 6),
            "p99": round(_p(durations, 0.99), 6),
            "max": round(max(durations), 6),
        },
        "tracemalloc": {
            "baseline_kb": round(baseline_size / 1024, 1),
            "end_kb": round(end_size / 1024, 1),
            "end_peak_kb": round(end_peak / 1024, 1),
            "delta_kb": round(leak_kb, 1),
            "leak_per_brief_bytes": round(leak_per_brief_b, 2),
            "samples": rss_samples,
        },
        # Long-term trend: median(last 100) vs median(first 100)
        "perf_drift": {
            "first_100_median_s": round(statistics.median(durations[:100]), 6),
            "last_100_median_s": round(statistics.median(durations[-100:]), 6),
            "drift_factor": round(
                statistics.median(durations[-100:]) / statistics.median(durations[:100]), 3
            ),
        },
    }
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out_path}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
