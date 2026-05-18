# SPDX-License-Identifier: Apache-2.0
"""COG-MESH-01 拡張テスト — M8.8 graph analytics + 実 Brief 統合."""

from __future__ import annotations

import pytest

from llive.brief.types import Brief
from llive.cognitive_mesh.brief_containers import BriefRef
from llive.cognitive_mesh.multi_brief import MultiBriefCoherenceManager


def _attach_n(mgr: MultiBriefCoherenceManager, n: int) -> list[BriefRef]:
    refs = []
    for i in range(n):
        ref = BriefRef(id=f"b-{i:03d}", topic=f"topic-{i}", payload=None)
        mgr.attach(ref)
        refs.append(ref)
    return refs


def test_shortest_path_simple_chain() -> None:
    mgr = MultiBriefCoherenceManager()
    refs = _attach_n(mgr, 3)
    mgr.record_impact(refs[0].id, refs[1].id, 1.0)
    mgr.record_impact(refs[1].id, refs[2].id, 1.0)
    path = mgr.shortest_path(refs[0].id, refs[2].id)
    assert path == [refs[0].id, refs[1].id, refs[2].id]


def test_shortest_path_same_node() -> None:
    mgr = MultiBriefCoherenceManager()
    _attach_n(mgr, 1)
    assert mgr.shortest_path("b-000", "b-000") == ["b-000"]


def test_shortest_path_unreachable() -> None:
    mgr = MultiBriefCoherenceManager()
    refs = _attach_n(mgr, 3)
    mgr.record_impact(refs[0].id, refs[1].id, 1.0)
    # b-001 から b-002 へエッジなし
    assert mgr.shortest_path(refs[0].id, refs[2].id) is None


def test_shortest_path_unknown_node() -> None:
    mgr = MultiBriefCoherenceManager()
    _attach_n(mgr, 2)
    assert mgr.shortest_path("missing", "b-000") is None
    assert mgr.shortest_path("b-000", "missing") is None


def test_shortest_path_picks_shorter_route() -> None:
    """A→B→C と A→C があれば A→C を返す."""
    mgr = MultiBriefCoherenceManager()
    refs = _attach_n(mgr, 3)
    mgr.record_impact(refs[0].id, refs[1].id, 1.0)
    mgr.record_impact(refs[1].id, refs[2].id, 1.0)
    mgr.record_impact(refs[0].id, refs[2].id, 1.0)
    path = mgr.shortest_path(refs[0].id, refs[2].id)
    assert path == [refs[0].id, refs[2].id]


def test_connected_components_isolated() -> None:
    mgr = MultiBriefCoherenceManager()
    _attach_n(mgr, 3)
    # edge 無し → 全部別成分
    comps = mgr.connected_components()
    sizes = sorted(len(c) for c in comps)
    assert sizes == [1, 1, 1]


def test_connected_components_two_clusters() -> None:
    mgr = MultiBriefCoherenceManager()
    refs = _attach_n(mgr, 4)
    mgr.record_impact(refs[0].id, refs[1].id, 1.0)
    mgr.record_impact(refs[2].id, refs[3].id, 1.0)
    comps = mgr.connected_components()
    sets = sorted([sorted(c) for c in comps])
    assert sets == [[refs[0].id, refs[1].id], [refs[2].id, refs[3].id]]


def test_centrality_scores_sum_to_unity() -> None:
    mgr = MultiBriefCoherenceManager()
    refs = _attach_n(mgr, 3)
    mgr.record_impact(refs[0].id, refs[1].id, 2.0)
    mgr.record_impact(refs[0].id, refs[2].id, 3.0)
    scores = mgr.centrality_scores()
    assert pytest.approx(sum(scores.values()), abs=1e-9) == 1.0
    assert scores[refs[0].id] == pytest.approx(1.0)
    assert scores[refs[1].id] == 0.0
    assert scores[refs[2].id] == 0.0


def test_centrality_scores_empty_graph_returns_zeros() -> None:
    mgr = MultiBriefCoherenceManager()
    refs = _attach_n(mgr, 2)
    scores = mgr.centrality_scores()
    assert scores == {refs[0].id: 0.0, refs[1].id: 0.0}


def test_top_central_briefs() -> None:
    mgr = MultiBriefCoherenceManager()
    refs = _attach_n(mgr, 4)
    mgr.record_impact(refs[0].id, refs[1].id, 5.0)  # high
    mgr.record_impact(refs[2].id, refs[3].id, 1.0)
    top = mgr.top_central_briefs(k=2)
    assert top[0][0] == refs[0].id
    assert top[0][1] > top[1][1]


def test_register_brief_attaches_and_wraps() -> None:
    mgr = MultiBriefCoherenceManager()
    brief = Brief(brief_id="real-001", goal="run nightly bench")
    ref = mgr.register_brief(brief)
    assert ref.id == "real-001"
    assert ref.topic == "run nightly bench"
    assert ref.payload is brief
    # get_brief() で本体取り出し可能
    assert mgr.get_brief("real-001") is brief


def test_register_brief_rejects_duplicate() -> None:
    mgr = MultiBriefCoherenceManager()
    brief = Brief(brief_id="real-001", goal="goal")
    mgr.register_brief(brief)
    with pytest.raises(ValueError, match="already attached"):
        mgr.register_brief(brief)


def test_get_brief_unknown_returns_none() -> None:
    mgr = MultiBriefCoherenceManager()
    assert mgr.get_brief("never-attached") is None


def test_detach_removes_edges() -> None:
    """既存仕様の念押し: detach すると関連 edge も消える."""
    mgr = MultiBriefCoherenceManager()
    refs = _attach_n(mgr, 3)
    mgr.record_impact(refs[0].id, refs[1].id, 1.0)
    mgr.record_impact(refs[1].id, refs[2].id, 1.0)
    mgr.detach(refs[1].id)
    # b-001 関連 edge は消えるべき
    assert mgr.impact_weight(refs[0].id, refs[1].id) == 0.0
    assert mgr.impact_weight(refs[1].id, refs[2].id) == 0.0
