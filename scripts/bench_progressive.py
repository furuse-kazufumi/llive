#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Progressive llive validation — model size × prompt-token size × FullSense loop.

Sweeps a matrix of (token-size, model) pairs, drives each cell through the
Brief API (LLIVE-002), and records the loop's stage diagnostics. The goal
is to surface where llive's internals start to bend under token pressure
and how that bend changes with model capacity.

Constraints respected:

* feedback_llive_measurement_purity — on-prem (Ollama) backends only; no
  cloud APIs in the same sweep.
* feedback_benchmark_progressive_tokens — fixed xs/s/m/l/xl ladder.

Usage::

    py -3.11 scripts/bench_progressive.py --models llama3.2:latest qwen2.5:7b \\
        --sizes xs s --out docs/benchmarks/2026-05-16-progressive/

    # smoke (1 cell)
    py -3.11 scripts/bench_progressive.py --smoke

Output files (one matrix per run):

    <out>/matrix.json   — full per-cell records
    <out>/summary.md    — human-readable table + observations
"""

from __future__ import annotations

import argparse
import io
import json
import os
import pathlib
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any

# Force UTF-8 stdout on Windows so per-cell logs print correctly.
if isinstance(sys.stdout, io.TextIOWrapper):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # pragma: no cover
        pass

from llive.brief import Brief, BriefLedger, BriefRunner, BriefStatus
from llive.fullsense.loop import FullSenseLoop
from llive.llm import OllamaBackend


# ---------------------------------------------------------------------------
# Token-size ladder — feedback_benchmark_progressive_tokens
# ---------------------------------------------------------------------------

# A 1-paragraph base unit, deliberately written to exercise the salience and
# curiosity stages: novel domain (precision metrology + LLM), explicit
# constraint vocabulary, and TRIZ-trigger keywords (vs / trade-off / parameter).
_BASE_PARAGRAPH = (
    "Investigate whether VQ-quantised spherical-harmonic coefficients from a "
    "3D Gaussian Splatting reconstruction can be tokenised for a precision-"
    "metrology LLM. The trade-off is between geometric fidelity and dynamic "
    "parameter range; static codebooks lose detail on novel parts whereas "
    "dynamic codebooks balloon the vocabulary."
)

# Target token counts: a single _BASE_PARAGRAPH is ~50 tokens.
_SIZE_RATIO = {
    "xs": 1,    # ~50 tokens
    "s": 4,     # ~200 tokens
    "m": 16,    # ~800 tokens
    "l": 60,    # ~3000 tokens
    "xl": 200,  # ~10000 tokens
}

# num_ctx override per size. Ollama's default (2048) silently truncates l/xl,
# so we widen the window. Picked to leave headroom for max_tokens=512 generation
# on top of the input. xl uses 16384 — only some models (qwen2.5 family) actually
# honour that; smaller models cap at their build-time limit.
_SIZE_NUM_CTX = {
    "xs": None,    # use Ollama default
    "s": None,
    "m": 4096,
    "l": 8192,
    "xl": 16384,
}

ALL_SIZES: tuple[str, ...] = ("xs", "s", "m", "l", "xl")


def build_prompt(size: str) -> str:
    n = _SIZE_RATIO[size]
    body = "\n\n".join(_BASE_PARAGRAPH for _ in range(n))
    return (
        "Context — progressive token validation matrix.\n\n"
        + body
        + "\n\nQuestion: based on the constraints above, what is the single "
        "most important parameter that gates feasibility, and why?"
    )


# ---------------------------------------------------------------------------
# Per-cell record
# ---------------------------------------------------------------------------


@dataclass
class CellRecord:
    model: str
    size: str
    prompt_chars: int
    elapsed_ms: float
    status: str
    decision: str
    rationale: str
    salience: dict[str, Any] = field(default_factory=dict)
    curiosity: dict[str, Any] = field(default_factory=dict)
    thought_chars: int = 0
    thought_confidence: float | None = None
    llm_elapsed_ms: float | None = None
    llm_response_chars: int | None = None
    ledger_entries: int = 0
    error: str | None = None


# ---------------------------------------------------------------------------
# Cell runner
# ---------------------------------------------------------------------------


def run_cell(*, model: str, size: str, out_dir: pathlib.Path) -> CellRecord:
    """Run one (model, size) cell through the Brief → FullSenseLoop pipeline."""
    prompt = build_prompt(size)
    brief = Brief(
        brief_id=f"prog-{size}-{model.replace(':', '_').replace('.', '_')}",
        goal=prompt,
        source="bench:progressive",
        priority=0.7,
        approval_required=False,   # bench runs unblocked — Step 4 gate is exercised separately
        ledger_path=out_dir / f"{size}-{model.replace(':', '_')}.jsonl",
    )

    backend = OllamaBackend(model=model)
    loop = FullSenseLoop(
        sandbox=True,
        salience_threshold=0.0,    # never gate on length here — we want stage data
        llm_backend=backend,
        debug=True,                # capture llm_elapsed_ms / llm_response_chars
    )
    runner = BriefRunner(loop=loop)

    t0 = time.perf_counter()
    try:
        result = runner.submit(brief)
    except Exception as exc:
        return CellRecord(
            model=model,
            size=size,
            prompt_chars=len(prompt),
            elapsed_ms=round((time.perf_counter() - t0) * 1000, 2),
            status="error",
            decision="(crash)",
            rationale="",
            error=repr(exc),
        )
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

    # Pull stage diagnostics back from the ledger so we get the same source of
    # truth the operator would see when post-hoc inspecting a run.
    salience: dict[str, Any] = {}
    curiosity: dict[str, Any] = {}
    thought_chars = 0
    thought_confidence: float | None = None
    llm_elapsed_ms: float | None = None
    llm_response_chars: int | None = None
    for rec in BriefLedger(brief.ledger_path).read():
        if rec.event != "loop_completed":
            continue
        stages = rec.payload.get("stages", {})
        if isinstance(stages, dict):
            sal = stages.get("salience")
            if isinstance(sal, dict):
                salience = {k: sal.get(k) for k in ("score", "threshold", "pass")}
            cur = stages.get("curiosity")
            if isinstance(cur, dict):
                curiosity = {
                    k: cur.get(k)
                    for k in ("score", "novelty", "known_overlap", "high_curiosity")
                }
            thought = stages.get("thought")
            if isinstance(thought, dict):
                txt = thought.get("text", "")
                thought_chars = len(txt) if isinstance(txt, str) else 0
                conf = thought.get("confidence")
                thought_confidence = float(conf) if isinstance(conf, (int, float)) else None
                dbg = thought.get("debug")
                if isinstance(dbg, dict):
                    le = dbg.get("llm_elapsed_ms")
                    if isinstance(le, (int, float)):
                        llm_elapsed_ms = float(le)
                    lr = dbg.get("llm_response_chars")
                    if isinstance(lr, (int, float)):
                        llm_response_chars = int(lr)

    return CellRecord(
        model=model,
        size=size,
        prompt_chars=len(prompt),
        elapsed_ms=elapsed_ms,
        status=result.status.value,
        decision=_decision_from_ledger(brief, fallback=result.status.value),
        rationale=result.rationale,
        salience=salience,
        curiosity=curiosity,
        thought_chars=thought_chars,
        thought_confidence=thought_confidence,
        llm_elapsed_ms=llm_elapsed_ms,
        llm_response_chars=llm_response_chars,
        ledger_entries=result.ledger_entries,
        error=result.error,
    )


def _decision_from_ledger(brief: Brief, *, fallback: str) -> str:
    for rec in BriefLedger(brief.ledger_path).read():  # type: ignore[arg-type]
        if rec.event == "decision":
            d = rec.payload.get("decision")
            if isinstance(d, str):
                return d
    return fallback


# ---------------------------------------------------------------------------
# Matrix driver + reporters
# ---------------------------------------------------------------------------


def run_matrix(
    *,
    models: list[str],
    sizes: list[str],
    out_dir: pathlib.Path,
    on_cell: Any = None,
) -> list[CellRecord]:
    out_dir.mkdir(parents=True, exist_ok=True)
    records: list[CellRecord] = []
    for size in sizes:
        for model in models:
            print(f"[cell] model={model} size={size} ...", flush=True)
            rec = run_cell(model=model, size=size, out_dir=out_dir)
            records.append(rec)
            print(
                f"    -> elapsed={rec.elapsed_ms} ms  status={rec.status}  "
                f"decision={rec.decision}  llm_ms={rec.llm_elapsed_ms}  "
                f"thought_chars={rec.thought_chars}",
                flush=True,
            )
            if on_cell is not None:
                on_cell(rec)
    return records


def write_outputs(records: list[CellRecord], out_dir: pathlib.Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    matrix_path = out_dir / "matrix.json"
    summary_path = out_dir / "summary.md"

    with matrix_path.open("w", encoding="utf-8") as fh:
        json.dump(
            {
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "ollama_host": os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
                "cells": [asdict(r) for r in records],
            },
            fh,
            ensure_ascii=False,
            indent=2,
        )

    with summary_path.open("w", encoding="utf-8") as fh:
        fh.write("# llive progressive validation matrix\n\n")
        fh.write("> on-prem only (Ollama). One Brief per cell, all flowing through\n")
        fh.write("> the Brief API → FullSenseLoop pipeline (LLIVE-001 + LLIVE-002).\n\n")
        fh.write("## Wall-time matrix (ms)\n\n")
        fh.write(_render_table(records, lambda r: f"{r.elapsed_ms:.0f}"))
        fh.write("\n\n## LLM-only wall time (ms; loop overhead excluded)\n\n")
        fh.write(_render_table(records, lambda r: f"{r.llm_elapsed_ms:.0f}" if r.llm_elapsed_ms else "—"))
        fh.write("\n\n## Loop decision\n\n")
        fh.write(_render_table(records, lambda r: r.decision))
        fh.write("\n\n## Salience score\n\n")
        fh.write(_render_table(records, lambda r: f"{r.salience.get('score', '—')}"))
        fh.write("\n\n## Curiosity score\n\n")
        fh.write(_render_table(records, lambda r: f"{r.curiosity.get('score', '—')}"))
        fh.write("\n\n## Thought text length (chars)\n\n")
        fh.write(_render_table(records, lambda r: str(r.thought_chars)))
        fh.write("\n\n## Per-cell ledger entries\n\n")
        fh.write(_render_table(records, lambda r: str(r.ledger_entries)))
        if any(r.error for r in records):
            fh.write("\n\n## Errors\n\n")
            for r in records:
                if r.error:
                    fh.write(f"- `{r.model}` × `{r.size}` → {r.error}\n")


def _render_table(records: list[CellRecord], cell_fn: Any) -> str:
    sizes = sorted({r.size for r in records}, key=lambda s: ALL_SIZES.index(s))
    models = sorted({r.model for r in records})
    by_key = {(r.model, r.size): r for r in records}
    out = ["| model \\ size | " + " | ".join(sizes) + " |"]
    out.append("| --- | " + " | ".join("---" for _ in sizes) + " |")
    for m in models:
        row = [f"`{m}`"]
        for s in sizes:
            rec = by_key.get((m, s))
            row.append(cell_fn(rec) if rec is not None else "—")
        out.append("| " + " | ".join(row) + " |")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models",
        nargs="+",
        default=["llama3.2:latest", "qwen2.5:7b", "qwen2.5:14b"],
        help="Ollama model ids to sweep (must be installed locally)",
    )
    parser.add_argument(
        "--sizes",
        nargs="+",
        default=list(ALL_SIZES),
        choices=ALL_SIZES,
        help="Token-size ladder rungs to include",
    )
    parser.add_argument(
        "--out",
        type=pathlib.Path,
        default=pathlib.Path("docs/benchmarks/progressive-matrix"),
        help="Output directory for matrix.json + summary.md + per-cell ledgers",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Single cell (first model × xs) — for wiring sanity checks",
    )
    args = parser.parse_args(argv)

    if args.smoke:
        args.models = args.models[:1]
        args.sizes = ["xs"]

    out_dir = args.out.expanduser().resolve()
    print(
        f"[bench] models={args.models}  sizes={args.sizes}  out={out_dir}",
        flush=True,
    )

    records = run_matrix(models=args.models, sizes=args.sizes, out_dir=out_dir)
    write_outputs(records, out_dir)

    print(f"[bench] wrote {out_dir / 'matrix.json'}")
    print(f"[bench] wrote {out_dir / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
