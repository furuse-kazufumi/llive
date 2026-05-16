# SPDX-License-Identifier: Apache-2.0
"""ICP — Idle Collaboration Protocol (C-14).

While the local agent is *idle* (no recent user input), it can spend
cycles asking peer Local LLMs (typically reachable through llmesh) for
information that would otherwise wait for a human prompt. Spec §A°2
calls this "the polite version of the swarm": never interrupt the user,
never spam the network, but use slack time to keep the local model's
context fresh.

This module deliberately stays free of any llmesh import: the actual
peer transport is supplied as a ``PeerClient`` callable. The MVP
implementation here is a scheduler + bookkeeping layer; the real wire
work happens at the boundary (``llmesh.skills.SkillSyncClient`` in
production, in-memory function in tests).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from llive.idle.detector import IdleDetector

PeerProvider = Callable[[], Iterable[str]]


@dataclass(frozen=True)
class CollabQuery:
    """One question to ask a peer during idle time."""

    intent: str
    """Why we're asking — e.g. ``"skill_lookup"``, ``"verify_claim"``."""
    query: str
    """Free-text payload understood by the receiving peer."""
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class CollabResult:
    """One peer's reply (or its absence)."""

    peer: str
    success: bool
    payload: dict[str, object] = field(default_factory=dict)
    error: str = ""
    at: float = 0.0  # filled in by IdleCollaborator


PeerClient = Callable[[str, CollabQuery], CollabResult]


@dataclass(frozen=True)
class TickReport:
    """Summary of one ``IdleCollaborator.tick`` invocation."""

    triggered: bool
    reason: str
    """Why the tick ran or didn't (e.g. ``"not_idle"``, ``"no_peers"``, ``"ok"``)."""
    results: tuple[CollabResult, ...] = ()


@dataclass
class IdleCollaborator:
    """Idle-time peer scheduler. Pure orchestration; no transport here.

    Args:
        detector: ``IdleDetector`` deciding whether we're idle.
        peer_provider: callable returning the current peer endpoint set.
        peer_client: callable that actually contacts one peer with a
            ``CollabQuery`` and returns a ``CollabResult``. Exceptions
            from this callable are captured into a failed ``CollabResult``,
            never raised.
        max_peers_per_tick: cap on peers contacted in one tick to avoid
            a thundering-herd against the mesh.
        cooldown_s: minimum seconds between two ticks even if both
            satisfy the idle condition. Defaults to 0 (no cooldown);
            set this to throttle against chatty schedulers.
    """

    detector: IdleDetector
    peer_provider: PeerProvider
    peer_client: PeerClient
    max_peers_per_tick: int = 3
    cooldown_s: float = 0.0
    _last_tick_at: float = field(default=-1.0, init=False)

    def tick(self, query: CollabQuery, *, now: float | None = None) -> TickReport:
        clock = now if now is not None else time.monotonic()

        status = self.detector.status()
        if not status.idle:
            return TickReport(triggered=False, reason="not_idle")

        if (
            self.cooldown_s > 0
            and self._last_tick_at >= 0
            and (clock - self._last_tick_at) < self.cooldown_s
        ):
            return TickReport(triggered=False, reason="cooldown")

        peers = [p for p in self.peer_provider() if isinstance(p, str) and p]
        if not peers:
            return TickReport(triggered=False, reason="no_peers")

        chosen = peers[: max(0, self.max_peers_per_tick)]
        if not chosen:
            return TickReport(triggered=False, reason="max_peers_zero")

        results: list[CollabResult] = []
        for peer in chosen:
            try:
                raw = self.peer_client(peer, query)
            except Exception as exc:
                results.append(
                    CollabResult(
                        peer=peer, success=False, error=repr(exc), at=clock
                    )
                )
                continue
            # Stamp the timestamp uniformly even if the client forgot.
            stamped = (
                raw
                if raw.at != 0.0
                else CollabResult(
                    peer=raw.peer or peer,
                    success=raw.success,
                    payload=dict(raw.payload),
                    error=raw.error,
                    at=clock,
                )
            )
            results.append(stamped)

        self._last_tick_at = clock
        return TickReport(triggered=True, reason="ok", results=tuple(results))


__all__ = [
    "CollabQuery",
    "CollabResult",
    "IdleCollaborator",
    "PeerClient",
    "PeerProvider",
    "TickReport",
]
