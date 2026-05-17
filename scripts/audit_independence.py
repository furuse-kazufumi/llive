#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""IND-FX — Independence audit for llive vs llove / llmesh.

LinkedIn フィードバック (2026-05-17): 「llive / llove / llmesh が相互依存して
いると、単体使用の価値が半減する」を受け、現状の依存関係を機械的に検証する。

ルール:

* **llive は llove / llmesh に runtime 依存してはいけない** — llive 単体で
  全機能が動く必要がある
* MCP / OPC-UA / sensor bridge 等の連携機能は **optional dependency** として
  分離 (pyproject [project.optional-dependencies])
* import エラーで動作する機能 (try/except ImportError でラップされている) は OK

Usage:

    py -3.11 scripts/audit_independence.py
    # exit 0 = clean / exit 1 = leak detected

Report: docs/audits/independence-YYYY-MM-DD.md
"""

from __future__ import annotations

import ast
import datetime
import sys
from dataclasses import dataclass, field
from pathlib import Path


# llive がインポートしてはいけない外部 (sibling) パッケージ
_FORBIDDEN_PACKAGES: tuple[str, ...] = ("llove", "llmesh")

# 例外的に許可されるパス (test/docs/scripts ではない src/llive 内の参照のみが対象)
_SRC_ROOT = Path(__file__).resolve().parents[1] / "src" / "llive"


@dataclass(frozen=True)
class ImportLeak:
    file_path: str
    line: int
    import_target: str
    context: str   # "module" / "function" (try/except is treated as soft)


@dataclass(frozen=True)
class AuditReport:
    audited_files: int
    leaks: tuple[ImportLeak, ...]
    soft_imports: tuple[ImportLeak, ...]  # try/except でラップされた optional import

    @property
    def is_clean(self) -> bool:
        return not self.leaks


def _scan_file(path: Path) -> tuple[list[ImportLeak], list[ImportLeak]]:
    """Return (hard_leaks, soft_leaks) for one file."""
    hard: list[ImportLeak] = []
    soft: list[ImportLeak] = []
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return hard, soft

    # Collect line numbers that are inside try/except blocks
    soft_ranges: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            soft_ranges.append((node.lineno, node.end_lineno or node.lineno))

    def _in_try(lineno: int) -> bool:
        return any(s <= lineno <= e for s, e in soft_ranges)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _FORBIDDEN_PACKAGES:
                    leak = ImportLeak(
                        file_path=str(path),
                        line=node.lineno,
                        import_target=alias.name,
                        context="soft" if _in_try(node.lineno) else "hard",
                    )
                    (soft if leak.context == "soft" else hard).append(leak)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            root = node.module.split(".")[0]
            if root in _FORBIDDEN_PACKAGES:
                leak = ImportLeak(
                    file_path=str(path),
                    line=node.lineno,
                    import_target=node.module,
                    context="soft" if _in_try(node.lineno) else "hard",
                )
                (soft if leak.context == "soft" else hard).append(leak)
    return hard, soft


def audit() -> AuditReport:
    hard_all: list[ImportLeak] = []
    soft_all: list[ImportLeak] = []
    count = 0
    for py in _SRC_ROOT.rglob("*.py"):
        count += 1
        h, s = _scan_file(py)
        hard_all.extend(h)
        soft_all.extend(s)
    return AuditReport(
        audited_files=count,
        leaks=tuple(hard_all),
        soft_imports=tuple(soft_all),
    )


def _render_markdown(report: AuditReport) -> str:
    today = datetime.date.today().isoformat()
    lines = [
        f"# llive Independence Audit — {today}",
        "",
        f"Audited files: **{report.audited_files}**",
        f"Forbidden packages: `{', '.join(_FORBIDDEN_PACKAGES)}`",
        f"Hard leaks: **{len(report.leaks)}**",
        f"Soft imports (try/except wrapped): {len(report.soft_imports)}",
        "",
    ]
    if report.is_clean:
        lines.append("✓ **No hard runtime dependencies on llove / llmesh detected.**")
    else:
        lines.append("✗ **Hard leaks found — these must be removed or wrapped in try/except:**")
        lines.append("")
        for leak in report.leaks:
            lines.append(f"- `{leak.file_path}:{leak.line}` imports `{leak.import_target}`")
    if report.soft_imports:
        lines.append("")
        lines.append("### Soft imports (acceptable — optional features)")
        for leak in report.soft_imports:
            lines.append(f"- `{leak.file_path}:{leak.line}` imports `{leak.import_target}` (inside try/except)")
    return "\n".join(lines) + "\n"


def main() -> int:
    report = audit()
    today = datetime.date.today().isoformat()
    out_dir = Path("docs/audits")
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"independence-{today}.md"
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    print(f"wrote {md_path}")
    print(f"audited {report.audited_files} files / hard leaks={len(report.leaks)} / soft={len(report.soft_imports)}")
    return 0 if report.is_clean else 1


if __name__ == "__main__":
    sys.exit(main())
