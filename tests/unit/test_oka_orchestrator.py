# SPDX-License-Identifier: Apache-2.0
"""OKA-03 — StrategyOrchestrator tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from llive.brief import BriefLedger
from llive.oka import (
    StrategyFamily,
    StrategyOrchestrator,
    StrategySwitchEvent,
)


def _seed_orch() -> StrategyOrchestrator:
    orch = StrategyOrchestrator(history_window=3, stall_delta=0.02)
    orch.register(StrategyFamily(name="symbolic", tags=("z3",)))
    orch.register(StrategyFamily(name="geometric"))
    orch.register(StrategyFamily(name="numeric"))
    return orch


def test_register_and_list() -> None:
    orch = _seed_orch()
    names = [f.name for f in orch.list_families()]
    assert names == ["symbolic", "geometric", "numeric"]


def test_register_rejects_duplicate() -> None:
    orch = _seed_orch()
    with pytest.raises(ValueError):
        orch.register(StrategyFamily(name="symbolic"))


def test_activate_rejects_unknown() -> None:
    orch = _seed_orch()
    with pytest.raises(KeyError):
        orch.activate("bogus")


def test_should_switch_only_after_window_fills() -> None:
    orch = _seed_orch()
    orch.activate("symbolic")
    orch.push_progress(0.1)
    orch.push_progress(0.1)
    assert not orch.should_switch()
    orch.push_progress(0.1)
    assert orch.should_switch()  # 3 件 (window) で停滞検出


def test_progress_increase_avoids_stall() -> None:
    orch = _seed_orch()
    orch.activate("symbolic")
    for p in (0.1, 0.3, 0.6):
        orch.push_progress(p)
    assert not orch.should_switch()


def test_switch_records_event_and_changes_active() -> None:
    orch = _seed_orch()
    orch.activate("symbolic")
    for _ in range(3):
        orch.push_progress(0.05)
    evt = orch.switch_to("geometric", reason="symbolic stalled")
    assert isinstance(evt, StrategySwitchEvent)
    assert evt.from_strategy == "symbolic"
    assert evt.to_strategy == "geometric"
    assert orch.active == "geometric"
    # history resets so the new strategy can be evaluated fresh
    assert not orch.should_switch()


def test_switch_to_same_strategy_rejected() -> None:
    orch = _seed_orch()
    orch.activate("symbolic")
    with pytest.raises(ValueError):
        orch.switch_to("symbolic")


def test_ledger_integration(tmp_path: Path) -> None:
    ledger = BriefLedger(tmp_path / "led.jsonl")
    orch = _seed_orch()
    orch.bind_ledger(ledger)
    orch.activate("symbolic")
    for _ in range(3):
        orch.push_progress(0.05)
    orch.switch_to("numeric", reason="stalled")
    events = [r for r in ledger.read() if r.event == "oka_strategy_switched"]
    assert len(events) == 1
    tg = ledger.trace_graph()
    assert any(d["event"] == "oka_strategy_switched" for d in tg.decision_chain)


def test_progress_value_range_validation() -> None:
    orch = _seed_orch()
    orch.activate("symbolic")
    with pytest.raises(ValueError):
        orch.push_progress(1.5)
