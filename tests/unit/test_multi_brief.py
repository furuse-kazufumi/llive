# SPDX-License-Identifier: Apache-2.0
"""Tests for COG-MESH-01 MultiBriefCoherenceManager."""

from __future__ import annotations

from datetime import datetime

import pytest

from llive.cognitive_mesh.brief_containers import BriefRef
from llive.cognitive_mesh.multi_brief import (
    CoherenceEvent,
    MultiBriefCoherenceManager,
)


def _make() -> MultiBriefCoherenceManager:
    return MultiBriefCoherenceManager()


def test_attach_and_detach() -> None:
    m = _make()
    a = BriefRef.new("topic-a")
    b = BriefRef.new("topic-b")
    m.attach(a)
    m.attach(b)
    assert len(m) == 2
    assert set(m.brief_ids()) == {a.id, b.id}
    m.detach(a.id)
    assert len(m) == 1
    assert m.brief_ids() == [b.id]


def test_attach_duplicate_rejected() -> None:
    m = _make()
    a = BriefRef.new("x")
    m.attach(a)
    with pytest.raises(ValueError, match="already attached"):
        m.attach(a)


def test_detach_unknown_raises() -> None:
    m = _make()
    with pytest.raises(KeyError):
        m.detach("nonexistent")


def test_by_topic_finds_briefs() -> None:
    m = _make()
    a = BriefRef.new("alpha")
    b = BriefRef.new("alpha")
    c = BriefRef.new("beta")
    m.attach(a)
    m.attach(b)
    m.attach(c)
    alphas = m.by_topic("alpha")
    assert len(alphas) == 2


def test_record_impact_accumulates() -> None:
    m = _make()
    a = BriefRef.new("a")
    b = BriefRef.new("b")
    m.attach(a)
    m.attach(b)
    m.record_impact(a.id, b.id, weight=0.4)
    m.record_impact(a.id, b.id, weight=0.6)
    assert m.impact_weight(a.id, b.id) == pytest.approx(1.0)
    assert m.impact_weight(b.id, a.id) == 0.0  # 方向あり


def test_record_impact_self_rejected() -> None:
    m = _make()
    a = BriefRef.new("a")
    m.attach(a)
    with pytest.raises(ValueError, match="self-impact"):
        m.record_impact(a.id, a.id)


def test_record_impact_unknown_brief_rejected() -> None:
    m = _make()
    a = BriefRef.new("a")
    m.attach(a)
    with pytest.raises(KeyError):
        m.record_impact(a.id, "nonexistent")


def test_tick_emits_events_above_threshold() -> None:
    m = _make()
    a = BriefRef.new("a")
    b = BriefRef.new("b")
    m.attach(a)
    m.attach(b)
    # 閾値未満
    m.record_impact(a.id, b.id, weight=0.5)
    assert m.tick() == []
    # 閾値以上
    m.record_impact(a.id, b.id, weight=0.6)
    events = m.tick()
    assert len(events) == 1
    assert events[0].src_brief_id == a.id
    assert events[0].dst_brief_id == b.id
    assert events[0].weight == pytest.approx(1.1)


def test_freeze_excludes_from_tick() -> None:
    m = _make()
    a = BriefRef.new("a")
    b = BriefRef.new("b")
    m.attach(a)
    m.attach(b)
    m.record_impact(a.id, b.id, weight=2.0)
    m.freeze(b.id)
    assert m.is_frozen(b.id)
    events = m.tick()
    assert events == []
    m.thaw(b.id)
    events_after = m.tick()
    assert len(events_after) == 1


def test_detach_removes_coherence_edges() -> None:
    m = _make()
    a = BriefRef.new("a")
    b = BriefRef.new("b")
    m.attach(a)
    m.attach(b)
    m.record_impact(a.id, b.id, weight=2.0)
    m.detach(b.id)
    assert m.impact_weight(a.id, b.id) == 0.0


def test_latest_events_history() -> None:
    m = _make()
    a = BriefRef.new("a")
    b = BriefRef.new("b")
    m.attach(a)
    m.attach(b)
    m.record_impact(a.id, b.id, weight=2.0)
    m.tick()
    m.record_impact(a.id, b.id, weight=2.0)
    m.tick()
    history = m.latest_events(n=10)
    assert len(history) == 2
    assert all(isinstance(e, CoherenceEvent) for e in history)
