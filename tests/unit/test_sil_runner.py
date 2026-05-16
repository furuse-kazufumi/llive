# SPDX-License-Identifier: Apache-2.0
"""Tests for SILRunner (C-13)."""

from __future__ import annotations

from llive.fullsense.bridges.tlb import TLBCoordinator
from llive.fullsense.self_interrogation import (
    InterrogationResult,
    InterrogatorId,
    SelfInterrogator,
)
from llive.fullsense.sil_runner import SILRunner
from llive.fullsense.types import ActionDecision, ActionPlan, EpistemicType, Stimulus


def _stim(content: str = "短い指示!") -> Stimulus:
    # Triggers SI1 (短い + ASCII !) so we get at least one fired result.
    return Stimulus(content=content, source="user", epistemic_type=EpistemicType.PRAGMATIC)


def _plan(decision: ActionDecision = ActionDecision.NOTE) -> ActionPlan:
    return ActionPlan(decision=decision, rationale="test", thought=None)


def test_first_call_runs_base_interrogator() -> None:
    coord = TLBCoordinator()
    runner = SILRunner(base=SelfInterrogator(), coordinator=coord)

    results = runner.run(_stim(), _plan())
    assert isinstance(results, tuple)
    assert all(isinstance(r, InterrogationResult) for r in results)
    assert any(r.fired for r in results)

    assert runner.stats()["misses"] == 1
    assert runner.stats()["hits"] == 0


def test_repeated_call_hits_cache() -> None:
    coord = TLBCoordinator()
    runner = SILRunner(base=SelfInterrogator(), coordinator=coord)

    s, p = _stim(), _plan()
    a = runner.run(s, p)
    b = runner.run(s, p)
    c = runner.run(s, p)
    assert a is b is c  # exact same cached tuple

    stats = runner.stats()
    assert stats["misses"] == 1
    assert stats["hits"] == 2
    assert stats["hit_rate"] > 0.5


def test_different_decision_distinct_cache_entry() -> None:
    coord = TLBCoordinator()
    runner = SILRunner(base=SelfInterrogator(), coordinator=coord)

    s = _stim()
    r1 = runner.run(s, _plan(ActionDecision.NOTE))
    r2 = runner.run(s, _plan(ActionDecision.PROPOSE))
    # SI5 fires for PROPOSE / INTERVENE — the two runs must differ.
    fired_si5_1 = any(
        r.interrogator == InterrogatorId.SI5_FIND_BLIND_SPOT and r.fired for r in r1
    )
    fired_si5_2 = any(
        r.interrogator == InterrogatorId.SI5_FIND_BLIND_SPOT and r.fired for r in r2
    )
    assert fired_si5_1 is False
    assert fired_si5_2 is True
    assert runner.stats()["misses"] == 2  # both runs were misses


def test_different_stimulus_distinct_cache_entry() -> None:
    coord = TLBCoordinator()
    runner = SILRunner(base=SelfInterrogator(), coordinator=coord)
    runner.run(_stim("hello"), _plan())
    runner.run(_stim("world"), _plan())
    assert runner.stats()["misses"] == 2


def test_cache_key_is_deterministic() -> None:
    s = _stim()
    p = _plan()
    k1 = SILRunner.cache_key(s, p)
    k2 = SILRunner.cache_key(s, p)
    assert k1 == k2
    assert len(k1) == 16


def test_stats_empty_runner_returns_zeroes() -> None:
    runner = SILRunner(base=SelfInterrogator(), coordinator=TLBCoordinator())
    assert runner.stats() == {"hits": 0, "misses": 0, "hit_rate": 0.0}


def test_coordinator_is_shared_across_runs() -> None:
    """Same coordinator across two SILRunner instances → cache survives."""
    coord = TLBCoordinator()
    s, p = _stim(), _plan()

    SILRunner(base=SelfInterrogator(), coordinator=coord).run(s, p)
    # New runner instance, same coordinator — should hit.
    SILRunner(base=SelfInterrogator(), coordinator=coord).run(s, p)

    cache_stats = coord.stats()
    assert cache_stats["SIL/interrogate"].hits == 1
    assert cache_stats["SIL/interrogate"].misses == 1
