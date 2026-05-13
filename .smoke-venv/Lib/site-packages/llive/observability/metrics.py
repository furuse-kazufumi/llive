"""Phase 1 basic metrics (OBS-02) — stored in DuckDB for cross-run analysis."""

from __future__ import annotations

import math
import os
import threading
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb


def compute_route_entropy(counts: dict[str, int] | Iterable[str]) -> float:
    """Shannon entropy (bits) of route selection. Empty → 0.0."""
    if isinstance(counts, dict):
        c = dict(counts)
    else:
        c = {}
        for item in counts:
            c[item] = c.get(item, 0) + 1
    total = sum(c.values())
    if total == 0:
        return 0.0
    entropy = 0.0
    for n in c.values():
        if n == 0:
            continue
        p = n / total
        entropy -= p * math.log2(p)
    return float(entropy)


def _default_db_path() -> Path:
    base = os.environ.get("LLIVE_DATA_DIR") or "D:/data/llive"
    return Path(base) / "metrics.duckdb"


class MetricsStore:
    """Append-only DuckDB store for run-level metrics."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else _default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = duckdb.connect(str(self.db_path))
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metrics (
                ts      TIMESTAMP,
                run_id  TEXT,
                key     TEXT,
                value   DOUBLE
            )
            """
        )

    def record(self, run_id: str, key: str, value: float, ts: datetime | None = None) -> None:
        when = ts or datetime.now(UTC)
        with self._lock:
            self._conn.execute(
                "INSERT INTO metrics (ts, run_id, key, value) VALUES (?, ?, ?, ?)",
                [when, run_id, key, float(value)],
            )

    def record_many(self, run_id: str, items: dict[str, float], ts: datetime | None = None) -> None:
        when = ts or datetime.now(UTC)
        with self._lock:
            self._conn.executemany(
                "INSERT INTO metrics (ts, run_id, key, value) VALUES (?, ?, ?, ?)",
                [(when, run_id, k, float(v)) for k, v in items.items()],
            )

    def query(self, run_id: str | None = None) -> list[dict[str, Any]]:
        if run_id:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT ts, run_id, key, value FROM metrics WHERE run_id = ? ORDER BY ts",
                    [run_id],
                ).fetchall()
        else:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT ts, run_id, key, value FROM metrics ORDER BY ts"
                ).fetchall()
        return [
            {"ts": r[0], "run_id": r[1], "key": r[2], "value": float(r[3])} for r in rows
        ]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


__all__ = ["MetricsStore", "compute_route_entropy"]
