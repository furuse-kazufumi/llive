"""Wiki Contradiction Detector (LLW-04).

Scans :class:`ConceptPage` content for *internal* contradictions:

1. **Statement-level** — page's ``structured_fields["contradicts"]`` carries
   explicit annotations (list of ``{description, severity}`` dicts).
2. **Edge-level** — duplicate ``linked_concept_ids`` (same slug appears
   multiple times) imply the consolidation pass merged conflicting edges.
3. **Provenance-level** — ``provenance.derived_from`` contains the same
   source id more than once (a soft hint of conflicting evidence).

The detector is purely structural; LLM-based natural-language contradiction
detection is deferred to Phase 4 (LLW-07 HITL workflow). Its output feeds
into the :class:`Consolidator` so future cycles can choose merge / split
according to detected contradictions.
"""

from __future__ import annotations

import uuid
from collections import Counter
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
    """Same source id appearing multiple times in derived_from."""
    if page.provenance is None:
        return []
    derived = list(page.provenance.derived_from)
    if not derived:
        return []
    counts = Counter(derived)
    out: list[WikiContradiction] = []
    for src, n in counts.items():
        if n >= 2:
            out.append(
                WikiContradiction(
                    contradiction_id=f"wcon_{uuid.uuid4().hex[:10]}",
                    page_id=page.concept_id,
                    kind="provenance",
                    description=f"source {src!r} appears {n} times in derived_from",
                    severity=min(1.0, 0.3 + 0.2 * (n - 1)),
                    evidence={"source": src, "count": n},
                )
            )
    return out


def _edge_conflicts(page: ConceptPage) -> list[WikiContradiction]:
    """Duplicate slug in linked_concept_ids — a stale merge survives."""
    if not page.linked_concept_ids:
        return []
    counts = Counter(page.linked_concept_ids)
    out: list[WikiContradiction] = []
    for slug, n in counts.items():
        if n >= 2:
            out.append(
                WikiContradiction(
                    contradiction_id=f"wcon_{uuid.uuid4().hex[:10]}",
                    page_id=page.concept_id,
                    kind="edge",
                    description=f"linked_concept {slug!r} listed {n} times",
                    severity=min(1.0, 0.4 + 0.2 * (n - 1)),
                    evidence={"slug": slug, "count": n},
                )
            )
    return out


def _statement_conflicts(page: ConceptPage) -> list[WikiContradiction]:
    """Look for ``structured_fields['contradicts']`` annotations."""
    flags = page.structured_fields.get("contradicts") if page.structured_fields else None
    if not isinstance(flags, list):
        return []
    out: list[WikiContradiction] = []
    for flag in flags:
        if not isinstance(flag, dict):
            continue
        desc = str(flag.get("description", "explicit contradiction flag"))
        sev = float(flag.get("severity", 0.6))
        out.append(
            WikiContradiction(
                contradiction_id=f"wcon_{uuid.uuid4().hex[:10]}",
                page_id=page.concept_id,
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
