"""Episodic memory (MEM-02) — DuckDB append-only time-series store."""

from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

from llive.memory.provenance import Provenance


def _default_db_path() -> Path:
    env = os.environ.get("LLIVE_DATA_DIR")
    if env:
        return Path(env) / "memory" / "episodic.duckdb"
    return Path("D:/data/llive/memory/episodic.duckdb")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class EpisodicEvent:
    content: str
    provenance: Provenance
    metadata: dict[str, Any] = field(default_factory=dict)
    ts: datetime = field(default_factory=_utcnow)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)


class EpisodicMemory:
    """Append-only DuckDB-backed event log with simple range/content queries."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else _default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = duckdb.connect(str(self.db_path))
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                event_id   TEXT PRIMARY KEY,
                ts         TIMESTAMP,
                content    TEXT,
                metadata   TEXT,
                provenance TEXT
            )
            """
        )

    def write(self, event: EpisodicEvent) -> str:
        with self._lock:
            self._conn.execute(
                "INSERT INTO events (event_id, ts, content, metadata, provenance) VALUES (?, ?, ?, ?, ?)",
                [
                    event.event_id,
                    event.ts,
                    event.content,
                    json.dumps(event.metadata),
                    event.provenance.to_json(),
                ],
            )
        return event.event_id

    def query_range(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[EpisodicEvent]:
        clauses: list[str] = []
        params: list[Any] = []
        if start is not None:
            clauses.append("ts >= ?")
            params.append(start)
        if end is not None:
            clauses.append("ts <= ?")
            params.append(end)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        query = f"SELECT event_id, ts, content, metadata, provenance FROM events {where} ORDER BY ts LIMIT ?"
        params.append(int(limit))
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_event(r) for r in rows]

    def query_recent(self, limit: int = 10) -> list[EpisodicEvent]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT event_id, ts, content, metadata, provenance FROM events ORDER BY ts DESC LIMIT ?",
                [int(limit)],
            ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def count(self) -> int:
        with self._lock:
            (n,) = self._conn.execute("SELECT COUNT(*) FROM events").fetchone()
        return int(n)

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM events")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "EpisodicMemory":
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    @staticmethod
    def _row_to_event(row: tuple) -> EpisodicEvent:
        event_id, ts, content, metadata_text, provenance_text = row
        metadata = json.loads(metadata_text) if metadata_text else {}
        provenance = Provenance.from_json(provenance_text)
        return EpisodicEvent(
            event_id=event_id,
            ts=ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts)),
            content=content,
            metadata=metadata,
            provenance=provenance,
        )
