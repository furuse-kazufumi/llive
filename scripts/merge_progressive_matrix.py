#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Merge multiple progressive-bench matrix.json files into one summary.

Used after running ``bench_progressive.py`` in stages (xs/s separate from
m / l / xl) so the per-size dirs can be reconciled into a single matrix
report without re-running the cells.

Usage::

    py -3.11 scripts/merge_progressive_matrix.py \\
        --inputs docs/benchmarks/2026-05-16-progressive-xss \\
                 docs/benchmarks/2026-05-16-progressive-m \\
        --out docs/benchmarks/2026-05-16-progressive-merged
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from bench_progressive import ALL_SIZES, CellRecord, write_outputs  # noqa: E402


def _load_cells(path: pathlib.Path) -> list[CellRecord]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: list[CellRecord] = []
    for raw in payload.get("cells", []):
        out.append(CellRecord(**{k: raw[k] for k in raw if hasattr(CellRecord, "__dataclass_fields__") and k in CellRecord.__dataclass_fields__}))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inputs",
        nargs="+",
        required=True,
        type=pathlib.Path,
        help="Directories that contain a matrix.json from bench_progressive.py",
    )
    parser.add_argument("--out", type=pathlib.Path, required=True)
    args = parser.parse_args(argv)

    all_cells: list[CellRecord] = []
    for d in args.inputs:
        mj = d / "matrix.json"
        if not mj.is_file():
            print(f"[merge] WARN: {mj} not found, skipping")
            continue
        cells = _load_cells(mj)
        all_cells.extend(cells)
        print(f"[merge] {mj}: {len(cells)} cells")

    # de-dupe by (model, size) — later wins
    by_key: dict[tuple[str, str], CellRecord] = {}
    for c in all_cells:
        by_key[(c.model, c.size)] = c
    merged = list(by_key.values())

    # sort: model asc, size in canonical order
    merged.sort(key=lambda r: (r.model, ALL_SIZES.index(r.size)))

    write_outputs(merged, args.out.expanduser().resolve())
    print(f"[merge] wrote {len(merged)} cells → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
