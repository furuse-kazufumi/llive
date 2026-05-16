# SPDX-License-Identifier: Apache-2.0
"""Import a tar.gz bundle into a fresh substrate (§MI1).

Importer は state を **新しい dest_dir に物理展開** する. Bundle に
含まれるファイルを dest_dir/{approval,sandbox,production}/ に配置し、
ledger は SqliteLedger で開けば即 replay 可能.
"""

from __future__ import annotations

import json
import tarfile
from dataclasses import dataclass, field
from pathlib import Path

from llive.migration.bundle import MANIFEST_FILENAME, SCHEMA_VERSION, BundleManifest


class IncompatibleBundleError(RuntimeError):
    """Bundle schema_version が importer の MAJOR と一致しない."""


@dataclass(frozen=True)
class ImportResult:
    """import_state() の戻り値."""

    manifest: BundleManifest
    dest_dir: Path
    ledger_path: Path | None
    sandbox_records_path: Path | None
    sandbox_denied_emits_path: Path | None
    production_records_path: Path | None
    memory_paths: dict[str, Path] = field(default_factory=dict)
    """Tier name → restored path (C-4). 例: ``{"episodic": dest/memory/episodic/file.duckdb}``"""


def _safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
    """Path traversal を防ぎつつ tar を展開する."""
    dest_resolved = dest.resolve()
    for member in tar.getmembers():
        target = (dest / member.name).resolve()
        if not str(target).startswith(str(dest_resolved)):
            raise RuntimeError(f"unsafe tar entry: {member.name!r}")
    tar.extractall(dest)


def import_state(bundle_path: Path | str, *, dest_dir: Path | str) -> ImportResult:
    """tar.gz bundle を dest_dir に展開し、状態 path を返す.

    Raises:
        IncompatibleBundleError: schema_version の MAJOR が異なる.
        FileNotFoundError: bundle に manifest.json が無い.
    """
    bundle_path = Path(bundle_path)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    with tarfile.open(bundle_path, "r:gz") as tar:
        _safe_extract(tar, dest_dir)

    manifest_file = dest_dir / MANIFEST_FILENAME
    if not manifest_file.exists():
        raise FileNotFoundError(f"manifest.json missing in bundle: {bundle_path!r}")

    manifest = BundleManifest.from_json(manifest_file.read_text(encoding="utf-8"))
    if manifest.schema_version != SCHEMA_VERSION:
        # Minor 違いは許容する (forward-compatibly)、MAJOR 違いは reject
        # 現状 schema は v1 のみなので厳密一致でよい
        raise IncompatibleBundleError(
            f"bundle schema_version={manifest.schema_version}, importer={SCHEMA_VERSION}"
        )

    ledger_path = dest_dir / "approval" / "ledger.db"
    sandbox_records = dest_dir / "sandbox" / "records.jsonl"
    sandbox_denied = dest_dir / "sandbox" / "denied_emits.jsonl"
    production = dest_dir / "production" / "records.jsonl"

    memory_root = dest_dir / "memory"
    memory_paths: dict[str, Path] = {}
    if memory_root.is_dir():
        for tier_dir in sorted(memory_root.iterdir()):
            if not tier_dir.is_dir():
                continue
            children = list(tier_dir.iterdir())
            if len(children) == 1:
                memory_paths[tier_dir.name] = children[0]
            else:
                memory_paths[tier_dir.name] = tier_dir

    return ImportResult(
        manifest=manifest,
        dest_dir=dest_dir,
        ledger_path=ledger_path if ledger_path.exists() else None,
        sandbox_records_path=sandbox_records if sandbox_records.exists() else None,
        sandbox_denied_emits_path=sandbox_denied if sandbox_denied.exists() else None,
        production_records_path=production if production.exists() else None,
        memory_paths=memory_paths,
    )


def load_jsonl(path: Path | str) -> list[dict[str, object]]:
    """Helper: JSONL を全行 dict として読み込む (importer 利用側で使う)."""
    out: list[dict[str, object]] = []
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


__all__ = [
    "ImportResult",
    "IncompatibleBundleError",
    "import_state",
    "load_jsonl",
]
