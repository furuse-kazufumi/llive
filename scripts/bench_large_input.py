#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Large-input stress — extreme Brief sizes (1 KB goal, 100 constraints, etc.)."""

from __future__ import annotations

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
)
from llive.fullsense.loop import FullSenseResult
from llive.fullsense.types import ActionDecision, ActionPlan, Thought, Stimulus
from llive.oka import CoreEssenceExtractor


class _AutoApprove:
    def evaluate(self, request: ApprovalRequest):
        return Verdict.APPROVED


class _MockLoop:
    def process(self, stim: Stimulus) -> FullSenseResult:
        return FullSenseResult(
            stim=stim,
            plan=ActionPlan(
                decision=ActionDecision.PROPOSE,
                rationale="large input rationale " * 20,
                thought=Thought(text="t", confidence=0.85, triz_principles=[1]),
            ),
            stages={"tools": [{"name": "echo", "args": {"x": 1}}]},
        )


def _make_brief(brief_id: str, goal_chars: int, n_constraints: int, n_criteria: int, ledger_path: Path) -> Brief:
    goal = "対称性と保存量と単位次元解析と矛盾解消と類比展開の話題で複合的に設計を進める " * (goal_chars // 40 + 1)
    constraints = tuple(f"制約 #{i}: p99 < {(i+1)*10}ms / 必須" for i in range(n_constraints))
    criteria = tuple(f"基準 #{i}: zero data loss for class {i}" for i in range(n_criteria))
    return Brief(
        brief_id=brief_id,
        goal=goal[:goal_chars],
        constraints=constraints,
        tools=("echo",),
        success_criteria=criteria,
        approval_required=True,
        ledger_path=ledger_path,
    )


def main() -> None:
    out_dir = Path("docs/benchmarks/2026-05-17-full-validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "large_input.json"
    tmpdir = Path(tempfile.mkdtemp(prefix="llive-large-"))

    runner = BriefRunner(
        loop=_MockLoop(),  # type: ignore[arg-type]
        approval_bus=ApprovalBus(policy=_AutoApprove()),
        tools={"echo": lambda a: {"ok": True}},
        governance_scorer=GovernanceScorer(),
        perspectives=RoleBasedMultiTrack(),
        essence_extractor=CoreEssenceExtractor(),
        prompt_linter=PromptLinter(),
    )

    profiles = [
        ("baseline", 50, 2, 1),
        ("medium", 500, 10, 5),
        ("large", 2000, 50, 20),
        ("xlarge", 5000, 100, 50),
        ("huge", 20000, 200, 100),
    ]
    results = []
    for name, goal_chars, nc, ncrit in profiles:
        brief = _make_brief(
            f"large-{name}", goal_chars, nc, ncrit,
            tmpdir / f"{name}.jsonl",
        )
        durations = []
        for trial in range(5):
            t0 = time.perf_counter()
            r = runner.submit(brief)
            durations.append(time.perf_counter() - t0)
            assert r.status is BriefStatus.COMPLETED
        ledger_size = (tmpdir / f"{name}.jsonl").stat().st_size
        results.append({
            "profile": name,
            "goal_chars": len(brief.goal),
            "n_constraints": len(brief.constraints),
            "n_criteria": len(brief.success_criteria),
            "wall_per_brief_s": {
                "mean": round(statistics.mean(durations), 5),
                "max": round(max(durations), 5),
            },
            "ledger_size_after_5_runs_bytes": ledger_size,
            "ledger_size_per_run_kb": round(ledger_size / 5 / 1024, 2),
        })

    report = {"profiles": results}
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out_path}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
