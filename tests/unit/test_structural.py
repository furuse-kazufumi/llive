# SPDX-License-Identifier: Apache-2.0
"""MEM-05: structural memory (Kùzu)."""

from __future__ import annotations

import pytest

from llive.memory.provenance import Provenance
from llive.memory.structural import VALID_EDGE_TYPES, VALID_NODE_TYPES, StructuralMemory


@pytest.fixture
def sm(tmp_path):
    store = StructuralMemory(db_path=tmp_path / "s.kuzu")
    yield store
    store.close()


def _prov(tag="t1") -> Provenance:
    return Provenance(source_type="test", source_id=tag)


def test_add_and_get_node(sm):
    nid = sm.add_node("semantic", payload={"hello": "world"}, provenance=_prov())
    got = sm.get_node(nid)
    assert got is not None
    assert got.memory_type == "semantic"
    assert got.payload["hello"] == "world"
    assert got.provenance is not None and got.provenance.source_type == "test"


def test_add_node_invalid_type(sm):
    with pytest.raises(ValueError):
        sm.add_node("not-a-type")


def test_list_nodes_by_type(sm):
    sm.add_node("semantic", payload={"i": 1})
    sm.add_node("episodic", payload={"i": 2})
    sm.add_node("concept", payload={"i": 3})
    sem_only = sm.list_nodes(memory_type="semantic")
    assert len(sem_only) == 1
    assert sem_only[0].memory_type == "semantic"
    assert sm.count_nodes() == 3
    assert sm.count_nodes(memory_type="concept") == 1


def test_list_nodes_invalid_type(sm):
    with pytest.raises(ValueError):
        sm.list_nodes(memory_type="bad")


def test_add_edge_and_query_neighbors(sm):
    a = sm.add_node("semantic", payload={"v": "a"})
    b = sm.add_node("concept", payload={"v": "b"})
    sm.add_edge(a, b, "linked_concept", weight=0.5, provenance=_prov())
    out = sm.query_neighbors(a, direction="out")
    assert len(out) == 1
    assert out[0].id == b
    inc = sm.query_neighbors(b, direction="in")
    assert len(inc) == 1
    assert inc[0].id == a


def test_query_neighbors_filter_rel(sm):
    a = sm.add_node("semantic", payload={"v": 1})
    b = sm.add_node("semantic", payload={"v": 2})
    c = sm.add_node("semantic", payload={"v": 3})
    sm.add_edge(a, b, "linked_concept")
    sm.add_edge(a, c, "derived_from")
    only_linked = sm.query_neighbors(a, rel_type="linked_concept", direction="out")
    assert {n.id for n in only_linked} == {b}
    only_derived = sm.query_neighbors(a, rel_type="derived_from", direction="out")
    assert {n.id for n in only_derived} == {c}


def test_query_neighbors_both_direction(sm):
    a = sm.add_node("semantic")
    b = sm.add_node("semantic")
    c = sm.add_node("semantic")
    sm.add_edge(a, b, "co_occurs_with")
    sm.add_edge(c, a, "co_occurs_with")
    both = sm.query_neighbors(a, direction="both")
    assert {n.id for n in both} == {b, c}


def test_query_neighbors_invalid_direction(sm):
    a = sm.add_node("semantic")
    with pytest.raises(ValueError):
        sm.query_neighbors(a, direction="diagonal")


def test_add_edge_invalid_rel(sm):
    a = sm.add_node("semantic")
    b = sm.add_node("semantic")
    with pytest.raises(ValueError):
        sm.add_edge(a, b, "made-up")


def test_delete_node_cascades(sm):
    a = sm.add_node("semantic", payload={"x": 1})
    b = sm.add_node("semantic", payload={"x": 2})
    sm.add_edge(a, b, "co_occurs_with")
    sm.delete_node(a)
    assert sm.get_node(a) is None
    assert sm.get_node(b) is not None
    # b's incoming edge from a should be cascaded
    assert sm.query_neighbors(b, direction="in") == []


def test_get_unknown_node(sm):
    assert sm.get_node("does-not-exist") is None


def test_constants_consistent():
    # safety net: sub-block / loader code paths reference these constants
    assert "semantic" in VALID_NODE_TYPES
    assert "linked_concept" in VALID_EDGE_TYPES
