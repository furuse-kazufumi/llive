#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Codebase statistics — LOC / modules / tests / ratio.

Plus a quick re-run of independence audit so the validation bundle is self-contained.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


def _count_loc(path: Path) -> tuple[int, int, int]:
    """Return (total_lines, code_lines, blank_lines) — comments folded into code."""
    total = code = blank = 0
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            total += 1
            stripped = line.strip()
            if not stripped:
                blank += 1
            else:
                code += 1
    except Exception:
        pass
    return total, code, blank


def _module_count(tree: ast.AST) -> tuple[int, int]:
    classes = sum(1 for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
    funcs = sum(1 for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    return classes, funcs


def gather(root: Path) -> dict:
    files = list(root.rglob("*.py"))
    total_lines = code_lines = blank_lines = 0
    classes = funcs = 0
    per_subpkg: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "lines": 0, "code": 0})
    for f in files:
        tl, cl, bl = _count_loc(f)
        total_lines += tl
        code_lines += cl
        blank_lines += bl
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"))
            c, fn = _module_count(tree)
            classes += c
            funcs += fn
        except SyntaxError:
            pass
        # subpackage = first dir under root
        rel = f.relative_to(root)
        parts = rel.parts
        if len(parts) >= 1:
            sub = parts[0] if not parts[0].endswith(".py") else "(root)"
            per_subpkg[sub]["files"] += 1
            per_subpkg[sub]["lines"] += tl
            per_subpkg[sub]["code"] += cl
    return {
        "files": len(files),
        "total_lines": total_lines,
        "code_lines": code_lines,
        "blank_lines": blank_lines,
        "classes": classes,
        "functions": funcs,
        "per_subpackage": dict(per_subpkg),
    }


def main() -> None:
    out_dir = Path("docs/benchmarks/2026-05-17-full-validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "codebase_stats.json"

    src_stats = gather(Path("src/llive"))
    test_stats = gather(Path("tests"))

    # Independence audit (re-run for fresh snapshot)
    audit_out = subprocess.run(
        [sys.executable, "scripts/audit_independence.py"],
        capture_output=True, text=True, encoding="utf-8",
    )

    report = {
        "src": src_stats,
        "tests": test_stats,
        "test_to_code_ratio": round(test_stats["code_lines"] / max(1, src_stats["code_lines"]), 3),
        "independence_audit_exit": audit_out.returncode,
        "independence_audit_stdout": audit_out.stdout.strip(),
    }
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out_path}")
    print(json.dumps({k: v for k, v in report.items() if k != "src" and k != "tests"}, ensure_ascii=False, indent=2))
    print(f"src: files={src_stats['files']}, code_lines={src_stats['code_lines']}, classes={src_stats['classes']}, funcs={src_stats['functions']}")
    print(f"tests: files={test_stats['files']}, code_lines={test_stats['code_lines']}")


if __name__ == "__main__":
    main()
