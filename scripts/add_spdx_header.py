"""Add SPDX-License-Identifier headers to all Python source files.

Adds the line ``# SPDX-License-Identifier: Apache-2.0`` to every ``.py``
file under ``src/`` and ``tests/`` that doesn't already have one.

Idempotent: running multiple times is safe.

Usage:
    py -3.11 scripts/add_spdx_header.py [--check] [--dirs src tests scripts]

Flags:
    --check       exit 1 if any file is missing the header (no writes)
    --dirs DIR... limit which directories to scan (default: src tests scripts)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SPDX_LINE = "# SPDX-License-Identifier: Apache-2.0"


def needs_header(path: Path) -> bool:
    try:
        head = path.read_text(encoding="utf-8").splitlines()[:5]
    except UnicodeDecodeError:
        return False
    return not any(SPDX_LINE in line for line in head)


def insert_header(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    insert_at = 0
    # preserve shebang
    if lines and lines[0].startswith("#!"):
        insert_at = 1
    # preserve PEP-263 coding declaration
    if insert_at < len(lines) and "coding" in lines[insert_at] and lines[insert_at].startswith("#"):
        insert_at += 1
    new_lines = lines[:insert_at] + [SPDX_LINE + "\n"] + lines[insert_at:]
    path.write_text("".join(new_lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 if any file is missing header")
    parser.add_argument(
        "--dirs",
        nargs="+",
        default=["src", "tests", "scripts"],
        help="directories to scan",
    )
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parent.parent
    missing: list[Path] = []
    for d in args.dirs:
        for path in (root / d).rglob("*.py"):
            if needs_header(path):
                missing.append(path)

    if args.check:
        for p in missing:
            print(f"missing SPDX header: {p.relative_to(root)}", file=sys.stderr)
        return 1 if missing else 0

    for p in missing:
        insert_header(p)
        print(f"added: {p.relative_to(root)}")
    print(f"\n{len(missing)} file(s) updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
