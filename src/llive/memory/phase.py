# SPDX-License-Identifier: Apache-2.0
"""Memory Phase Manager (MEM-09).

Five phases: ``hot → warm → cold → archived → erased``.

Transitions are evaluated on a configurable cron (default daily). Each
entry exposes ``phase``, ``last_access_at``, ``access_count``, and
``phase_changed_at``. Phase 1 / Phase 2 builtin memories do not yet carry
these fields out of the box; this module operates on a generic record
protocol so callers can wire it up incrementally.

GDPR semantics: ``erased`` removes payload + embedding from storage, keeps
metadata only (so audit trails survive right-to-be-forgotten requests).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

PHASES = ("hot", "warm", "cold", "archived", "erased")

DEFAULT_THRESHOLDS_DAYS: dict[tuple[str, str], int] = {
    ("hot", "warm"): 7,
    ("warm", "cold"): 30,
    ("cold", "archived"): 90,
    ("archived", "erased"): 180,
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class PhaseRecord:
    """Generic record shape understood by the phase manager."""

    entry_id: str
    phase: str = "hot"
    last_access_at: datetime = field(default_factory=_utcnow)
    access_count: int = 0
    phase_changed_at: datetime = field(default_factory=_utcnow)
    surprise: float | None = None
    privacy_class: str = "internal"  # public / internal / confidential / untrusted

    def touch(self) -> None:
        """Record an access; promotes back to hot."""
        self.last_access_at = _utcnow()
        self.access_count += 1
        if self.phase != "hot":
            self.phase = "hot"
            self.phase_changed_at = _utcnow()

    def age_days(self, now: datetime | None = None) -> float:
        ref = now or _utcnow()
        return (ref - self.last_access_at).total_seconds() / 86400.0


class PhaseEraser(Protocol):
    """Callback invoked when a record transitions to ``erased``.

    Implementations should drop payload + embedding from underlying storage,
    keeping metadata (id, phase=erased, audit trail) only.
    """

    def __call__(self, record: PhaseRecord) -> None: ...


@dataclass
class TransitionEvent:
    entry_id: str
    from_phase: str
    to_phase: str
    age_days: float
    reason: str = ""


class MemoryPhaseManager:
    """Apply phase transitions to a batch of records based on age + surprise.

    Phase 2 keeps it simple: time-based with one surprise-aware guard at
    ``cold → archived`` (low-surprise records archive faster). Phase 3+
    will tighten this with per-page Bayesian thresholds.
    """

    def __init__(
        self,
        thresholds_days: dict[tuple[str, str], int] | None = None,
        archive_surprise_threshold: float | None = 0.2,
        eraser: PhaseEraser | None = None,
    ) -> None:
        self.thresholds_days = dict(thresholds_days or DEFAULT_THRESHOLDS_DAYS)
        for transition in self.thresholds_days:
            if transition not in DEFAULT_THRESHOLDS_DAYS:
                raise ValueError(f"unknown transition {transition!r}")
        self.archive_surprise_threshold = archive_surprise_threshold
        self.eraser = eraser

    # -- public api --------------------------------------------------------

    def evaluate(
        self,
        records: list[PhaseRecord],
        now: datetime | None = None,
    ) -> list[TransitionEvent]:
        """Apply transitions in-place and return the list of transitions."""
        ref = now or _utcnow()
        events: list[TransitionEvent] = []
        for rec in records:
            ev = self._step(rec, ref)
            if ev is not None:
                events.append(ev)
        return events

    # -- internals ---------------------------------------------------------

    def _step(self, rec: PhaseRecord, now: datetime) -> TransitionEvent | None:
        age = rec.age_days(now)
        cur = rec.phase
        if cur == "erased":
            return None
        nxt = self._next_phase(cur)
        if nxt is None:
            return None
        threshold = self.thresholds_days.get((cur, nxt))
        if threshold is None:
            return None
        if age < threshold:
            return None
        # cold → archived has an extra surprise guard
        if (cur, nxt) == ("cold", "archived") and self.archive_surprise_threshold is not None:
            if rec.surprise is not None and rec.surprise >= self.archive_surprise_threshold:
                return None  # keep cold; high-surprise content held longer
        # archived → erased respects privacy class
        if (cur, nxt) == ("archived", "erased") and rec.privacy_class == "public":
            # public data is allowed to persist indefinitely
            return None
        # transition
        prev = rec.phase
        rec.phase = nxt
        rec.phase_changed_at = now
        if nxt == "erased" and self.eraser is not None:
            self.eraser(rec)
        return TransitionEvent(
            entry_id=rec.entry_id,
            from_phase=prev,
            to_phase=nxt,
            age_days=age,
            reason=self._reason(prev, nxt, age, rec),
        )

    def _next_phase(self, current: str) -> str | None:
        try:
            idx = PHASES.index(current)
        except ValueError:
            return None
        if idx >= len(PHASES) - 1:
            return None
        return PHASES[idx + 1]

    def _reason(self, prev: str, nxt: str, age_days: float, rec: PhaseRecord) -> str:
        return f"age={age_days:.1f}d, threshold={self.thresholds_days[(prev, nxt)]}d"
