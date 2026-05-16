#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Brief A/B runner — drop a single Brief into the FullSense Loop and report.

This is a *minimal* probe to learn what llive currently does when handed a
high-level Brief (vs what an external coding agent like Claude Code / Codex
does for the same Brief). It is intentionally small: it does NOT implement
the missing "Brief API" — that gap is the headline finding.

Usage::

    python scripts/run_brief.py "<brief text>"
    python scripts/run_brief.py path/to/brief.md
    python scripts/run_brief.py --json path/to/brief.md > result.json

The script writes a JSON record with the ActionPlan + per-stage diagnostics
so the result can be diffed against an external agent's output.
"""

from __future__ import annotations

import argparse
import dataclasses
import io
import json
import pathlib
import sys
import time
from typing import Any

# Windows default stdout (cp932) can't print U+2014 etc. — force UTF-8.
if isinstance(sys.stdout, io.TextIOWrapper):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # pragma: no cover
        pass

from llive.fullsense.loop import FullSenseLoop
from llive.fullsense.types import EpistemicType, Stimulus


def _to_jsonable(obj: Any) -> Any:
    """Best-effort conversion to JSON-serialisable primitives."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _to_jsonable(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if hasattr(obj, "value"):  # StrEnum and friends
        return obj.value
    return obj


def load_brief(arg: str) -> str:
    p = pathlib.Path(arg)
    if p.exists() and p.is_file():
        return p.read_text(encoding="utf-8")
    return arg


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("brief", help="brief text or path to a file containing the brief")
    parser.add_argument(
        "--source",
        default="manual",
        choices=("manual", "user", "sensor", "idle", "internal"),
        help="Stimulus.source label (default: manual)",
    )
    parser.add_argument(
        "--surprise",
        type=float,
        default=0.7,
        help="Stimulus.surprise score 0-1 (default: 0.7; salience gate default = 0.4)",
    )
    parser.add_argument(
        "--epistemic",
        default="pragmatic",
        choices=tuple(e.value for e in EpistemicType),
        help="Stimulus.epistemic_type (default: pragmatic — implementation-focused)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a single JSON record to stdout instead of human-readable text",
    )
    args = parser.parse_args(argv)

    brief_text = load_brief(args.brief)

    loop = FullSenseLoop(sandbox=True)
    stim = Stimulus(
        content=brief_text,
        source=args.source,
        surprise=args.surprise,
        epistemic_type=EpistemicType(args.epistemic),
    )

    t0 = time.perf_counter()
    result = loop.process(stim)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    record: dict[str, Any] = {
        "brief_chars": len(brief_text),
        "stim": {
            "source": stim.source,
            "surprise": stim.surprise,
            "epistemic_type": stim.epistemic_type.value if stim.epistemic_type else None,
            "stim_id": stim.stim_id,
        },
        "elapsed_ms": round(elapsed_ms, 2),
        "plan": {
            "decision": result.plan.decision.value,
            "rationale": getattr(result.plan, "rationale", None),
        },
        "stages": _to_jsonable(result.stages),
        "output_bus_len": len(loop.output_bus),
    }

    if args.json:
        json.dump(record, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"brief_chars      : {record['brief_chars']}")
        print(f"elapsed_ms       : {record['elapsed_ms']}")
        print(f"plan.decision    : {record['plan']['decision']}")
        print(f"plan.rationale   : {record['plan']['rationale']}")
        print(f"output_bus_len   : {record['output_bus_len']}")
        print(f"stages keys      : {sorted(record['stages'].keys())}")
        for k, v in record["stages"].items():
            print(f"  {k:14}: {v}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
