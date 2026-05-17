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

    # -- COG-03: trace graph -------------------------------------------------

    def trace_graph(self) -> "TraceGraph":
        """Build the 3-layer trace graph (evidence / tool / decision).

        Each chain is an ordered list of nodes; nodes carry just enough
        identifiers for an auditor to follow the link back to the original
        ledger row. Designed as a *view* — no state is materialised on disk
        beyond the JSONL itself.

        * **evidence_chain**: TRIZ citations + RAD doc_paths + calculations
          that grounded the Brief
        * **tool_chain**: tool_invoked / tool_rejected / tool_failed events
        * **decision_chain**: decision event + approval verdict + outcome
        """
        evidence: list[dict[str, Any]] = []
        tools: list[dict[str, Any]] = []
        decisions: list[dict[str, Any]] = []
        for r in self.read():
            if r.event == "grounding_applied":
                p = r.payload
                for t in p.get("triz", []) or []:
                    evidence.append({"kind": "triz", **t})
                for c in p.get("rad", []) or []:
                    evidence.append({"kind": "rad", **c})
                for c in p.get("calc", []) or []:
                    evidence.append({"kind": "calc", **c})
            elif r.event == "math_verified":
                # MATH-02 — Sympy/Z3 deterministic check that backed the Brief's
                # math claim. Recorded with verdict + solver so auditors can
                # tell apart "equivalent under sympy" vs "z3-valid implication".
                # ``payload["kind"]`` is equivalence/implication/satisfiability —
                # preserve it as ``check_kind`` and use the evidence chain's own
                # ``kind`` slot to tag this as a math-style citation.
                entry = dict(r.payload)
                entry["check_kind"] = entry.pop("kind", "")
                entry["kind"] = "math"
                evidence.append(entry)
            elif r.event == "oka_essence_extracted":
                # OKA-01/02 — core essence as evidence backing the Brief's framing.
                evidence.append({"kind": "oka_essence", **r.payload})
            elif r.event == "oka_notebook_appended":
                # OKA-04 — reflective note (intermediate / failed_attempt / insight /
                # open_question / reframing). Preserves the note kind as note_kind
                # so the evidence-chain ``kind`` slot can stay "oka_note".
                entry = dict(r.payload)
                entry["note_kind"] = entry.pop("kind", "")
                entry["kind"] = "oka_note"
                evidence.append(entry)
            elif r.event == "lint_findings_recorded":
                # VRB-02 — promptlint hits land as evidence so audit can see
                # "this Brief was reviewed at submission time and yielded N hits".
                evidence.append({"kind": "lint", **r.payload})
            elif r.event == "premortem_generated":
                # VRB-04 — formal failure scenarios. Marked as evidence so the
                # audit trail shows the Brief was pre-mortem'd before action.
                evidence.append({"kind": "premortem", **r.payload})
            elif r.event == "eval_spec_evaluated":
                # VRB-05 — formal eval outcome. Decision-chain because it's a
                # judgement about the Brief (pass / fail / stop), not raw
                # evidence material.
                decisions.append({"event": r.event, **r.payload})
            elif r.event in {"tool_invoked", "tool_rejected", "tool_failed"}:
                tools.append({"event": r.event, **r.payload})
            elif r.event in {"decision", "approval_requested", "approval_resolved", "outcome", "governance_scored", "oka_strategy_switched"}:
                # OKA-03 — strategy switches are decision-level audit events
                # (a switch is a meta-decision about how to proceed).
                decisions.append({"event": r.event, **r.payload})
        return TraceGraph(
            evidence_chain=tuple(evidence),
            tool_chain=tuple(tools),
            decision_chain=tuple(decisions),
        )


@dataclass(frozen=True)
class TraceGraph:
    """COG-03 — 3-layer view over a BriefLedger.

    Each chain is a tuple of dicts so the view is hashable and safe to
    persist (e.g. for cross-Brief comparisons or evolution learning data).
    """

    evidence_chain: tuple[dict[str, Any], ...] = ()
    tool_chain: tuple[dict[str, Any], ...] = ()
    decision_chain: tuple[dict[str, Any], ...] = ()

    @property
    def is_empty(self) -> bool:
        return not (self.evidence_chain or self.tool_chain or self.decision_chain)


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
