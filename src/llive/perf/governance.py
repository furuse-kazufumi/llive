# SPDX-License-Identifier: Apache-2.0
"""APO ApprovalBus glue — close the §E self-correction loop (C-10).

Wires the C-9 Verifier output to the C-1 ApprovalBus. Each Modification
becomes one ``ApprovalRequest`` with action ``"apo.modify"`` and a
payload that captures the full change context (target, current,
proposed, rationale metric/severity, originating reason). The bus's
policy layer is expected to either auto-decide (e.g. AllowList of safe
target prefixes) or queue for human review.

Only APPROVED modifications reach the supplied ``applier`` callable.
The result is a structured ``ApplyResult`` summarising every outcome so
the caller can log / display / replay.

Module is pure orchestration: no I/O of its own, no Verifier or
Optimizer dependency at runtime — the caller composes the pipeline.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from llive.approval.bus import ApprovalBus, Verdict
from llive.perf.optimizer import Modification

ApplyStatus = Literal["applied", "denied", "skipped_unknown", "applier_error"]

Applier = Callable[[Modification], None]


@dataclass(frozen=True)
class ApplyOutcome:
    """One Modification's journey through the gate."""

    modification: Modification
    status: ApplyStatus
    verdict: Verdict | None
    request_id: str
    reason: str = ""


@dataclass(frozen=True)
class ApplyResult:
    """Aggregate of an ``apply_with_approval`` run."""

    outcomes: tuple[ApplyOutcome, ...]

    @property
    def applied(self) -> tuple[ApplyOutcome, ...]:
        return tuple(o for o in self.outcomes if o.status == "applied")

    @property
    def denied(self) -> tuple[ApplyOutcome, ...]:
        return tuple(o for o in self.outcomes if o.status == "denied")

    @property
    def errors(self) -> tuple[ApplyOutcome, ...]:
        return tuple(o for o in self.outcomes if o.status == "applier_error")


def _modification_payload(mod: Modification) -> dict[str, object]:
    """Serialise a Modification for the ApprovalBus payload field."""
    rationale = mod.rationale
    return {
        "target": mod.target,
        "current": mod.current,
        "proposed": mod.proposed,
        "delta": mod.delta,
        "rationale": {
            "metric": rationale.metric,
            "stat": rationale.stat,
            "observed": rationale.observed,
            "threshold": rationale.threshold,
            "severity": rationale.severity,
            "reason": rationale.reason,
        },
    }


def apply_with_approval(
    bus: ApprovalBus,
    modifications: Sequence[Modification],
    applier: Applier,
    *,
    principal: str = "apo",
    action: str = "apo.modify",
) -> ApplyResult:
    """Send each modification through the bus; apply only on APPROVED.

    Args:
        bus: configured ``ApprovalBus`` (likely with a Policy that
            auto-approves a known target allow-list).
        modifications: typically ``VerificationResult.accepted``.
        applier: callback that performs the actual mutation. Exceptions
            are captured into ``ApplyOutcome.status = "applier_error"``
            and reason.
        principal: the principal field on the approval request
            (default ``"apo"``).
        action: action string on the request (default
            ``"apo.modify"``); useful to swap when running multiple
            APO instances side by side.

    Returns:
        ``ApplyResult`` with one ``ApplyOutcome`` per input modification.
    """
    outcomes: list[ApplyOutcome] = []
    for mod in modifications:
        req = bus.request(
            action, _modification_payload(mod), principal=principal
        )
        verdict = bus.current_verdict(req.request_id)
        if verdict == Verdict.APPROVED:
            try:
                applier(mod)
            except Exception as exc:
                outcomes.append(
                    ApplyOutcome(
                        modification=mod,
                        status="applier_error",
                        verdict=verdict,
                        request_id=req.request_id,
                        reason=repr(exc),
                    )
                )
                continue
            outcomes.append(
                ApplyOutcome(
                    modification=mod,
                    status="applied",
                    verdict=verdict,
                    request_id=req.request_id,
                )
            )
        elif verdict == Verdict.DENIED:
            outcomes.append(
                ApplyOutcome(
                    modification=mod,
                    status="denied",
                    verdict=verdict,
                    request_id=req.request_id,
                    reason="policy_or_human_denied",
                )
            )
        else:  # REVOKED or still pending — treat as not applied
            outcomes.append(
                ApplyOutcome(
                    modification=mod,
                    status="skipped_unknown",
                    verdict=verdict,
                    request_id=req.request_id,
                    reason=f"verdict={verdict!s}",
                )
            )
    return ApplyResult(outcomes=tuple(outcomes))


__all__ = [
    "ApplyOutcome",
    "ApplyResult",
    "ApplyStatus",
    "Applier",
    "apply_with_approval",
]
