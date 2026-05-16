# SPDX-License-Identifier: Apache-2.0
"""Tests for ICP (idle collaboration) — C-14."""

from __future__ import annotations

import pytest

from llive.idle import (
    CollabQuery,
    CollabResult,
    IdleCollaborator,
    IdleDetector,
)


def _idle_detector(idle: bool) -> IdleDetector:
    """An IdleDetector wired to a manual provider that reports the desired state."""
    threshold = 60.0
    seconds = threshold + 1 if idle else 0.0
    return IdleDetector(
        threshold_s=threshold,
        last_input_provider=lambda: seconds,
    )


def _ok_client(peer: str, query: CollabQuery) -> CollabResult:
    return CollabResult(peer=peer, success=True, payload={"echo": query.query})


def test_not_idle_skips_tick() -> None:
    coll = IdleCollaborator(
        detector=_idle_detector(False),
        peer_provider=lambda: ["p1"],
        peer_client=_ok_client,
    )
    report = coll.tick(CollabQuery(intent="ask", query="q"))
    assert report.triggered is False
    assert report.reason == "not_idle"
    assert report.results == ()


def test_idle_with_no_peers_skips() -> None:
    coll = IdleCollaborator(
        detector=_idle_detector(True),
        peer_provider=lambda: [],
        peer_client=_ok_client,
    )
    report = coll.tick(CollabQuery(intent="ask", query="q"))
    assert report.triggered is False
    assert report.reason == "no_peers"


def test_idle_dispatches_to_each_peer() -> None:
    coll = IdleCollaborator(
        detector=_idle_detector(True),
        peer_provider=lambda: ["p1", "p2", "p3"],
        peer_client=_ok_client,
    )
    report = coll.tick(CollabQuery(intent="ask", query="hello"))
    assert report.triggered is True
    peers = [r.peer for r in report.results]
    assert peers == ["p1", "p2", "p3"]
    assert all(r.success for r in report.results)


def test_max_peers_per_tick_caps_dispatch() -> None:
    coll = IdleCollaborator(
        detector=_idle_detector(True),
        peer_provider=lambda: [f"p{i}" for i in range(10)],
        peer_client=_ok_client,
        max_peers_per_tick=2,
    )
    report = coll.tick(CollabQuery(intent="ask", query="hello"))
    assert len(report.results) == 2


def test_max_peers_zero_emits_explanation() -> None:
    coll = IdleCollaborator(
        detector=_idle_detector(True),
        peer_provider=lambda: ["p1"],
        peer_client=_ok_client,
        max_peers_per_tick=0,
    )
    report = coll.tick(CollabQuery(intent="ask", query="q"))
    assert report.triggered is False
    assert report.reason == "max_peers_zero"


def test_client_exception_recorded_as_failure() -> None:
    def boom(peer: str, query: CollabQuery) -> CollabResult:
        raise RuntimeError(f"peer {peer} unreachable")

    coll = IdleCollaborator(
        detector=_idle_detector(True),
        peer_provider=lambda: ["p1"],
        peer_client=boom,
    )
    report = coll.tick(CollabQuery(intent="ask", query="q"))
    assert report.triggered is True
    r = report.results[0]
    assert r.success is False
    assert "peer p1 unreachable" in r.error


def test_cooldown_blocks_second_tick() -> None:
    coll = IdleCollaborator(
        detector=_idle_detector(True),
        peer_provider=lambda: ["p1"],
        peer_client=_ok_client,
        cooldown_s=30.0,
    )
    r1 = coll.tick(CollabQuery(intent="ask", query="q"), now=100.0)
    r2 = coll.tick(CollabQuery(intent="ask", query="q"), now=110.0)
    assert r1.triggered is True
    assert r2.triggered is False
    assert r2.reason == "cooldown"


def test_cooldown_allows_after_window() -> None:
    coll = IdleCollaborator(
        detector=_idle_detector(True),
        peer_provider=lambda: ["p1"],
        peer_client=_ok_client,
        cooldown_s=30.0,
    )
    r1 = coll.tick(CollabQuery(intent="ask", query="q"), now=100.0)
    r2 = coll.tick(CollabQuery(intent="ask", query="q"), now=140.0)
    assert r1.triggered is True
    assert r2.triggered is True


def test_results_carry_timestamp() -> None:
    coll = IdleCollaborator(
        detector=_idle_detector(True),
        peer_provider=lambda: ["p1"],
        peer_client=_ok_client,
    )
    report = coll.tick(CollabQuery(intent="ask", query="q"), now=12345.0)
    assert report.results[0].at == pytest.approx(12345.0)


def test_peer_provider_filters_empty_strings() -> None:
    coll = IdleCollaborator(
        detector=_idle_detector(True),
        peer_provider=lambda: ["", "p1", None],  # type: ignore[list-item]
        peer_client=_ok_client,
    )
    report = coll.tick(CollabQuery(intent="ask", query="q"))
    assert [r.peer for r in report.results] == ["p1"]
