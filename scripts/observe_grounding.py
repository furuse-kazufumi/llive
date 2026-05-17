# SPDX-License-Identifier: Apache-2.0
"""Run a handful of realistic Briefs through BriefGrounder and report what
each grounding citation channel (TRIZ / RAD / calc / units / constants) actually
surfaces. The point is to *observe* — not to assert — so we can decide which
parts of the minimal grounding layer need follow-up iteration.

Usage:

    py -3.11 scripts/observe_grounding.py [--out path.md]

The script runs entirely with the offline TRIZ index + an empty RAD index (so
no corpus is needed), and writes a Markdown summary that can be folded into
articles or REQUIREMENTS.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

# Disable the heavyweight RAD corpus bootstrap — we want to focus the
# observation on the math-side grounding (calc / units / constants).
os.environ.setdefault("LLIVE_DISABLE_RAD_GROUNDING", "1")

from llive.brief import Brief, BriefGrounder, BriefLedger, BriefRunner
from llive.fullsense.loop import FullSenseLoop
from llive.triz.loader import load_principles


SAMPLE_BRIEFS: list[Brief] = [
    Brief(
        brief_id="phys-drone",
        goal=(
            "Design a delivery drone that maintains 5 m/s during a 30 s window "
            "at 100 kg payload, given a 9.81 m/s^2 gravitational acceleration "
            "and a 1.2 kg/m^3 air density. Confirm (5 * 30) covers the route."
        ),
    ),
    Brief(
        brief_id="energy-photon",
        goal=(
            "Compute the photon energy at 500 nm using the planck constant "
            "and the speed of light. Cross-check via the elementary charge to "
            "express the result in eV."
        ),
    ),
    Brief(
        brief_id="trade-off",
        goal=(
            "Resolve the trade-off between high precision and speed in our "
            "evaluation pipeline. We need a parameter that controls quality "
            "without breaking determinism."
        ),
    ),
    Brief(
        brief_id="bookkeep",
        goal=(
            "Ship the report in 5 days, then revisit in 2 weeks. Each chapter "
            "should be under 30 pages. Send 1 email per milestone."
        ),
    ),
    Brief(
        brief_id="mixed",
        goal=(
            "Use the boltzmann constant to estimate kT at 300 K and compare "
            "with (1.38e-23 * 300). Confirm the result lies between 4 J and "
            "5 J for a mole of ideal gas. avogadro should appear too."
        ),
    ),
    Brief(
        brief_id="prose-only",
        goal=(
            "Write the executive summary of the architecture rationale. "
            "Focus on auditability and reproducibility, not numbers."
        ),
    ),
]


def _summarise_one(brief: Brief, runner: BriefRunner) -> dict:
    ledger_path = Path(brief.ledger_path) if brief.ledger_path else None
    if ledger_path is None:
        # Force a per-brief ledger for inspection
        ledger_path = Path(f".tmp-grounding-obs-{brief.brief_id}.jsonl")
        brief = Brief(
            brief_id=brief.brief_id,
            goal=brief.goal,
            approval_required=False,
            ledger_path=ledger_path,
        )
    runner.submit(brief)
    records = list(BriefLedger(ledger_path).read())
    grounding = next((r for r in records if r.event == "grounding_applied"), None)
    augmented = next((r for r in records if r.event == "stimulus_built"), None)
    g_payload = grounding.payload if grounding else {}
    summary = {
        "brief_id": brief.brief_id,
        "goal": brief.goal,
        "triz": g_payload.get("triz", []),
        "rad": g_payload.get("rad", []),
        "calc": g_payload.get("calc", []),
        "units": g_payload.get("units", []),
        "constants": g_payload.get("constants", []),
        "augmented_goal_chars": g_payload.get("augmented_goal_chars"),
    }
    return summary


def _render_markdown(rows: list[dict]) -> str:
    lines: list[str] = [
        "# BriefGrounder 観察レポート (実 Brief サンプル 6 件)",
        "",
        "MATH-01/05/08 + TRIZ の citation channel が実 Brief で何を surface するかの観察結果。",
        "**目的**: assertion ではなく観察。次イテレーションの優先順位を決める材料。",
        "",
        "## サマリー",
        "",
        "| brief_id | TRIZ | calc | units | constants | augmented_goal 字数 |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| `{r['brief_id']}` | {len(r['triz'])} | {len(r['calc'])} | "
            f"{len(r['units'])} | {len(r['constants'])} | "
            f"{r['augmented_goal_chars']} |"
        )
    lines.append("")
    for r in rows:
        lines.append(f"## `{r['brief_id']}`")
        lines.append("")
        lines.append(f"**Goal**: {r['goal']}")
        lines.append("")
        if r["triz"]:
            lines.append("**TRIZ citations**:")
            for c in r["triz"]:
                lines.append(
                    f"- #{c['principle_id']} {c.get('name')} "
                    f"(trigger: `{c.get('trigger')}`)"
                )
            lines.append("")
        if r["calc"]:
            lines.append("**Inline calculations (MATH-08)**:")
            for c in r["calc"]:
                if c["error"]:
                    lines.append(f"- `{c['expression']}` → ERROR: {c['error']}")
                else:
                    lines.append(
                        f"- `{c['expression']}` = {c['value']} "
                        f"(ops={c['operation_count']})"
                    )
            lines.append("")
        if r["units"]:
            lines.append("**Quantities recognised (MATH-01)**:")
            for u in r["units"]:
                if u["error"]:
                    lines.append(
                        f"- `{u['raw_text']}` → UNKNOWN: {u['error']}"
                    )
                else:
                    lines.append(
                        f"- `{u['raw_text']}` → value={u['value']}, "
                        f"dims={u['dimensions']}"
                    )
            lines.append("")
        if r["constants"]:
            lines.append("**Physical constants grounded (MATH-05)**:")
            for c in r["constants"]:
                lines.append(
                    f"- `{c['matched_alias']}` → {c['symbol']} = {c['value']} "
                    f"[{c['dimensions']}] ({c['source']})"
                )
            lines.append("")
    # Aggregated observation notes
    lines.append("## 集約観察")
    lines.append("")
    error_units = sum(
        1 for r in rows for u in r["units"] if u["error"] is not None
    )
    ok_units = sum(
        1 for r in rows for u in r["units"] if u["error"] is None
    )
    error_calcs = sum(
        1 for r in rows for c in r["calc"] if c["error"] is not None
    )
    ok_calcs = sum(
        1 for r in rows for c in r["calc"] if c["error"] is None
    )
    total_constants = sum(len(r["constants"]) for r in rows)
    lines.append(
        f"- 単位 citation: 成功 {ok_units} 件 / 失敗 {error_units} 件"
    )
    lines.append(
        f"- 計算 citation: 成功 {ok_calcs} 件 / 失敗 {error_calcs} 件"
    )
    lines.append(f"- 定数 citation 合計: {total_constants} 件")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    grounder = BriefGrounder(principles=load_principles())
    runner = BriefRunner(
        loop=FullSenseLoop(sandbox=True, salience_threshold=0.0),
        grounder=grounder,
    )
    rows = [_summarise_one(b, runner) for b in SAMPLE_BRIEFS]
    md = _render_markdown(rows)
    if args.out:
        args.out.write_text(md, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(md)
    # Clean up tmp ledgers
    for b in SAMPLE_BRIEFS:
        tmp = Path(f".tmp-grounding-obs-{b.brief_id}.jsonl")
        if tmp.exists():
            tmp.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
