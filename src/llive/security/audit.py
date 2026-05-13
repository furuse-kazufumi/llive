"""Append-only audit trail with SHA-256 hash chain (SEC-03).

Every recorded action is hashed together with the previous entry's hash,
producing a tamper-evident log:

    entry_hash_i = SHA-256(prev_hash || ts || actor || action || payload_json)

The trail is persisted as a single SQLite database (one row per entry).
``verify_chain`` walks the table and confirms every hash matches; any
mismatch reports the first broken offset.

SQLite was picked over DuckDB for SEC-03 because:
* It is in the Python stdlib (no extra wheel) — eliminates a runtime
  dependency for security-critical code.
* The append-only insert pattern is trivial for sqlite3.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_GENESIS = "0" * 64


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _default_db_path() -> Path:
    base = os.environ.get("LLIVE_DATA_DIR") or "D:/data/llive"
    return Path(base) / "audit" / "trail.sqlite3"


@dataclass
class AuditEntry:
    """One immutable row in the audit trail."""

    seq: int
    ts: datetime
    actor: str
    action: str
    payload: dict[str, Any]
    prev_hash: str
    entry_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "ts": self.ts.isoformat(),
            "actor": self.actor,
            "action": self.action,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
        }


def _compute_hash(prev_hash: str, ts: str, actor: str, action: str, payload_json: str) -> str:
    h = hashlib.sha256()
    h.update(prev_hash.encode("utf-8"))
    h.update(b"|")
    h.update(ts.encode("utf-8"))
    h.update(b"|")
    h.update(actor.encode("utf-8"))
    h.update(b"|")
    h.update(action.encode("utf-8"))
    h.update(b"|")
    h.update(payload_json.encode("utf-8"))
    return h.hexdigest()


@dataclass
class _ChainVerificationResult:
    ok: bool
    broken_at_seq: int | None = None
    reason: str | None = None
    inspected: int = 0


class AuditTrail:
    """SQLite-backed append-only hash chain."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else _default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_trail (
                seq        INTEGER PRIMARY KEY AUTOINCREMENT,
                ts         TEXT NOT NULL,
                actor      TEXT NOT NULL,
                action     TEXT NOT NULL,
                payload    TEXT NOT NULL,
                prev_hash  TEXT NOT NULL,
                entry_hash TEXT NOT NULL UNIQUE
            )
            """
        )

    # -- writes ------------------------------------------------------------

    def append(self, actor: str, action: str, payload: dict[str, Any] | None = None) -> AuditEntry:
        with self._lock:
            row = self._conn.execute(
                "SELECT entry_hash FROM audit_trail ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            prev = row[0] if row else _GENESIS
            ts = _utcnow()
            payload = payload or {}
            payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            ts_str = ts.isoformat()
            entry_hash = _compute_hash(prev, ts_str, actor, action, payload_json)
            cur = self._conn.execute(
                "INSERT INTO audit_trail (ts, actor, action, payload, prev_hash, entry_hash) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (ts_str, actor, action, payload_json, prev, entry_hash),
            )
            seq = cur.lastrowid
        return AuditEntry(
            seq=int(seq),
            ts=ts,
            actor=actor,
            action=action,
            payload=payload,
            prev_hash=prev,
            entry_hash=entry_hash,
        )

    # -- reads -------------------------------------------------------------

    def count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM audit_trail").fetchone()
        return int(row[0])

    def list(self, *, since_seq: int = 0, limit: int = 100) -> list[AuditEntry]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT seq, ts, actor, action, payload, prev_hash, entry_hash "
                "FROM audit_trail WHERE seq > ? ORDER BY seq ASC LIMIT ?",
                (since_seq, limit),
            ).fetchall()
        return [_row_to_entry(r) for r in rows]

    def head(self) -> AuditEntry | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT seq, ts, actor, action, payload, prev_hash, entry_hash "
                "FROM audit_trail ORDER BY seq DESC LIMIT 1"
            ).fetchone()
        return _row_to_entry(row) if row else None

    def verify(self) -> _ChainVerificationResult:
        return verify_chain(self)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> AuditTrail:
        return self

    def __exit__(self, *a) -> None:
        self.close()


def _row_to_entry(row: tuple) -> AuditEntry:
    return AuditEntry(
        seq=int(row[0]),
        ts=datetime.fromisoformat(row[1]),
        actor=row[2],
        action=row[3],
        payload=json.loads(row[4]) if row[4] else {},
        prev_hash=row[5],
        entry_hash=row[6],
    )


def verify_chain(trail: AuditTrail) -> _ChainVerificationResult:
    """Walk the trail end-to-end; report the first broken row, if any."""
    prev = _GENESIS
    inspected = 0
    with trail._lock:
        rows = trail._conn.execute(
            "SELECT seq, ts, actor, action, payload, prev_hash, entry_hash "
            "FROM audit_trail ORDER BY seq ASC"
        ).fetchall()
    for row in rows:
        inspected += 1
        seq = int(row[0])
        ts_str = row[1]
        actor = row[2]
        action = row[3]
        payload_json = row[4]
        prev_hash = row[5]
        entry_hash = row[6]
        if prev_hash != prev:
            return _ChainVerificationResult(
                ok=False,
                broken_at_seq=seq,
                reason=f"prev_hash mismatch (expected {prev[:12]}…, got {prev_hash[:12]}…)",
                inspected=inspected,
            )
        recomputed = _compute_hash(prev_hash, ts_str, actor, action, payload_json)
        if recomputed != entry_hash:
            return _ChainVerificationResult(
                ok=False,
                broken_at_seq=seq,
                reason=f"entry_hash mismatch at seq {seq}",
                inspected=inspected,
            )
        prev = entry_hash
    return _ChainVerificationResult(ok=True, inspected=inspected)


__all__ = ["AuditEntry", "AuditTrail", "verify_chain"]
