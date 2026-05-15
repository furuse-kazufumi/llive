"""SqliteLedger — Spec §AB1 (replayable) を再起動越しに永続化.

stdlib のみ (sqlite3 + json). DB スキーマは v1 で固定:
    requests(request_id PK, action, payload_json, principal, timeout_s, created_at)
    responses(id INTEGER PK AUTOINCREMENT, request_id, verdict, by, rationale, at)
    meta(key PK, value)  -- schema_version 等

`ApprovalBus(ledger=SqliteLedger(path))` で組合せ、起動時に pending / ledger を
復元する.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from llive.approval.bus import ApprovalRequest, ApprovalResponse, Verdict

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    request_id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    principal TEXT NOT NULL,
    timeout_s REAL NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL,
    verdict TEXT NOT NULL,
    by_principal TEXT NOT NULL,
    rationale TEXT NOT NULL,
    at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_responses_request ON responses(request_id);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class LedgerState:
    """ledger を読み込んだ後の復元状態."""

    requests: dict[str, ApprovalRequest]
    """すべての request (pending とは限らない)."""
    responses: list[ApprovalResponse]
    """time 順 (id ASC) で並んだ response 列."""


class SqliteLedger:
    """SQLite で response/request を永続化する ledger backend."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._set_meta("schema_version", str(SCHEMA_VERSION))

    # -- meta -------------------------------------------------------------

    def _set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def schema_version(self) -> int:
        row = self._conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        return int(row["value"]) if row else 0

    # -- write -----------------------------------------------------------

    def append_request(self, req: ApprovalRequest) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO requests"
            "(request_id, action, payload_json, principal, timeout_s, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                req.request_id,
                req.action,
                json.dumps(req.payload, sort_keys=True, default=str),
                req.principal,
                req.timeout_s,
                req.created_at,
            ),
        )

    def append_response(self, resp: ApprovalResponse) -> None:
        self._conn.execute(
            "INSERT INTO responses(request_id, verdict, by_principal, rationale, at) "
            "VALUES (?, ?, ?, ?, ?)",
            (resp.request_id, resp.verdict.value, resp.by, resp.rationale, resp.at),
        )

    # -- read ------------------------------------------------------------

    def load(self) -> LedgerState:
        req_rows = self._conn.execute(
            "SELECT request_id, action, payload_json, principal, timeout_s, created_at "
            "FROM requests"
        ).fetchall()
        requests: dict[str, ApprovalRequest] = {
            r["request_id"]: ApprovalRequest(
                request_id=r["request_id"],
                action=r["action"],
                payload=json.loads(r["payload_json"]),
                principal=r["principal"],
                timeout_s=float(r["timeout_s"]),
                created_at=float(r["created_at"]),
            )
            for r in req_rows
        }
        resp_rows = self._conn.execute(
            "SELECT request_id, verdict, by_principal, rationale, at "
            "FROM responses ORDER BY id ASC"
        ).fetchall()
        responses = [
            ApprovalResponse(
                request_id=r["request_id"],
                verdict=Verdict(r["verdict"]),
                by=r["by_principal"],
                rationale=r["rationale"],
                at=float(r["at"]),
            )
            for r in resp_rows
        ]
        return LedgerState(requests=requests, responses=responses)

    def iter_responses(self) -> Iterator[ApprovalResponse]:
        for r in self._conn.execute(
            "SELECT request_id, verdict, by_principal, rationale, at "
            "FROM responses ORDER BY id ASC"
        ):
            yield ApprovalResponse(
                request_id=r["request_id"],
                verdict=Verdict(r["verdict"]),
                by=r["by_principal"],
                rationale=r["rationale"],
                at=float(r["at"]),
            )

    # -- lifecycle -------------------------------------------------------

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> SqliteLedger:
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()


__all__ = ["LedgerState", "SqliteLedger", "SCHEMA_VERSION"]
