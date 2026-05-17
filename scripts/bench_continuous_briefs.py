#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Continuous-Brief stress test — 100 Briefs back-to-back, 9 factors all-on.

Measures:
- wall time per Brief (mean / median / p95 / p99)
- ledger file size growth (per Brief)
- in-process memory growth (RSS via psutil if available, else gc proxy)
- success / failure count
- annotations emit count per Brief

Output: docs/benchmarks/2026-05-17-full-validation/continuous_briefs.json
"""

from __future__ import annotations

import gc
import json
import os
import statistics
import tempfile
import time
from pathlib import Path

os.environ.setdefault("LLIVE_DISABLE_RAD_GROUNDING", "1")

from llive.approval.bus import ApprovalBus, ApprovalRequest, Verdict
from llive.brief import (
    Brief, BriefLedger, BriefRunner, BriefStatus,
    GovernanceScorer, RoleBasedMultiTrack, PromptLinter,
    BriefGrounder, GroundingConfig,
)
from llive.fullsense.loop import FullSenseResult
from llive.fullsense.types import ActionDecision, ActionPlan, Thought, Stimulus
from llive.math import MathVerifier
from llive.oka import CoreEssenceExtractor, ReflectiveNotebook, StrategyFamily, StrategyOrchestrator

N_BRIEFS = 100
GOAL_TEMPLATE = "trade-off between static and dynamic structures for run #{i}"


class _AutoApprove:
    def evaluate(self, request: ApprovalRequest):
        return Verdict.APPROVED


class _MockLoop:
    def process(self, stim: Stimulus) -> FullSenseResult:
        return FullSenseResult(
            stim=stim,
            plan=ActionPlan(
                decision=ActionDecision.PROPOSE,
                rationale="bench decision rationale text",
                thought=Thought(text="t", confidence=0.85, triz_principles=[1, 15]),
            ),
            stages={"tools": [{"name": "echo", "args": {"x": 1}}]},
        )


class _Principle:
    def __init__(self, pid, name):
        self.id, self.name = pid, name
        self.description = ""
        self.examples = []


def _rss_mb() -> float:
    try:
        import psutil
        return psutil.Process(os.getpid()).memory_info().rss / 1e6
    except Exception:
        return float("nan")


def main() -> None:
    out_dir = Path("docs/benchmarks/2026-05-17-full-validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "continuous_briefs.json"

    tmpdir = Path(tempfile.mkdtemp(prefix="llive-bench-"))
    durations: list[float] = []
    ledger_sizes: list[int] = []
    annotation_counts: list[int] = []
    rss_samples: list[float] = []
    statuses: dict[str, int] = {}

    grounder = BriefGrounder(
        principles={1: _Principle(1, "Segmentation"), 15: _Principle(15, "Dynamics")},
        config=GroundingConfig(max_triz=2),
    )
    governance = GovernanceScorer()
    perspectives = RoleBasedMultiTrack()
    extractor = CoreEssenceExtractor()
    notebook = ReflectiveNotebook(tmpdir / "_notebook.jsonl")
    orch = StrategyOrchestrator()
    orch.register(StrategyFamily(name="symbolic"))
    orch.activate("symbolic")
    linter = PromptLinter()
    verifier = MathVerifier()
    bus = ApprovalBus(policy=_AutoApprove())

    runner = BriefRunner(
        loop=_MockLoop(),  # type: ignore[arg-type]
        approval_bus=bus,
        tools={"echo": lambda a: {"ok": True, "args": a, "artifact": "bench"}},
        grounder=grounder,
        governance_scorer=governance,
        perspectives=perspectives,
        math_verifier=verifier,
        essence_extractor=extractor,
        notebook=notebook,
        strategy_orchestrator=orch,
        prompt_linter=linter,
    )

    rss_baseline = _rss_mb()
    t_total_start = time.perf_counter()

    for i in range(N_BRIEFS):
        ledger_path = tmpdir / f"b-{i:03d}.jsonl"
        brief = Brief(
            brief_id=f"stress-{i:03d}",
            goal=GOAL_TEMPLATE.format(i=i),
            constraints=("preserve at-least-once semantics", "p99 < 100ms"),
            tools=("echo",),
            success_criteria=("zero data loss",),
            approval_required=True,
            ledger_path=ledger_path,
        )
        t0 = time.perf_counter()
        result = runner.submit(brief)
        durations.append(time.perf_counter() - t0)
        ledger_sizes.append(ledger_path.stat().st_size)
        annotation_counts.append(len(result.annotations))
        statuses[result.status.value] = statuses.get(result.status.value, 0) + 1
        if i % 20 == 0:
            gc.collect()
            rss_samples.append(_rss_mb())

    total_wall = time.perf_counter() - t_total_start
    rss_after = _rss_mb()

    def _p(xs, q):
        s = sorted(xs)
        return s[int(len(s) * q)] if s else 0.0

    report = {
        "n_briefs": N_BRIEFS,
        "total_wall_s": round(total_wall, 4),
        "throughput_briefs_per_s": round(N_BRIEFS / total_wall, 3) if total_wall > 0 else None,
        "per_brief_s": {
            "mean": round(statistics.mean(durations), 6),
            "median": round(statistics.median(durations), 6),
            "p95": round(_p(durations, 0.95), 6),
            "p99": round(_p(durations, 0.99), 6),
            "min": round(min(durations), 6),
            "max": round(max(durations), 6),
        },
        "ledger_size_bytes": {
            "first": ledger_sizes[0],
            "last": ledger_sizes[-1],
            "mean": int(statistics.mean(ledger_sizes)),
            "growth_factor_last_over_first": round(
                ledger_sizes[-1] / ledger_sizes[0] if ledger_sizes[0] else 0, 3
            ),
        },
        "annotations_per_brief": {
            "mean": round(statistics.mean(annotation_counts), 3),
            "min": min(annotation_counts),
            "max": max(annotation_counts),
        },
        "memory_rss_mb": {
            "baseline": round(rss_baseline, 1) if rss_baseline == rss_baseline else None,
            "after": round(rss_after, 1) if rss_after == rss_after else None,
            "samples": [round(x, 1) for x in rss_samples if x == x],
        },
        "status_counts": statuses,
        "all_completed": statuses.get(BriefStatus.COMPLETED.value, 0) == N_BRIEFS,
    }

    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out_path}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
