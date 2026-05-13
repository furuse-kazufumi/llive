"""Parameter memory (MEM-06) — AdapterProfile store.

Filesystem + DuckDB hybrid:

- Adapter weight files: ``<data_dir>/parameter/<adapter_id>.safetensors``
- Index table:           ``<data_dir>/memory/parameter_index.duckdb``

Real LoRA loading is delegated to HuggingFace PEFT (optional extra
``llmesh-llive[torch]``). In Phase 2 the store happily registers adapters
authored with any format-tag and verifies SHA-256 — actually attaching them
to a model is the caller's responsibility.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb
from pydantic import BaseModel, ConfigDict, Field

from llive.memory.provenance import Provenance


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _default_data_dir() -> Path:
    base = os.environ.get("LLIVE_DATA_DIR") or "D:/data/llive"
    return Path(base) / "memory" / "parameter"


def _default_index_path() -> Path:
    base = os.environ.get("LLIVE_DATA_DIR") or "D:/data/llive"
    return Path(base) / "memory" / "parameter_index.duckdb"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class AdapterProfile(BaseModel):
    """Metadata describing one adapter (LoRA/IA3/prefix/etc.)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    name: str
    base_model: str  # e.g., "Qwen/Qwen2.5-0.5B"
    format: str  # "lora" | "ia3" | "prefix" | "state_dict"
    adapter_size_mb: float = 0.0
    target_modules: list[str] = Field(default_factory=list)
    alpha: float | None = None
    dropout: float | None = None
    tags: list[str] = Field(default_factory=list)
    provenance: Provenance | None = None
    sha256: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


@dataclass
class AdapterRecord:
    profile: AdapterProfile
    weight_path: Path
    active: bool = False


class AdapterStore:
    """Register / load / activate adapters; verify integrity via SHA-256."""

    def __init__(
        self,
        data_dir: Path | str | None = None,
        index_path: Path | str | None = None,
    ) -> None:
        self.data_dir = Path(data_dir) if data_dir else _default_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = Path(index_path) if index_path else _default_index_path()
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = duckdb.connect(str(self.index_path))
        self._active: set[str] = set()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS adapter_index (
                adapter_id     TEXT PRIMARY KEY,
                name           TEXT,
                base_model     TEXT,
                format         TEXT,
                adapter_size_mb DOUBLE,
                tags           TEXT,
                sha256         TEXT,
                profile_json   TEXT,
                weight_path    TEXT,
                created_at     TIMESTAMP
            )
            """
        )

    # -- registration / removal --------------------------------------------

    def register(
        self,
        weight_path: Path | str,
        profile: AdapterProfile,
        copy_into_store: bool = True,
    ) -> AdapterProfile:
        src = Path(weight_path)
        if not src.exists():
            raise FileNotFoundError(f"adapter weight not found: {src}")
        if copy_into_store:
            dst = self.data_dir / f"{profile.id}{src.suffix or '.safetensors'}"
            shutil.copy2(src, dst)
            stored = dst
        else:
            stored = src
        profile.sha256 = _sha256(stored)
        profile.adapter_size_mb = stored.stat().st_size / (1024 * 1024)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO adapter_index "
                "(adapter_id, name, base_model, format, adapter_size_mb, tags, sha256, profile_json, weight_path, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    profile.id,
                    profile.name,
                    profile.base_model,
                    profile.format,
                    float(profile.adapter_size_mb),
                    json.dumps(profile.tags),
                    profile.sha256,
                    profile.model_dump_json(),
                    str(stored),
                    profile.created_at,
                ],
            )
        return profile

    def remove(self, adapter_id: str, delete_weights: bool = False) -> None:
        with self._lock:
            row = self._conn.execute(
                "SELECT weight_path FROM adapter_index WHERE adapter_id = ?",
                [adapter_id],
            ).fetchone()
            if row is None:
                return
            self._conn.execute("DELETE FROM adapter_index WHERE adapter_id = ?", [adapter_id])
        if delete_weights:
            path = Path(row[0])
            if path.exists():
                path.unlink()
        self._active.discard(adapter_id)

    # -- lookup ------------------------------------------------------------

    def list(self) -> list[AdapterRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT profile_json, weight_path FROM adapter_index ORDER BY created_at"
            ).fetchall()
        out: list[AdapterRecord] = []
        for row in rows:
            profile = AdapterProfile.model_validate_json(row[0])
            out.append(
                AdapterRecord(profile=profile, weight_path=Path(row[1]), active=profile.id in self._active)
            )
        return out

    def get(self, adapter_id: str) -> AdapterRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT profile_json, weight_path FROM adapter_index WHERE adapter_id = ?",
                [adapter_id],
            ).fetchone()
        if row is None:
            return None
        profile = AdapterProfile.model_validate_json(row[0])
        return AdapterRecord(
            profile=profile, weight_path=Path(row[1]), active=adapter_id in self._active
        )

    def verify_sha256(self, adapter_id: str) -> bool:
        record = self.get(adapter_id)
        if record is None:
            return False
        if not record.weight_path.exists():
            return False
        actual = _sha256(record.weight_path)
        return actual == record.profile.sha256

    # -- activation --------------------------------------------------------

    def activate(self, adapter_id: str) -> AdapterRecord:
        record = self.get(adapter_id)
        if record is None:
            raise KeyError(f"unknown adapter {adapter_id!r}")
        if not self.verify_sha256(adapter_id):
            raise RuntimeError(f"adapter {adapter_id!r} failed integrity check")
        self._active.add(adapter_id)
        record.active = True
        return record

    def deactivate(self, adapter_id: str) -> None:
        self._active.discard(adapter_id)

    @property
    def active_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._active))

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        with self._lock:
            self._conn.close()
