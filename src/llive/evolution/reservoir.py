"""Failed-Candidate Reservoir (EVO-06).

Stores rejected / failed CandidateDiff results so future mutation policies can
learn from the failures. Backed by DuckDB to share the columnar store with
:class:`EpisodicMemory`, but kept in a separate table (``failed_candidates``)
to preserve query patterns and minimise contention.

Schema::

    failed_candidates(
        candidate_id     VARCHAR PRIMARY KEY,
        rejected_at      TIMESTAMP NOT NULL,
        reason           VARCHAR NOT NULL,         -- verifier|bench|hitl|reverse_evo
        rejector         VARCHAR NOT NULL,         -- subsystem id
        diff             JSON NOT NULL,            -- CandidateDiff dump
        score_bundle     JSON,                     -- bench metrics if available
        mutation_policy  VARCHAR,                  -- e.g. triz_inspired
        contradiction_id VARCHAR,                  -- LLW-AC link
        notes            VARCHAR
    )

The reservoir is **append-only**: nothing is ever updated or deleted by the
public API. Pruning is offered separately to bound disk usage.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _default_db_path() -> Path:
    base = os.environ.get("LLIVE_DATA_DIR") or "D:/data/llive"
    return Path(base) / "reservoir.duckdb"


_VALID_REASONS: frozenset[str] = frozenset({"verifier", "bench", "hitl", "reverse_evo", "other"})


@dataclass
class FailedCandidate:
    candidate_id: str
    rejected_at: datetime
    reason: str
    rejector: str
    diff: dict[str, Any]
    score_bundle: dict[str, Any] | None = None
    mutation_policy: str | None = None
    contradiction_id: str | None = None
    notes: str | None = None

    @classmethod
    def new(
        cls,
        diff: dict[str, Any],
        *,
        reason: str,
        rejector: str,
        mutation_policy: str | None = None,
        score_bundle: dict[str, Any] | None = None,
        contradiction_id: str | None = None,
        notes: str | None = None,
        candidate_id: str | None = None,
    ) -> FailedCandidate:
        if reason not in _VALID_REASONS:
            raise ValueError(f"unknown rejection reason: {reason!r}")
        return cls(
            candidate_id=candidate_id or f"failed_{uuid.uuid4().hex[:12]}",
            rejected_at=_utcnow(),
            reason=reason,
            rejector=rejector,
            diff=dict(diff),
            score_bundle=dict(score_bundle) if score_bundle else None,
            mutation_policy=mutation_policy,
            contradiction_id=contradiction_id,
            notes=notes,
        )

    def to_row(self) -> dict[str, Any]:
        d = asdict(self)
        d["diff"] = json.dumps(d["diff"], ensure_ascii=False, sort_keys=True)
        if d["score_bundle"] is not None:
            d["score_bundle"] = json.dumps(d["score_bundle"], ensure_ascii=False, sort_keys=True)
        return d


@dataclass
class ReservoirSummary:
    count: int = 0
    by_reason: dict[str, int] = field(default_factory=dict)
    by_policy: dict[str, int] = field(default_factory=dict)
    oldest: datetime | None = None
    newest: datetime | None = None


class FailedCandidateReservoir:
    """Append-only DuckDB table of rejected candidates."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else _default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = duckdb.connect(str(self.db_path))
        self._conn.execute(
            """
            CREATE SEQUENCE IF NOT EXISTS failed_candidates_seq START 1;
            CREATE TABLE IF NOT EXISTS failed_candidates (
                seq              BIGINT DEFAULT nextval('failed_candidates_seq'),
                candidate_id     VARCHAR PRIMARY KEY,
                rejected_at      TIMESTAMP NOT NULL,
                reason           VARCHAR NOT NULL,
                rejector         VARCHAR NOT NULL,
                diff             VARCHAR NOT NULL,
                score_bundle     VARCHAR,
                mutation_policy  VARCHAR,
                contradiction_id VARCHAR,
                notes            VARCHAR
            )
            """
        )

    # -- public API --------------------------------------------------------

    def record(self, fc: FailedCandidate) -> None:
        row = fc.to_row()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO failed_candidates
                (candidate_id, rejected_at, reason, rejector, diff, score_bundle,
                 mutation_policy, contradiction_id, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    row["candidate_id"],
                    row["rejected_at"],
                    row["reason"],
                    row["rejector"],
                    row["diff"],
                    row["score_bundle"],
                    row["mutation_policy"],
                    row["contradiction_id"],
                    row["notes"],
                ],
            )

    def count(self, *, reason: str | None = None) -> int:
        sql = "SELECT COUNT(*) FROM failed_candidates"
        args: list[Any] = []
        if reason is not None:
            sql += " WHERE reason = ?"
            args.append(reason)
        with self._lock:
            return int(self._conn.execute(sql, args).fetchone()[0])

    def list(
        self,
        *,
        reason: str | None = None,
        mutation_policy: str | None = None,
        limit: int = 100,
    ) -> list[FailedCandidate]:
        conds: list[str] = []
        args: list[Any] = []
        if reason is not None:
            conds.append("reason = ?")
            args.append(reason)
        if mutation_policy is not None:
            conds.append("mutation_policy = ?")
            args.append(mutation_policy)
        where = (" WHERE " + " AND ".join(conds)) if conds else ""
        sql = (
            "SELECT candidate_id, rejected_at, reason, rejector, diff, score_bundle, "
            "mutation_policy, contradiction_id, notes "
            f"FROM failed_candidates{where} ORDER BY rejected_at DESC LIMIT ?"
        )
        args.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [_row_to_obj(r) for r in rows]

    def summary(self) -> ReservoirSummary:
        with self._lock:
            cnt = int(self._conn.execute("SELECT COUNT(*) FROM failed_candidates").fetchone()[0])
            by_r = self._conn.execute(
                "SELECT reason, COUNT(*) FROM failed_candidates GROUP BY reason"
            ).fetchall()
            by_p = self._conn.execute(
                "SELECT mutation_policy, COUNT(*) FROM failed_candidates "
                "WHERE mutation_policy IS NOT NULL GROUP BY mutation_policy"
            ).fetchall()
            range_row = self._conn.execute(
                "SELECT MIN(rejected_at), MAX(rejected_at) FROM failed_candidates"
            ).fetchone()
        return ReservoirSummary(
            count=cnt,
            by_reason={r[0]: int(r[1]) for r in by_r},
            by_policy={r[0]: int(r[1]) for r in by_p},
            oldest=range_row[0] if range_row else None,
            newest=range_row[1] if range_row else None,
        )

    def sample(self, *, k: int = 5, mutation_policy: str | None = None) -> list[FailedCandidate]:
        """Random sample for mutation-policy learning."""
        conds: list[str] = []
        args: list[Any] = []
        if mutation_policy is not None:
            conds.append("mutation_policy = ?")
            args.append(mutation_policy)
        where = (" WHERE " + " AND ".join(conds)) if conds else ""
        sql = (
            "SELECT candidate_id, rejected_at, reason, rejector, diff, score_bundle, "
            "mutation_policy, contradiction_id, notes "
            f"FROM failed_candidates{where} USING SAMPLE ?"
        )
        args.append(int(k))
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [_row_to_obj(r) for r in rows]

    def prune(self, *, keep_last: int) -> int:
        """Delete all but the most recent ``keep_last`` rows. Returns deleted count."""
        if keep_last < 0:
            raise ValueError("keep_last must be >= 0")
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM failed_candidates").fetchone()
            total = int(row[0])
            if total <= keep_last:
                return 0
            cutoff_row = self._conn.execute(
                "SELECT rejected_at FROM failed_candidates ORDER BY rejected_at DESC "
                "LIMIT 1 OFFSET ?",
                [keep_last - 1] if keep_last > 0 else [0],
            ).fetchone()
            if cutoff_row is None:
                return 0
            cutoff = cutoff_row[0]
            if keep_last == 0:
                # delete everything
                self._conn.execute("DELETE FROM failed_candidates")
                return total
            self._conn.execute("DELETE FROM failed_candidates WHERE rejected_at < ?", [cutoff])
            remaining = int(
                self._conn.execute("SELECT COUNT(*) FROM failed_candidates").fetchone()[0]
            )
            return total - remaining

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # context-manager friendliness
    def __enter__(self) -> FailedCandidateReservoir:
        return self

    def __exit__(self, *a) -> None:
        self.close()

    def __iter__(self) -> Iterable[FailedCandidate]:
        return iter(self.list(limit=10_000))


def _row_to_obj(row: tuple) -> FailedCandidate:
    return FailedCandidate(
        candidate_id=row[0],
        rejected_at=row[1] if isinstance(row[1], datetime) else _utcnow(),
        reason=row[2],
        rejector=row[3],
        diff=json.loads(row[4]),
        score_bundle=json.loads(row[5]) if row[5] else None,
        mutation_policy=row[6],
        contradiction_id=row[7],
        notes=row[8],
    )


__all__ = [
    "FailedCandidate",
    "FailedCandidateReservoir",
    "ReservoirSummary",
]
