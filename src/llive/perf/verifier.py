# SPDX-License-Identifier: Apache-2.0
"""APO Verifier — §E3 formal pre-check (C-9).

Last gate before an Optimizer (C-8) proposal reaches ApprovalBus
(C-10) / human review. Each ``Modification`` is run through a list of
``InvariantCheck`` callables; the first ``False`` rejects the proposal
and the reason is recorded.

Invariants are intentionally plain callables, not Z3 constraints. The
domain here (numeric ``current → proposed`` deltas) is simple enough
that callable predicates are clearer than SMT encoding, and they keep
the verifier free of optional dependencies. The structural verifier in
``llive.evolution.verifier`` (which *does* use Z3) handles the
heavier "structural change to a container spec" case.

The output is a structured ``VerificationResult`` so audit logs /
ApprovalBus payloads can carry both the accepted and the rejected
proposals with rationales.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from llive.perf.optimizer import Modification

# A check returns either a plain bool (legacy) or (bool, reason: str).
_InvariantReturn = bool | tuple[bool, str]
InvariantCheck = Callable[[Modification], _InvariantReturn]


@dataclass(frozen=True)
class RejectedModification:
    """One proposal that failed verification, with the offending invariant's name."""

    modification: Modification
    invariant: str
    reason: str


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of one ``Verifier.verify`` call."""

    accepted: tuple[Modification, ...] = ()
    rejected: tuple[RejectedModification, ...] = ()

    @property
    def all_accepted(self) -> bool:
        return not self.rejected


@dataclass
class Verifier:
    """Pre-flight invariant checker for APO Modifications."""

    invariants: tuple[InvariantCheck, ...] = field(default_factory=tuple)

    def add(self, check: InvariantCheck) -> None:
        self.invariants = (*self.invariants, check)

    def verify(self, modifications: Sequence[Modification]) -> VerificationResult:
        accepted: list[Modification] = []
        rejected: list[RejectedModification] = []
        for mod in modifications:
            failure: tuple[str, str] | None = None
            for check in self.invariants:
                name = getattr(check, "__name__", "invariant")
                try:
                    result = check(mod)
                except Exception as exc:
                    failure = (name, f"invariant raised: {exc!r}")
                    break
                ok, reason = _unpack(result)
                if not ok:
                    failure = (name, reason)
                    break
            if failure is None:
                accepted.append(mod)
            else:
                rejected.append(
                    RejectedModification(
                        modification=mod, invariant=failure[0], reason=failure[1]
                    )
                )
        return VerificationResult(
            accepted=tuple(accepted), rejected=tuple(rejected)
        )


def _unpack(result: _InvariantReturn) -> tuple[bool, str]:
    if isinstance(result, tuple):
        ok, reason = result
        return bool(ok), str(reason)
    return bool(result), "" if result else "predicate returned False"


# ---------------------------------------------------------------------------
# Built-in invariants — reusable, named, fail with explanations
# ---------------------------------------------------------------------------


def non_negative(mod: Modification) -> _InvariantReturn:
    """``proposed`` must not go below zero. Catches accidental sign flips."""
    if mod.proposed < 0:
        return False, f"{mod.target}.proposed={mod.proposed} < 0"
    return True, ""


def relaxation_only(target_prefix: str = "profiler.threshold") -> InvariantCheck:
    """Threshold-relaxation targets may only *increase* (never tighten silently)."""

    def _check(mod: Modification) -> _InvariantReturn:
        if not mod.target.startswith(target_prefix):
            return True, ""
        if mod.proposed < mod.current:
            return False, (
                f"{mod.target}: relaxation_only but proposed "
                f"{mod.proposed} < current {mod.current}"
            )
        return True, ""

    _check.__name__ = "relaxation_only"
    return _check


def load_reduction_only(target_prefix: str = "scheduler") -> InvariantCheck:
    """Scheduler / load targets may only *decrease* under APO control."""

    def _check(mod: Modification) -> _InvariantReturn:
        if not mod.target.startswith(target_prefix):
            return True, ""
        if mod.proposed > mod.current:
            return False, (
                f"{mod.target}: load_reduction_only but proposed "
                f"{mod.proposed} > current {mod.current}"
            )
        return True, ""

    _check.__name__ = "load_reduction_only"
    return _check


def bounded_step(max_step_ratio: float = 0.5) -> InvariantCheck:
    """No single step may shift the value by more than ``max_step_ratio``.

    Forces APO to take small steps even when an aggressive strategy is
    plugged in. Prevents one round from wiping the safety envelope.
    """

    def _check(mod: Modification) -> _InvariantReturn:
        if mod.current == 0:
            return True, ""  # cannot ratio against zero, defer to other checks
        ratio = abs(mod.proposed - mod.current) / abs(mod.current)
        if ratio > max_step_ratio:
            return False, (
                f"{mod.target}: |Δ/current|={ratio:.3f} > "
                f"max_step_ratio={max_step_ratio}"
            )
        return True, ""

    _check.__name__ = "bounded_step"
    return _check


def default_invariants() -> Iterable[InvariantCheck]:
    """Conservative invariant pack suitable for most APO deployments."""
    return (
        non_negative,
        relaxation_only(),
        load_reduction_only(),
        bounded_step(0.5),
    )


__all__ = [
    "InvariantCheck",
    "RejectedModification",
    "VerificationResult",
    "Verifier",
    "bounded_step",
    "default_invariants",
    "load_reduction_only",
    "non_negative",
    "relaxation_only",
]
