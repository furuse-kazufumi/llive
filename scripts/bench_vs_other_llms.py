#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Other-LLM comparison bench — llive (FullSenseLoop) × backend swap.

Three backends (mock / qwen2.5:7b / qwen2.5:14b) × three Briefs.
Same Brief content, same loop, only backend differs → measures the value
llive adds *and* how it scales with a heavier on-prem model.

Honest disclosure (per feedback_benchmark_honest_disclosure):
- Only on-prem (ollama) + mock comparison. Cloud APIs (Perplexity / Anthropic /
  Codex / Gemini) are NOT included in this run — those require credentials
  that are currently rotated/unavailable.
- All measurements are wall time on the same machine, same process.
- Output quality is judged by deterministic post-checks (length / contains key
  terms / has typos), not human judgement.

Output: docs/benchmarks/2026-05-17-full-validation/vs_other_llms.json
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

os.environ.setdefault("LLIVE_DISABLE_RAD_GROUNDING", "1")

from llive.fullsense.loop import FullSenseLoop
from llive.fullsense.types import EpistemicType, Stimulus


# ---- Briefs -----------------------------------------------------------------

BRIEFS = [
    {
        "id": "B1_math",
        "text": (
            "次の数式の等価性を判断してください: (x+1)^2 と x^2 + 2*x + 1。"
            "結論を 1 文で述べてください。"
        ),
        "expected_terms": ["等価", "等しい", "equal", "equivalent"],
        "typo_terms": ["lllive", "lllmesh"],
    },
    {
        "id": "B2_design",
        "text": (
            "保存量と対称性の関係を 3 行以内で説明してください。"
            "物理学的観点で重要な点を 1 つ挙げてください。"
        ),
        "expected_terms": ["保存", "対称", "Noether", "ネーター"],
        "typo_terms": ["lllive"],
    },
    {
        "id": "B3_spec",
        "text": (
            "次のシステムを設計します。要件: p99 レイテンシ < 100ms、"
            "データロス 0 件。3 つの主要設計判断を列挙してください。"
        ),
        "expected_terms": ["レイテンシ", "p99", "データ", "100ms"],
        "typo_terms": ["lllive"],
    },
]


BACKENDS = [
    {"name": "mock", "spec": None},
    {"name": "ollama:qwen2.5:7b", "spec": "ollama:qwen2.5:7b"},
    {"name": "ollama:qwen2.5:14b", "spec": "ollama:qwen2.5:14b"},
]


def _build_loop(backend_spec: str | None) -> FullSenseLoop:
    llm = None
    if backend_spec is not None:
        from llive.llm import OllamaBackend
        if backend_spec.startswith("ollama:"):
            model = backend_spec.split(":", 1)[1]
            llm = OllamaBackend(model=model, timeout=600.0)
        else:
            from llive.llm import resolve_backend
            llm = resolve_backend(backend_spec)
    return FullSenseLoop(sandbox=True, salience_threshold=0.0, llm_backend=llm)


def _grade(rationale: str, expected: list[str], typos: list[str]) -> dict:
    """Deterministic quality grade — no LLM judging."""
    text = (rationale or "")
    hit_expected = [t for t in expected if t.lower() in text.lower()]
    hit_typos = [t for t in typos if t.lower() in text.lower()]
    return {
        "rationale_chars": len(text),
        "rationale_words": len(re.findall(r"\S+", text)),
        "expected_terms_hit": hit_expected,
        "expected_coverage": round(len(hit_expected) / max(1, len(expected)), 3),
        "typo_terms_hit": hit_typos,
        "has_typo": bool(hit_typos),
    }


def _extract_llm_thought(result) -> str:
    """Pull the actual LLM-produced text from stages, not the loop's fixed
    rationale template. The Thought.text holds the inner monologue output."""
    # Prefer plan.thought.text (already a Thought dataclass)
    thought = getattr(result.plan, "thought", None)
    if thought is not None:
        text = getattr(thought, "text", None)
        if text:
            return str(text)
    # Fallback to stages['thought'] (dict form after _to_jsonable)
    stages = getattr(result, "stages", {}) or {}
    th = stages.get("thought")
    if isinstance(th, dict):
        return str(th.get("text", "") or "")
    return ""


def _run_one(backend_name: str, backend_spec: str | None, brief: dict) -> dict:
    loop = _build_loop(backend_spec)
    stim = Stimulus(
        content=brief["text"],
        source="manual",
        surprise=0.7,
        epistemic_type=EpistemicType.PRAGMATIC,
    )
    t0 = time.perf_counter()
    try:
        result = loop.process(stim)
        elapsed = time.perf_counter() - t0
        plan = result.plan
        thought_text = _extract_llm_thought(result)
        return {
            "ok": True,
            "elapsed_s": round(elapsed, 3),
            "decision": plan.decision.value,
            "rationale": plan.rationale,
            "thought_text": thought_text,
            "grade": _grade(thought_text, brief["expected_terms"], brief["typo_terms"]),
        }
    except Exception as exc:
        return {
            "ok": False,
            "elapsed_s": round(time.perf_counter() - t0, 3),
            "error": repr(exc),
        }


def main() -> None:
    out_dir = Path("docs/benchmarks/2026-05-17-full-validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "vs_other_llms.json"

    grid: dict = {}
    for backend in BACKENDS:
        grid[backend["name"]] = {}
        for brief in BRIEFS:
            print(f"[{backend['name']}] {brief['id']} ...", flush=True)
            r = _run_one(backend["name"], backend["spec"], brief)
            grid[backend["name"]][brief["id"]] = r
            if r["ok"]:
                print(f"  -> {r['elapsed_s']}s, decision={r['decision']}, "
                      f"coverage={r['grade']['expected_coverage']}, "
                      f"typo={r['grade']['has_typo']}")
            else:
                print(f"  -> ERROR: {r['error']}")

    # Aggregate
    summary = {}
    for backend_name, runs in grid.items():
        times = [r["elapsed_s"] for r in runs.values() if r["ok"]]
        coverages = [r["grade"]["expected_coverage"] for r in runs.values() if r["ok"]]
        typo_count = sum(1 for r in runs.values() if r["ok"] and r["grade"]["has_typo"])
        summary[backend_name] = {
            "runs": len(runs),
            "ok_count": len(times),
            "mean_elapsed_s": round(sum(times) / len(times), 3) if times else None,
            "mean_coverage": round(sum(coverages) / len(coverages), 3) if coverages else None,
            "any_typo": typo_count > 0,
            "typo_briefs": typo_count,
        }

    report = {
        "backends": [b["name"] for b in BACKENDS],
        "briefs": [b["id"] for b in BRIEFS],
        "grid": grid,
        "summary": summary,
        "notes": (
            "All on-prem (mock + ollama). Cloud APIs excluded — credentials "
            "rotated. Quality grading is deterministic post-check only."
        ),
    }
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {out_path}")
    print("\n--- summary ---")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
