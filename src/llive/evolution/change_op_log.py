# SPDX-License-Identifier: Apache-2.0
"""Real ChangeOp action-sequence logging (SPEC-MESH-01 → SPEC-MESH-07 prerequisite).

:mod:`llive.evolution.branch_predictor` measured ``hit_rate`` on **synthetic**
ChangeOp streams. The perf doc's open blocker
(``docs/perf_comparison/branch_predictor_hit_rate_2026_05_24.md`` §次ステップ 1) was
that *no running loop persisted the real ChangeOp sequence a live llive emits*, so
the synthetic figures could not be overwritten with measured ones. This module
closes that gap: it records the **action label** of every ChangeOp actually
materialised by ``apply_diff`` (e.g. inside
:meth:`llive.triz.self_reflection.SelfReflectionSession._verify`) to an append-only
JSONL ledger, and reads it back as the action stream that
:func:`llive.evolution.branch_predictor.evaluate_hit_rate` consumes.

It does **not** itself produce ``hit_rate`` numbers — that is
:mod:`llive.evolution.branch_predictor_real`. It only persists the ground-truth
sequence so a *real* measurement becomes possible once operational runs accumulate.

HONEST DISCLOSURE ([[feedback_benchmark_honest_disclosure]]): a single
self-reflection cycle emits a short burst of ChangeOps; a meaningful ``hit_rate``
needs many cycles concatenated chronologically. Until enough real records
accumulate, the synthetic figures remain the ceiling — **this module is the
mechanism, not the data**. ``applied`` marks whether the burst passed the static
gate, so a consumer can measure either the emitted or the promotable stream.
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from llive.evolution.change_op import (
    ChangeOp,
    InsertSubblock,
    RemoveSubblock,
    ReorderSubblocks,
    ReplaceSubblock,
)

# Concrete ChangeOp class -> Phase-1 action label. This inverts
# ``change_op.build_change_op`` (label -> instance) so logging is decoupled from
# the CandidateDiff dict shape and works straight off the materialised ops that
# ``apply_diff`` returns. Kept as plain strings, mirroring CHANGE_OP_ACTIONS.
_OP_ACTION: dict[type[ChangeOp], str] = {
    InsertSubblock: "insert_subblock",
    RemoveSubblock: "remove_subblock",
    ReplaceSubblock: "replace_subblock",
    ReorderSubblocks: "reorder_subblocks",
}

_ROW_KIND = "change_op_seq"


class ChangeOpLogError(Exception):
    """Raised when a ChangeOp instance cannot be mapped to a known action label."""


def op_action_label(op: ChangeOp) -> str:
    """Return the Phase-1 action label for a materialised :class:`ChangeOp`.

    Raises:
        ChangeOpLogError: if ``op`` is not one of the four Phase-1 ChangeOps.
    """
    label = _OP_ACTION.get(type(op))
    if label is None:
        raise ChangeOpLogError(f"no action label for ChangeOp type {type(op).__name__!r}")
    return label


def op_action_labels(ops: Iterable[ChangeOp]) -> list[str]:
    """Action labels for a sequence of materialised ChangeOps, preserving order."""
    return [op_action_label(op) for op in ops]


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class ChangeOpRecord:
    """One persisted ChangeOp burst — the ops of a single applied CandidateDiff."""

    ts: str
    source: str
    actions: tuple[str, ...]
    candidate_id: str | None = None
    container_id: str | None = None
    applied: bool = True  # True == passed the static gate (promotable)

    def to_json(self) -> dict[str, object]:
        return {
            "row": _ROW_KIND,
            "ts": self.ts,
            "source": self.source,
            "candidate_id": self.candidate_id,
            "container_id": self.container_id,
            "applied": self.applied,
            "actions": list(self.actions),
        }


class ChangeOpSequenceLog:
    """Append-only JSONL ledger of real ChangeOp action sequences.

    One row per materialised diff (a *burst* of one or more actions). Reading
    concatenates the bursts in write order — the chronological operational stream
    the branch predictor would speculate over. Designed to be threaded into any
    path that calls ``apply_diff`` (self-reflection, bench, a future multi-gen
    loop) so the real sequence accumulates wherever evolution actually runs.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    # -- writing -----------------------------------------------------------

    def record_ops(
        self,
        ops: Sequence[ChangeOp],
        *,
        source: str,
        candidate_id: str | None = None,
        container_id: str | None = None,
        applied: bool = True,
    ) -> ChangeOpRecord | None:
        """Map ops to action labels and append one JSONL row.

        Returns ``None`` without writing when ``ops`` is empty (an empty diff
        carries no branch to predict, so it would only pollute the stream).
        """
        if not ops:
            return None
        return self.record_actions(
            op_action_labels(ops),
            source=source,
            candidate_id=candidate_id,
            container_id=container_id,
            applied=applied,
        )

    def record_actions(
        self,
        actions: Sequence[str],
        *,
        source: str,
        candidate_id: str | None = None,
        container_id: str | None = None,
        applied: bool = True,
    ) -> ChangeOpRecord:
        rec = ChangeOpRecord(
            ts=_utcnow_iso(),
            source=source,
            actions=tuple(actions),
            candidate_id=candidate_id,
            container_id=container_id,
            applied=applied,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec.to_json(), ensure_ascii=False) + "\n")
        return rec

    # -- reading -----------------------------------------------------------

    def iter_records(self) -> Iterator[ChangeOpRecord]:
        """Yield every ChangeOp record in write order (skips foreign/blank rows)."""
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if obj.get("row") != _ROW_KIND:
                    continue
                yield ChangeOpRecord(
                    ts=obj.get("ts", ""),
                    source=obj.get("source", ""),
                    actions=tuple(obj.get("actions", ())),
                    candidate_id=obj.get("candidate_id"),
                    container_id=obj.get("container_id"),
                    applied=bool(obj.get("applied", True)),
                )

    def action_stream(self, *, applied_only: bool = True) -> list[str]:
        """Flatten all records into one chronological action stream.

        This is the realistic operational sequence: an origin emits ChangeOps
        back-to-back across cycles, so the seam between two records is a genuine
        operational transition (the origin really did emit them in this order),
        even though it is not a within-diff causal step — noted in the perf doc.

        With ``applied_only`` (default) only bursts that passed the static gate
        are included — the promotable stream a speculative executor would chase.
        """
        stream: list[str] = []
        for rec in self.iter_records():
            if applied_only and not rec.applied:
                continue
            stream.extend(rec.actions)
        return stream


__all__ = [
    "ChangeOpLogError",
    "ChangeOpRecord",
    "ChangeOpSequenceLog",
    "op_action_label",
    "op_action_labels",
]
