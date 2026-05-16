# SPDX-License-Identifier: Apache-2.0
"""APO Optimizer — §E2 bounded modification (C-8).

Diagnostics (C-7) emits a list of ``Issue`` objects describing where
the runtime deviated from desired behaviour. The Optimizer turns those
issues into **proposed** ``Modification`` objects — never applied
directly, because §E2 mandates that:

1. Every self-modification is **bounded**: a hard cap on count per
   round AND a value-range envelope per target.
2. The proposal is **transparent**: each modification carries its
   rationale (a reference back to the originating ``Issue``).
3. The actual mutation is gated by ApprovalBus (C-1) and the
   Verifier (§E3) — both downstream of this module.

This module deliberately does no I/O and no mutation. It is the pure
function ``issues -> proposals`` that the rest of the self-correction
pipeline can be designed against.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from llive.perf.diagnostics import Issue

OptimizationStrategy = Callable[[Issue], "Modification | None"]


@dataclass(frozen=True)
class Modification:
    """A bounded change proposal targeting one named parameter.

    ``target`` is an opaque dotted-path identifier (e.g.
    ``"profiler.threshold.loop_tick_p95_ms"``) — interpreted by the
    eventual applier, not by this module. ``current`` and ``proposed``
    are the before / after numeric values. ``rationale`` carries the
    originating ``Issue`` for audit logs and ApprovalBus payloads.
    """

    target: str
    current: float
    proposed: float
    rationale: Issue

    @property
    def delta(self) -> float:
        return self.proposed - self.current


@dataclass(frozen=True)
class ModificationBound:
    """Hard envelope on what a target's proposed value is allowed to be."""

    target: str
    min_value: float
    max_value: float


@dataclass
class Optimizer:
    """Issue → Modification proposer with bounded-modification guarantees.

    Args:
        strategies: callables that map one ``Issue`` to one
            ``Modification`` (or ``None`` to abstain). Strategies are
            tried in order; the first non-None proposal wins per issue.
        max_modifications: hard cap on proposals returned by one
            ``propose()`` call. Excess proposals are dropped (highest
            severity kept first).
        bounds: per-target envelopes. A proposal whose ``proposed``
            value lies outside the envelope is rejected (the issue is
            still surfaced but no modification is emitted).
    """

    strategies: tuple[OptimizationStrategy, ...] = ()
    max_modifications: int = 5
    bounds: tuple[ModificationBound, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.max_modifications < 0:
            raise ValueError("max_modifications must be >= 0")

    def _within_bound(self, mod: Modification) -> bool:
        for b in self.bounds:
            if b.target == mod.target:
                return b.min_value <= mod.proposed <= b.max_value
        # No declared bound → accept; caller can declare a strict bound
        # for safety-critical targets to forbid unspecified ones.
        return True

    def propose(self, issues: Sequence[Issue]) -> list[Modification]:
        """Map issues to bounded modifications. Pure; no I/O."""
        # Issues already carry severity — keep the worst first so that
        # the max_modifications cap drops noise, not signal.
        ranked = sorted(
            issues,
            key=lambda i: ({"error": 2, "warn": 1, "info": 0}[i.severity], i.observed),
            reverse=True,
        )
        proposals: list[Modification] = []
        for issue in ranked:
            mod: Modification | None = None
            for strat in self.strategies:
                mod = strat(issue)
                if mod is not None:
                    break
            if mod is None:
                continue
            if not self._within_bound(mod):
                continue
            proposals.append(mod)
            if len(proposals) >= self.max_modifications:
                break
        return proposals


# ---------------------------------------------------------------------------
# Strategy factories — common, reusable proposals
# ---------------------------------------------------------------------------


def raise_threshold_strategy(
    *,
    target_prefix: str = "profiler.threshold",
    bump: float = 1.10,
) -> OptimizationStrategy:
    """Propose a *small* upward relaxation of the threshold that was breached.

    Use when "tight thresholds catching real but acceptable drift" is
    the dominant failure mode. The target identifier is constructed as
    ``f"{target_prefix}.{metric}.{stat}"`` so callers can pin a bound
    on the same key.
    """

    def _strategy(issue: Issue) -> Modification | None:
        if issue.threshold <= 0:
            return None
        new_value = issue.threshold * bump
        target = f"{target_prefix}.{issue.metric}.{issue.stat}"
        return Modification(
            target=target,
            current=issue.threshold,
            proposed=new_value,
            rationale=issue,
        )

    return _strategy


def reduce_load_strategy(
    *,
    target: str = "scheduler.concurrency",
    current_concurrency: int = 4,
    floor: int = 1,
) -> OptimizationStrategy:
    """Propose dropping concurrency when latency-style issues recur.

    Intended for ``loop.tick.ms``-style metrics. Returns ``None`` for
    issues unrelated to load. Pairs naturally with a
    ``ModificationBound`` that pins the floor.
    """

    def _strategy(issue: Issue) -> Modification | None:
        if not issue.metric.endswith(".ms") and "loop" not in issue.metric:
            return None
        if current_concurrency <= floor:
            return None
        return Modification(
            target=target,
            current=float(current_concurrency),
            proposed=float(max(floor, current_concurrency - 1)),
            rationale=issue,
        )

    return _strategy


__all__ = [
    "Modification",
    "ModificationBound",
    "Optimizer",
    "OptimizationStrategy",
    "raise_threshold_strategy",
    "reduce_load_strategy",
]
