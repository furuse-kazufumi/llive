# SPDX-License-Identifier: Apache-2.0
"""Brief-specific ledger — append-only JSONL with replay-friendly records.

The ledger captures every state transition a Brief goes through:

* ``brief_submitted`` — the parsed Brief that arrived
* ``stage_recorded`` — one per FullSense loop stage diagnostic
* ``decision`` — the loop's ActionPlan
* ``approval_requested`` / ``approval_resolved`` — Approval Bus events
* ``tool_invoked`` — one per whitelist-passed tool call (Step 5)
* ``outcome`` — terminal :class:`BriefResult`

The SIL (Synthetic Information Layer) axis depends on this ledger being
reproducible: replaying the lines in order MUST yield the same
:class:`BriefResult`. We deliberately do *not* embed timestamps inside
the record's identifying fields — they live in a side ``meta`` envelope
that replay can ignore.

JSONL keeps the format trivially diff-able and tail-able from the CLI;
the C-1 SQLite ledger ( :mod:`llive.approval.ledger` ) is heavier-weight
and tightly coupled to the Approval Bus contract, so reusing it here
would bleed approval semantics into the generic Brief audit log.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping


@dataclass(frozen=True)
class LedgerRecord:
    """A single ledger entry — type tag + payload + replay-irrelevant meta."""

    event: str
    payload: dict[str, Any]
    meta: dict[str, Any]


class BriefLedger:
    """Append-only JSONL ledger for a Brief run.

    Multiple :class:`BriefRunner` instances may share a single ledger file
    (one ledger per ``brief_id`` is the common case). Concurrent writers
    are serialised by a process-local lock; cross-process safety is out of
    scope for v0.7.0 (the operator runs one runner at a time).
    """

    _ENCODING = "utf-8"

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._count = 0

    @property
    def entries_written(self) -> int:
        """How many records this instance has appended."""
        return self._count

    def append(self, event: str, payload: Mapping[str, Any]) -> LedgerRecord:
        """Append a single record. Returns the record as written."""
        record = LedgerRecord(
            event=str(event),
            payload=dict(payload),
            meta={
                "ts": time.time(),
                "pid": os.getpid(),
            },
        )
        line = json.dumps(
            {"event": record.event, "payload": record.payload, "meta": record.meta},
            ensure_ascii=False,
            sort_keys=True,
        )
        with self._lock:
            with self.path.open("a", encoding=self._ENCODING) as fh:
                fh.write(line + "\n")
            self._count += 1
        return record

    def read(self) -> Iterator[LedgerRecord]:
        """Yield every record in append order. Useful for replay/inspection."""
        if not self.path.is_file():
            return
        with self.path.open("r", encoding=self._ENCODING) as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                obj = json.loads(raw)
                yield LedgerRecord(
                    event=obj["event"],
                    payload=obj.get("payload", {}),
                    meta=obj.get("meta", {}),
                )


def default_ledger_path(brief_id: str, root: Path | None = None) -> Path:
    """Resolve the default ledger location for a given ``brief_id``.

    Order: ``LLIVE_BRIEF_LEDGER_DIR`` env → ``LLIVE_DATA_DIR/briefs`` env →
    ``~/.llive/briefs``. The ``brief_id`` is used as the file stem; it was
    already validated to be a safe path segment by
    :class:`~llive.brief.types.Brief`.
    """
    if root is not None:
        base = Path(root)
    elif "LLIVE_BRIEF_LEDGER_DIR" in os.environ:
        base = Path(os.environ["LLIVE_BRIEF_LEDGER_DIR"])
    elif "LLIVE_DATA_DIR" in os.environ:
        base = Path(os.environ["LLIVE_DATA_DIR"]) / "briefs"
    else:
        base = Path.home() / ".llive" / "briefs"
    return base / f"{brief_id}.jsonl"
