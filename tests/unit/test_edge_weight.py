"""LLW-AC-10: dynamic edge weight updater."""

from __future__ import annotations

import datetime as _dt
import json

import pytest

from llive.memory.edge_weight import EdgeWeightConfig, EdgeWeightUpdater
from llive.memory.structural import StructuralMemory


@pytest.fixture
def sm(tmp_path):
    s = StructuralMemory(db_path=tmp_path / "s.kuzu")
    yield s
    s.close()


@pytest.fixture
def updater(sm, tmp_path):
    return EdgeWeightUpdater(sm, log_path=tmp_path / "weights.jsonl")


def _two_pages(sm) -> tuple[str, str]:
    a = sm.add_node("concept", payload={"title": "A"})
    b = sm.add_node("concept", payload={"title": "B"})
    return a, b


def test_on_read_hit_increases_weight(sm, updater):
    a, b = _two_pages(sm)
    sm.add_edge(a, b, "linked_concept", weight=0.3)
    n = updater.on_read_hit(a, [b])
    assert n == 1
    edges = updater._fetch_all_edges()
    assert edges[0].weight == pytest.approx(0.32, rel=1e-3)


def test_on_read_hit_no_edge_returns_zero(updater, sm):
    a, b = _two_pages(sm)
    n = updater.on_read_hit(a, [b])
    assert n == 0


def test_on_contradiction_decreases_weight(sm, updater):
    a, b = _two_pages(sm)
    sm.add_edge(a, b, "linked_concept", weight=0.5)
    assert updater.on_contradiction(a, b)
    edges = updater._fetch_all_edges()
    assert edges[0].weight == pytest.approx(0.4, rel=1e-3)


def test_weight_clipped_to_zero(sm, updater):
    a, b = _two_pages(sm)
    sm.add_edge(a, b, "linked_concept", weight=0.06)
    updater.on_contradiction(a, b)  # 0.06 - 0.1 = -0.04 → clipped to 0, below floor → pruned
    edges = updater._fetch_all_edges()
    assert edges == []


def test_dormant_zone_keeps_edge_for_resurrection(sm, updater):
    """Weights between floor (0.02) and min_keep (0.05) should stay as dormant."""
    a, b = _two_pages(sm)
    sm.add_edge(a, b, "linked_concept", weight=0.04)
    # adjustment that lands in dormant zone (above floor, below min_keep)
    updater._adjust(a, b, "linked_concept", -0.005, reason="test")
    edges = updater._fetch_all_edges()
    assert len(edges) == 1
    assert updater.config.floor_weight <= edges[0].weight < updater.config.min_weight_keep


def test_random_boost_can_resurrect(sm, updater):
    import random as _r

    a, b = _two_pages(sm)
    sm.add_edge(a, b, "linked_concept", weight=0.03)  # dormant
    # Force random_boost to always fire so we deterministically observe a boost.
    updater._rng = _r.Random(0)
    updater.config.random_boost_probability = 1.0
    boosted = updater.random_boost()
    assert boosted == 1
    edges = updater._fetch_all_edges()
    assert edges[0].weight > 0.03


def test_visit_count_updates_on_read_hit(sm, updater):
    a, b = _two_pages(sm)
    sm.add_edge(a, b, "linked_concept", weight=0.5)
    assert updater.visit_count(a, b, "linked_concept") == 0
    updater.on_read_hit(a, [b])
    updater.on_read_hit(a, [b])
    assert updater.visit_count(a, b, "linked_concept") == 2
    assert updater.total_visits() == 2


def test_exploration_score_unvisited_edge_higher():
    from llive.memory.edge_weight import EdgeWeightConfig, EdgeWeightUpdater

    # No structural backend needed for pure scoring math
    upd = EdgeWeightUpdater.__new__(EdgeWeightUpdater)
    upd.config = EdgeWeightConfig()
    s_high_visits = upd.exploration_score(weight=0.5, visit_count=100, total_visits=200)
    s_low_visits = upd.exploration_score(weight=0.5, visit_count=0, total_visits=200)
    assert s_low_visits > s_high_visits


def test_rank_neighbors_combines_weight_and_visits(sm, updater):
    a = sm.add_node("concept", payload={"i": 0})
    b = sm.add_node("concept", payload={"i": 1})
    c = sm.add_node("concept", payload={"i": 2})
    # b has higher weight, c is unvisited but lower weight
    sm.add_edge(a, b, "linked_concept", weight=0.6)
    sm.add_edge(a, c, "linked_concept", weight=0.3)
    # Mark b as visited many times
    updater._visit_counts[(a, b, "linked_concept")] = 50
    edges = [(a, b, "linked_concept", 0.6), (a, c, "linked_concept", 0.3)]
    ranked = updater.rank_neighbors(edges, c=2.0)
    # c (unvisited) should bubble up despite lower raw weight
    assert ranked[0][0] == c


def test_weight_clipped_to_one(sm, updater):
    a, b = _two_pages(sm)
    sm.add_edge(a, b, "linked_concept", weight=0.99)
    updater.config.alpha_read = 0.5
    updater.on_read_hit(a, [b])
    edges = updater._fetch_all_edges()
    assert edges[0].weight == 1.0


def test_on_surprise_boost(sm, updater):
    a, b = _two_pages(sm)
    sm.add_edge(a, b, "linked_concept", weight=0.4)
    updater.on_surprise(a, surprise=0.8, neighbor_ids=[b])  # 0.4 + 0.15*0.8 = 0.52
    edges = updater._fetch_all_edges()
    assert edges[0].weight == pytest.approx(0.52, rel=1e-3)


def test_time_decay_reduces_weight(sm, updater):
    a, b = _two_pages(sm)
    sm.add_edge(a, b, "linked_concept", weight=0.6)
    # decay 30 days into the future relative to creation
    later = _dt.datetime.now(_dt.UTC) + _dt.timedelta(days=30)
    updated = updater.apply_time_decay(now=later)
    assert updated >= 1
    edges = updater._fetch_all_edges()
    # exp(-1) ≈ 0.368 → new weight ≈ 0.22
    assert edges[0].weight < 0.3


def test_prune_only_below_floor(sm, updater):
    a, b = _two_pages(sm)
    sm.add_edge(a, b, "linked_concept", weight=0.04)  # in dormant zone (>= floor 0.02, < keep 0.05)
    deleted = updater.prune()
    assert deleted == 0  # dormant edges are preserved
    assert len(updater._fetch_all_edges()) == 1
    # but explicit threshold removes them
    deleted = updater.prune(threshold=0.05)
    assert deleted == 1


def test_log_jsonl_appends(sm, updater, tmp_path):
    a, b = _two_pages(sm)
    sm.add_edge(a, b, "linked_concept", weight=0.5)
    updater.on_read_hit(a, [b])
    log_path = updater.log_path
    payload = json.loads(log_path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert payload["op"] == "adjust"
    assert payload["reason"] == "read_hit"
    assert payload["old_weight"] == 0.5


def test_invalid_rel_type(sm, updater):
    a, b = _two_pages(sm)
    sm.add_edge(a, b, "linked_concept", weight=0.5)
    with pytest.raises(ValueError):
        updater._adjust(a, b, "totally-fake-rel", 0.1, reason="x")


def test_default_config_values():
    cfg = EdgeWeightConfig()
    assert cfg.alpha_read > 0
    assert cfg.alpha_penalty > 0
    assert cfg.min_weight_keep > 0
    assert "linked_concept" in cfg.decay_tau_days
    # AC-11 additions
    assert 0 < cfg.floor_weight < cfg.min_weight_keep
    assert 0 < cfg.random_boost_probability <= 1.0
    assert cfg.ucb_c > 0
