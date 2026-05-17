#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OKA + CREAT pipeline ベンチ — essence → KJ → mindmap → structurize 連続実行."""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from llive.brief import Brief, RoleBasedMultiTrack
from llive.creat import KJExtractor, MindMapBuilder, StructureSynthesizer, SynecticsEngine
from llive.fullsense.types import ActionDecision, ActionPlan, Thought
from llive.oka import (
    CoreEssenceExtractor,
    ExplanationAligner,
    GroundTruthEssence,
    InsightScorer,
)


N = 100


def _b(i: int) -> Brief:
    return Brief(
        brief_id=f"oka-pipe-{i}",
        goal=f"保存量と対称性を活かす設計 (run #{i})。なぜそれが自然か説明したい。",
        constraints=("p99 < 100ms",),
        success_criteria=("0 件 data loss",),
    )


def main() -> None:
    out_dir = Path("docs/benchmarks/2026-05-17-full-validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "oka_pipeline.json"

    extractor = CoreEssenceExtractor()
    kj = KJExtractor(max_ideas=6)
    mm = MindMapBuilder(max_depth=2)
    syn = StructureSynthesizer()
    syne = SynecticsEngine()
    aligner = ExplanationAligner()
    scorer = InsightScorer()
    persp_engine = RoleBasedMultiTrack()
    plan = ActionPlan(
        decision=ActionDecision.PROPOSE,
        rationale="bench plan rationale",
        thought=Thought(text="t", confidence=0.85, triz_principles=[1, 15]),
    )

    pipeline_times = []
    per_stage = {k: [] for k in (
        "essence", "kj", "mindmap", "synectics", "perspectives",
        "structurize", "explanation", "insight_score",
    )}

    t_total = time.perf_counter()
    for i in range(N):
        brief = _b(i)
        gt = GroundTruthEssence(
            essence_summary="保存量と対称性",
            mystery="なぜ自然か",
            invariants=("保存量",),
            symmetries=("対称性",),
        )
        t0 = time.perf_counter()

        ts = time.perf_counter(); ce = extractor.extract(brief.goal, source_id=brief.brief_id); per_stage["essence"].append(time.perf_counter() - ts)
        ts = time.perf_counter(); board = kj.extract(brief); per_stage["kj"].append(time.perf_counter() - ts)
        ts = time.perf_counter(); tree = mm.build(brief); per_stage["mindmap"].append(time.perf_counter() - ts)
        ts = time.perf_counter(); _ = syne.generate(brief); per_stage["synectics"].append(time.perf_counter() - ts)
        ts = time.perf_counter(); persp = persp_engine.observe(brief, ActionDecision.PROPOSE, plan); per_stage["perspectives"].append(time.perf_counter() - ts)
        ts = time.perf_counter(); draft = syn.synthesize(brief, kj_board=board, mindmap=tree, perspectives=persp); per_stage["structurize"].append(time.perf_counter() - ts)
        ts = time.perf_counter(); _ = aligner.align("answer here", essence=ce, alternative_descriptions=("alt-A", "alt-B")); per_stage["explanation"].append(time.perf_counter() - ts)
        ts = time.perf_counter(); _ = scorer.score(ce, gt); per_stage["insight_score"].append(time.perf_counter() - ts)

        pipeline_times.append(time.perf_counter() - t0)

    total_wall = time.perf_counter() - t_total

    def _summary(xs):
        s = sorted(xs)
        return {
            "mean_ms": round(statistics.mean(xs) * 1000, 4),
            "median_ms": round(statistics.median(xs) * 1000, 4),
            "p95_ms": round(s[int(len(s) * 0.95)] * 1000, 4),
            "max_ms": round(max(xs) * 1000, 4),
        }

    report = {
        "n_runs": N,
        "total_wall_s": round(total_wall, 4),
        "throughput_per_s": round(N / total_wall, 2),
        "pipeline_per_run": _summary(pipeline_times),
        "per_stage": {k: _summary(v) for k, v in per_stage.items()},
    }
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out_path}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
