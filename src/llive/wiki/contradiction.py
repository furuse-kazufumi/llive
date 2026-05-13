"""Wiki Contradiction Detector (LLW-04).

Scans :class:`ConceptPage` content for *internal* contradictions:

1. **Statement-level** — page contains two summary fragments that share
   key noun phrases but assert opposite facts (e.g. "X enables Y" vs
   "X prevents Y"). Phase 3 MVR detects this only via an explicit
   ``contradicts`` annotation in the page metadata.
2. **Edge-level** — two outgoing ``contradicts`` edges that ultimately
   resolve to the same destination concept.
3. **Provenance-level** — derived_from event chain references the same
   source twice with conflicting confidence values.

The detector is purely structural; LLM-based natural-language contradiction
detection is deferred to Phase 4 (LLW-07 HITL workflow). Its output feeds
into the :class:`Consolidator` so future cycles can choose merge / split
according to detected contradictions.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from llive.memory.concept import ConceptPage


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class WikiContradiction:
    contradiction_id: str
    page_id: str
    kind: str  # "statement" | "edge" | "provenance"
    description: str
    severity: float
    evidence: dict[str, Any] = field(default_factory=dict)
    detected_at: datetime = field(default_factory=_utcnow)


def _provenance_conflicts(page: ConceptPage) -> list[WikiContradiction]:
    """Find duplicate source_ids in provenance.derived_from with conflicting confidence."""
    out: list[WikiContradiction] = []
    derived = list(getattr(page.provenance, "derived_from", []) or [])
    seen: dict[str, float] = {}
    for entry in derived:
        if isinstance(entry, dict):
            src = entry.get("source_id") or entry.get("event_id")
            conf = float(entry.get("confidence", 1.0))
        else:
            src, conf = str(entry), 1.0
        if src is None:
            continue
        if src in seen and abs(seen[src] - conf) > 0.3:
            out.append(
                WikiContradiction(
                    contradiction_id=f"wcon_{uuid.uuid4().hex[:10]}",
                    page_id=page.page_id,
                    kind="provenance",
                    description=(
                        f"source {src!r} appears with conflicting confidence "
                        f"({seen[src]:.2f} vs {conf:.2f})"
                    ),
                    severity=min(1.0, abs(seen[src] - conf)),
                    evidence={"source": src, "values": [seen[src], conf]},
                )
            )
        else:
            seen[src] = conf
    return out


def _edge_conflicts(page: ConceptPage) -> list[WikiContradiction]:
    """Two ``contradicts`` edges resolving to the same destination concept."""
    out: list[WikiContradiction] = []
    dests: dict[str, int] = {}
    for edge in getattr(page, "linked_concepts", []) or []:
        if isinstance(edge, dict):
            rel = edge.get("rel_type", "linked_concept")
            dst = edge.get("concept_id") or edge.get("dst")
        else:
            rel = getattr(edge, "rel_type", "linked_concept")
            dst = getattr(edge, "concept_id", None) or getattr(edge, "dst", None)
        if rel != "contradicts" or dst is None:
            continue
        dests[dst] = dests.get(dst, 0) + 1
    for dst, n in dests.items():
        if n >= 2:
            out.append(
                WikiContradiction(
                    contradiction_id=f"wcon_{uuid.uuid4().hex[:10]}",
                    page_id=page.page_id,
                    kind="edge",
                    description=f"{n} contradicts edges resolve to {dst!r}",
                    severity=min(1.0, 0.4 + 0.2 * n),
                    evidence={"dst": dst, "count": n},
                )
            )
    return out


def _statement_conflicts(page: ConceptPage) -> list[WikiContradiction]:
    """Look for explicit ``contradicts`` block in optional page metadata."""
    extra = getattr(page, "extra", None) or getattr(page, "metadata", None) or {}
    if not isinstance(extra, dict):
        return []
    flags = extra.get("contradicts") or []
    out: list[WikiContradiction] = []
    if isinstance(flags, list):
        for flag in flags:
            if not isinstance(flag, dict):
                continue
            desc = str(flag.get("description", "explicit contradiction flag"))
            sev = float(flag.get("severity", 0.6))
            out.append(
                WikiContradiction(
                    contradiction_id=f"wcon_{uuid.uuid4().hex[:10]}",
                    page_id=page.page_id,
                    kind="statement",
                    description=desc,
                    severity=min(1.0, max(0.0, sev)),
                    evidence={"raw": flag},
                )
            )
    return out


def detect_wiki_contradictions(page: ConceptPage) -> list[WikiContradiction]:
    """Run all detectors against a single ConceptPage; sort by severity DESC."""
    out: list[WikiContradiction] = []
    out.extend(_provenance_conflicts(page))
    out.extend(_edge_conflicts(page))
    out.extend(_statement_conflicts(page))
    out.sort(key=lambda c: -c.severity)
    return out


__all__ = ["WikiContradiction", "detect_wiki_contradictions"]
