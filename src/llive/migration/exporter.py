# SPDX-License-Identifier: Apache-2.0
"""Export current agent state into a portable tar.gz bundle (§MI1)."""

from __future__ import annotations

import json
import platform
import shutil
import socket
import sys
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from llive.migration.bundle import MANIFEST_FILENAME, SCHEMA_VERSION, Bundle, BundleManifest


def _current_substrate() -> dict[str, str]:
    """Substrate metadata を採取 (digital classical 系の場合)."""
    return {
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "machine": platform.machine(),
        "hostname": socket.gethostname(),
    }


def _llive_version() -> str:
    try:
        from importlib.metadata import version

        return version("llmesh-llive")
    except Exception:
        return "unknown"


def _dump_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _serialise_sandbox_records(sandbox: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in sandbox.records():
        rows.append(
            {
                "kind": "sandbox_record",
                "recorded_at": rec.recorded_at,
                "stim_id": rec.stim.stim_id,
                "stim_content": rec.stim.content,
                "stim_source": rec.stim.source,
                "stim_surprise": rec.stim.surprise,
                "plan_decision": rec.plan.decision.value,
                "plan_rationale": rec.plan.rationale,
            }
        )
    return rows


def _serialise_sandbox_denied(sandbox: Any) -> list[dict[str, Any]]:
    recorder = getattr(sandbox, "denied_emits", None)
    if recorder is None:
        return []
    rows = []
    for entry in recorder():
        rows.append({"kind": "denied_emit", **entry})
    return rows


def _serialise_production_records(production_bus: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in production_bus.records():
        rows.append(
            {
                "kind": "production_record",
                "action": rec.action,
                "payload": rec.payload,
                "verdict": rec.verdict.value,
                "request_id": rec.request_id,
                "side_effect_executed": rec.side_effect_executed,
                "rationale": rec.rationale,
                "error_repr": rec.error_repr,
                "at": rec.at,
            }
        )
    return rows


def export_state(
    *,
    ledger_path: Path | str | None = None,
    sandbox: Any | None = None,
    production_bus: Any | None = None,
    out_path: Path | str,
) -> Bundle:
    """現在の agent state を tar.gz bundle に書き出す.

    Args:
        ledger_path: SqliteLedger DB path. None なら approval state はスキップ.
        sandbox: SandboxOutputBus. None なら sandbox state はスキップ.
        production_bus: ProductionOutputBus. None なら production state はスキップ.
        out_path: 出力 .tar.gz path (拡張子不問だが慣例として .tar.gz)

    Returns:
        Bundle (path + manifest).
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    components: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)

        if ledger_path is not None:
            src = Path(ledger_path)
            if src.exists():
                dest = stage / "approval" / "ledger.db"
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                components.append("approval")

        if sandbox is not None:
            records = _serialise_sandbox_records(sandbox)
            denied = _serialise_sandbox_denied(sandbox)
            if records:
                _dump_jsonl(stage / "sandbox" / "records.jsonl", records)
            if denied:
                _dump_jsonl(stage / "sandbox" / "denied_emits.jsonl", denied)
            if records or denied:
                components.append("sandbox")

        if production_bus is not None:
            rows = _serialise_production_records(production_bus)
            if rows:
                _dump_jsonl(stage / "production" / "records.jsonl", rows)
                components.append("production")

        manifest = BundleManifest(
            schema_version=SCHEMA_VERSION,
            llive_version=_llive_version(),
            source_substrate=_current_substrate(),
            exported_at=datetime.now(UTC).isoformat(timespec="seconds"),
            components=components,
        )
        (stage / MANIFEST_FILENAME).write_text(manifest.to_json(), encoding="utf-8")

        with tarfile.open(out_path, "w:gz") as tar:
            for child in sorted(stage.rglob("*")):
                if child.is_file():
                    tar.add(child, arcname=str(child.relative_to(stage)))

    return Bundle(path=out_path, manifest=manifest)


__all__ = ["export_state"]
