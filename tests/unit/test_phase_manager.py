# SPDX-License-Identifier: Apache-2.0
"""MEM-09: MemoryPhaseManager."""

from __future__ import annotations

import datetime as _dt

import pytest

from llive.memory.phase import (
    DEFAULT_THRESHOLDS_DAYS,
    MemoryPhaseManager,
    PhaseRecord,
)

_NOW = _dt.datetime(2026, 5, 13, 12, 0, 0, tzinfo=_dt.UTC)


def _record(entry_id, phase="hot", days_ago=0, **kw):
    return PhaseRecord(
        entry_id=entry_id,
        phase=phase,
        last_access_at=_NOW - _dt.timedelta(days=days_ago),
        **kw,
    )


def test_hot_to_warm_after_7d():
    rec = _record("a", phase="hot", days_ago=8)
    mgr = MemoryPhaseManager()
    events = mgr.evaluate([rec], now=_NOW)
    assert len(events) == 1
    assert events[0].to_phase == "warm"
    assert rec.phase == "warm"


def test_warm_to_cold_after_30d():
    rec = _record("b", phase="warm", days_ago=35)
    events = MemoryPhaseManager().evaluate([rec], now=_NOW)
    assert rec.phase == "cold"
    assert events[0].to_phase == "cold"


def test_cold_to_archived_after_90d_low_surprise():
    rec = _record("c", phase="cold", days_ago=100, surprise=0.1)
    events = MemoryPhaseManager().evaluate([rec], now=_NOW)
    assert rec.phase == "archived"
    assert events[0].to_phase == "archived"


def test_cold_stays_when_surprise_high():
    rec = _record("c", phase="cold", days_ago=100, surprise=0.6)
    events = MemoryPhaseManager().evaluate([rec], now=_NOW)
    assert rec.phase == "cold"
    assert events == []


def test_archived_to_erased_after_180d():
    rec = _record("d", phase="archived", days_ago=200, privacy_class="internal")
    events = MemoryPhaseManager().evaluate([rec], now=_NOW)
    assert rec.phase == "erased"
    assert events[0].to_phase == "erased"


def test_public_data_never_erases():
    rec = _record("public", phase="archived", days_ago=400, privacy_class="public")
    events = MemoryPhaseManager().evaluate([rec], now=_NOW)
    assert rec.phase == "archived"
    assert events == []


def test_eraser_called_on_transition():
    erased: list[str] = []

    def eraser(r: PhaseRecord) -> None:
        erased.append(r.entry_id)

    mgr = MemoryPhaseManager(eraser=eraser)
    rec = _record("e", phase="archived", days_ago=200)
    mgr.evaluate([rec], now=_NOW)
    assert erased == ["e"]


def test_no_transition_before_threshold():
    rec = _record("y", phase="hot", days_ago=3)
    events = MemoryPhaseManager().evaluate([rec], now=_NOW)
    assert events == []


def test_touch_returns_to_hot():
    rec = _record("z", phase="cold", days_ago=100)
    rec.touch()
    assert rec.phase == "hot"
    assert rec.access_count == 1


def test_default_thresholds_complete():
    # Every consecutive transition is covered
    for src, dst in [
        ("hot", "warm"),
        ("warm", "cold"),
        ("cold", "archived"),
        ("archived", "erased"),
    ]:
        assert (src, dst) in DEFAULT_THRESHOLDS_DAYS


def test_unknown_transition_rejected():
    with pytest.raises(ValueError):
        MemoryPhaseManager(thresholds_days={("hot", "cold"): 5})


def test_evaluate_does_not_touch_erased():
    rec = _record("done", phase="erased", days_ago=500)
    events = MemoryPhaseManager().evaluate([rec], now=_NOW)
    assert events == []
