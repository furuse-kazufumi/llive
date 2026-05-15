# SPDX-License-Identifier: Apache-2.0
"""Self-Reflection mode (TRIZ-07).

Top-level orchestrator that ties together:

* :class:`ContradictionDetector` (TRIZ-02)
* :func:`map_contradiction`         (TRIZ-03)
* :class:`RadBackedIdeaGenerator`   (TRIZ-04)
* :func:`verify_diff` static gate   (EVO-04)
* :class:`FailedCandidateReservoir` (EVO-06)

One ``SelfReflectionSession.run_once(samples, container)`` invocation
performs the entire FR-23 → FR-25 → static gate pipeline and returns a
list of :class:`Proposal` records suitable for llove HITL display.

The session never auto-promotes anything: failed verifications are spooled
to the reservoir, passing candidates are returned for manual approval.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from llive.evolution.change_op import apply_diff
from llive.evolution.reservoir import FailedCandidate, FailedCandidateReservoir
from llive.evolution.verifier import Invariants, VerificationResult, verify_diff
from llive.schema.models import CandidateDiff, ContainerSpec
from llive.triz.contradiction import Contradiction, ContradictionDetector, MetricSpec
from llive.triz.principle_mapper import MappingResult, map_contradiction
from llive.triz.rad_generator import GeneratedCandidate, RadBackedIdeaGenerator


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class Proposal:
    """One concrete idea ready for HITL review."""

    proposal_id: str
    contradiction: Contradiction
    mapping: MappingResult
    candidate: GeneratedCandidate
    verification: VerificationResult
    accepted: bool  # True if static gate passed (HITL still must approve)
    notes: str | None = None
    created_at: datetime = field(default_factory=_utcnow)


@dataclass
class SessionSummary:
    session_id: str
    n_contradictions: int
    n_proposals: int
    n_passed: int
    n_failed: int
    duration_ms: float
    started_at: datetime
    finished_at: datetime


class SelfReflectionSession:
    """One-shot Self-Reflection driver. Re-instantiate per cycle."""

    def __init__(
        self,
        *,
        registry: dict[str, MetricSpec] | None = None,
        window: int = 100,
        min_samples: int = 8,
        top_k_principles: int = 2,
        reservoir: FailedCandidateReservoir | None = None,
        generator: RadBackedIdeaGenerator | None = None,
        invariants: Invariants | None = None,
        use_smt: bool = True,
    ) -> None:
        self.detector = ContradictionDetector(
            registry=registry, window=window, min_samples=min_samples
        )
        self.top_k_principles = int(top_k_principles)
        self.reservoir = reservoir
        self.generator = generator or RadBackedIdeaGenerator()
        self.invariants = invariants or Invariants()
        self.use_smt = bool(use_smt)

    # -- ingestion ---------------------------------------------------------

    def observe_many(self, samples: Iterable[dict[str, float]]) -> int:
        n = 0
        for s in samples:
            self.detector.observe_many(s)
            n += 1
        return n

    # -- main entry --------------------------------------------------------

    def run_once(
        self,
        container: ContainerSpec,
        *,
        max_contradictions: int = 5,
        notes: str | None = None,
    ) -> tuple[list[Proposal], SessionSummary]:
        session_id = f"reflect_{uuid.uuid4().hex[:10]}"
        started = _utcnow()
        contradictions = self.detector.detect()[: max(0, int(max_contradictions))]
        proposals: list[Proposal] = []
        n_pass = 0
        n_fail = 0
        for c in contradictions:
            mapping = map_contradiction(c, top_k=self.top_k_principles)
            for rec in mapping.recommendations:
                candidate = self.generator.generate(c, rec, container_id=container.container_id)
                verification = self._verify(container, candidate)
                proposals.append(
                    Proposal(
                        proposal_id=f"prop_{uuid.uuid4().hex[:10]}",
                        contradiction=c,
                        mapping=mapping,
                        candidate=candidate,
                        verification=verification,
                        accepted=verification.ok,
                        notes=notes,
                    )
                )
                if verification.ok:
                    n_pass += 1
                else:
                    n_fail += 1
                    self._spool_failure(candidate, verification)
        finished = _utcnow()
        summary = SessionSummary(
            session_id=session_id,
            n_contradictions=len(contradictions),
            n_proposals=len(proposals),
            n_passed=n_pass,
            n_failed=n_fail,
            duration_ms=(finished - started).total_seconds() * 1000.0,
            started_at=started,
            finished_at=finished,
        )
        return proposals, summary

    # -- internals ---------------------------------------------------------

    def _verify(
        self, container: ContainerSpec, candidate: GeneratedCandidate
    ) -> VerificationResult:
        try:
            diff = _coerce_candidate_diff(candidate.diff)
            _, ops = apply_diff(container, diff)
        except Exception as exc:
            return VerificationResult(ok=False, reasons=[f"apply_diff failed: {exc}"])
        return verify_diff(container, ops, self.invariants, use_smt=self.use_smt)

    def _spool_failure(
        self, candidate: GeneratedCandidate, verification: VerificationResult
    ) -> None:
        if self.reservoir is None:
            return
        fc = FailedCandidate.new(
            diff=candidate.diff,
            reason="verifier",
            rejector="self_reflection",
            mutation_policy="triz_inspired",
            contradiction_id=candidate.contradiction_id,
            notes="; ".join(verification.reasons) if verification.reasons else None,
        )
        self.reservoir.record(fc)


def _coerce_candidate_diff(payload: dict[str, Any]) -> CandidateDiff:
    """Normalise the dict shape emitted by TemplateIdeaLLM into a CandidateDiff."""
    return CandidateDiff.model_validate(payload)


def write_session_jsonl(
    proposals: Iterable[Proposal], summary: SessionSummary, out_path: Path | str
) -> Path:
    """Append one JSONL row per proposal plus a trailing summary line."""
    import json

    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for prop in proposals:
            fh.write(
                json.dumps(
                    {
                        "row": "proposal",
                        "proposal_id": prop.proposal_id,
                        "contradiction_id": prop.contradiction.contradiction_id,
                        "principle_id": prop.candidate.principle_id,
                        "accepted": prop.accepted,
                        "reasons": prop.verification.reasons,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        fh.write(
            json.dumps(
                {
                    "row": "summary",
                    "session_id": summary.session_id,
                    "n_contradictions": summary.n_contradictions,
                    "n_proposals": summary.n_proposals,
                    "n_passed": summary.n_passed,
                    "n_failed": summary.n_failed,
                    "duration_ms": summary.duration_ms,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    return p


__all__ = [
    "Proposal",
    "SelfReflectionSession",
    "SessionSummary",
    "write_session_jsonl",
]
