# SPDX-License-Identifier: Apache-2.0
"""Import the Raptor RAD (Research Aggregation Directory) corpus into llive.

Raptor が D:/docs/<分野>_v2/ などに蓄えている RAD コーパスを、
llive 配下 (``data/rad/``) に物理コピーして「独立した知識庫」として使えるようにする。

Phase A (v0.2.0) の取り込み層スクリプト。標準ライブラリのみで動く。

レイアウト::

    data/rad/
      <分野>_v2/            ← Raptor からの読み専用ミラー
      _learned/<分野>/      ← llive 自身の学習堆積 (Phase B で利用)
      _index.json           ← 取り込みメタ (このスクリプトが生成)

ソース解決優先順位 (環境変数 → 既定):

    1. ``--source`` 引数
    2. ``$LLIVE_RAD_SOURCE``
    3. ``$RAPTOR_CORPUS_DIR``
    4. ``D:/docs``

宛先解決優先順位:

    1. ``--dest`` 引数
    2. ``$LLIVE_RAD_DIR``
    3. ``<repo root>/data/rad``

差分判定はサイズ + mtime ベース (高速)。完全一致を確かめたい場合は ``--force`` で全再コピー。

Usage::

    py -3.11 scripts/import_rad.py --dry-run                    # 全 _v2 分野を確認
    py -3.11 scripts/import_rad.py                              # 全 _v2 分野を取り込み
    py -3.11 scripts/import_rad.py --corpora hacker_corpus_v2   # 指定分野のみ
    py -3.11 scripts/import_rad.py --include-legacy             # _v2 以外も含める
    py -3.11 scripts/import_rad.py --mirror                     # 削除も同期
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path("D:/docs")
DEFAULT_DEST = ROOT / "data" / "rad"
INDEX_FILE = "_index.json"
LEARNED_DIR = "_learned"
SCHEMA_VERSION = 1


@dataclass
class CorpusStat:
    name: str
    source_subpath: str
    file_count: int = 0
    bytes: int = 0
    added: int = 0
    updated: int = 0
    skipped: int = 0
    removed: int = 0
    imported_at: str = ""


@dataclass
class ImportReport:
    schema_version: int = SCHEMA_VERSION
    source: str = ""
    dest: str = ""
    imported_at: str = ""
    corpora: dict[str, dict] = field(default_factory=dict)


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def resolve_source(arg: str | None) -> Path:
    if arg:
        return Path(arg).resolve()
    env = os.environ.get("LLIVE_RAD_SOURCE") or os.environ.get("RAPTOR_CORPUS_DIR")
    if env:
        return Path(env).resolve()
    return DEFAULT_SOURCE.resolve()


def resolve_dest(arg: str | None) -> Path:
    if arg:
        return Path(arg).resolve()
    env = os.environ.get("LLIVE_RAD_DIR")
    if env:
        return Path(env).resolve()
    return DEFAULT_DEST.resolve()


def list_corpora(source: Path, *, include_legacy: bool, only: list[str] | None) -> list[Path]:
    if not source.exists():
        raise FileNotFoundError(f"source not found: {source}")
    dirs = [p for p in sorted(source.iterdir()) if p.is_dir()]
    if only:
        wanted = {n.strip() for n in only if n.strip()}
        dirs = [p for p in dirs if p.name in wanted]
        missing = wanted - {p.name for p in dirs}
        if missing:
            print(f"[WARN] unknown corpora ignored: {sorted(missing)}", file=sys.stderr)
        return dirs
    if include_legacy:
        return dirs
    # 既定: _v2 があれば優先、無い分野は v1 を採用 (tui_corpus, security_papers_2025_2026 等)
    by_base: dict[str, dict[str, Path]] = {}
    for p in dirs:
        if p.name.endswith("_v2"):
            base = p.name[:-3]
            by_base.setdefault(base, {})["v2"] = p
        else:
            by_base.setdefault(p.name, {}).setdefault("v1", p)
    chosen: list[Path] = []
    for versions in by_base.values():
        chosen.append(versions.get("v2") or versions["v1"])
    return sorted(chosen, key=lambda p: p.name)


def _same(src: Path, dst: Path) -> bool:
    try:
        s = src.stat()
        d = dst.stat()
    except FileNotFoundError:
        return False
    return s.st_size == d.st_size and int(s.st_mtime) == int(d.st_mtime)


def sync_corpus(
    src_dir: Path,
    dst_dir: Path,
    *,
    mirror: bool,
    dry_run: bool,
    force: bool,
) -> CorpusStat:
    stat = CorpusStat(name=src_dir.name, source_subpath=src_dir.name)

    # 1. source → dest コピー
    for src in src_dir.rglob("*"):
        rel = src.relative_to(src_dir)
        dst = dst_dir / rel
        if src.is_dir():
            if not dry_run:
                dst.mkdir(parents=True, exist_ok=True)
            continue
        if not src.is_file():
            continue  # symlink / 特殊ファイルはスキップ
        stat.file_count += 1
        stat.bytes += src.stat().st_size
        existed_before = dst.exists()
        if existed_before and not force and _same(src, dst):
            stat.skipped += 1
            continue
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        if existed_before:
            stat.updated += 1
        else:
            stat.added += 1

    # 2. mirror モード: source に存在しないファイルを dest から削除
    if mirror and dst_dir.exists():
        for dst in dst_dir.rglob("*"):
            rel = dst.relative_to(dst_dir)
            src = src_dir / rel
            if dst.is_file() and not src.exists():
                if not dry_run:
                    dst.unlink()
                stat.removed += 1

    stat.imported_at = now_iso()
    return stat


def write_index(dest: Path, report: ImportReport, *, dry_run: bool) -> Path:
    path = dest / INDEX_FILE
    if dry_run:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(report)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def ensure_learned_dir(dest: Path, *, dry_run: bool) -> None:
    """書き層の予約ディレクトリ (Phase B で使う)。空でも README を置いておく。"""
    learned = dest / LEARNED_DIR
    if dry_run:
        return
    learned.mkdir(parents=True, exist_ok=True)
    readme = learned / "README.md"
    if not readme.exists():
        readme.write_text(
            "# `_learned/` — llive 学習堆積層 (Phase B)\n\n"
            "ここには llive の生物学的記憶モデル "
            "(semantic / consolidation) から書き戻された学習物が "
            "`<分野>/<doc-id>.md` 形式で堆積する。\n"
            "Raptor RAD 由来の読み層 (`../<分野>_v2/`) と "
            "同じ `RadCorpusIndex` に統合され、出典は "
            "`provenance.json` で管理される。\n",
            encoding="utf-8",
        )


def format_stat(stat: CorpusStat) -> str:
    return (
        f"{stat.name:<40} "
        f"files={stat.file_count:>6}  "
        f"bytes={stat.bytes:>10}  "
        f"added={stat.added:>5} updated={stat.updated:>5} "
        f"skipped={stat.skipped:>5} removed={stat.removed:>5}"
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Import Raptor RAD corpus into llive/data/rad",
    )
    p.add_argument("--source", help="Raptor RAD source dir (default: $LLIVE_RAD_SOURCE | $RAPTOR_CORPUS_DIR | D:/docs)")
    p.add_argument("--dest", help="llive RAD dest dir (default: $LLIVE_RAD_DIR | <repo>/data/rad)")
    p.add_argument("--corpora", help="comma-separated corpus names (overrides --all)")
    p.add_argument("--all", action="store_true", help="include all _v2 corpora (default)")
    p.add_argument("--include-legacy", action="store_true", help="also include non-_v2 corpora")
    p.add_argument("--mirror", action="store_true", help="also delete files no longer in source")
    p.add_argument("--force", action="store_true", help="re-copy every file (ignore size+mtime)")
    p.add_argument("--dry-run", action="store_true", help="show plan but do not touch files")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    # Windows cp932 でも絵文字 / em-dash を吐けるよう stdout を UTF-8 に再設定
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args(argv)
    source = resolve_source(args.source)
    dest = resolve_dest(args.dest)
    only = list(args.corpora.split(",")) if args.corpora else None

    print(f"[import_rad] source = {source}")
    print(f"[import_rad] dest   = {dest}")
    if args.dry_run:
        print("[import_rad] DRY RUN -- no files will be modified")

    try:
        corpora = list_corpora(source, include_legacy=args.include_legacy, only=only)
    except FileNotFoundError as e:
        print(f"[ERR] {e}", file=sys.stderr)
        return 2
    if not corpora:
        print("[import_rad] no corpora matched", file=sys.stderr)
        return 1

    report = ImportReport(
        source=str(source),
        dest=str(dest),
        imported_at=now_iso(),
    )

    print(f"[import_rad] {len(corpora)} corpora")
    for src_dir in corpora:
        dst_dir = dest / src_dir.name
        stat = sync_corpus(
            src_dir,
            dst_dir,
            mirror=args.mirror,
            dry_run=args.dry_run,
            force=args.force,
        )
        report.corpora[stat.name] = asdict(stat)
        print(f"  {format_stat(stat)}")

    ensure_learned_dir(dest, dry_run=args.dry_run)
    index_path = write_index(dest, report, dry_run=args.dry_run)
    total_files = sum(s["file_count"] for s in report.corpora.values())
    total_bytes = sum(s["bytes"] for s in report.corpora.values())
    print(
        f"[import_rad] total: {total_files} files, "
        f"{total_bytes / (1024 * 1024):.1f} MB, index={index_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
