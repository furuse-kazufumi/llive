# SPDX-License-Identifier: Apache-2.0
"""GraphRAG skeleton smoke tests (taxonomy 優先度 #2).

Exercises the in-memory hybrid retrieval store: node/edge mutation,
hybrid query top-k, hop-bounded neighbours, relation filtering,
serialization round-trip, and empty-store behaviour.
"""

from __future__ import annotations

import numpy as np

from llive.memory.graph_rag import Edge, GraphRAGStore, Node


def _emb(*vals: float) -> np.ndarray:
    return np.asarray(vals, dtype=np.float32)


def _build_chain() -> GraphRAGStore:
    """a --rel--> b --rel--> c --other--> d  (a,b,c lexically similar)."""
    store = GraphRAGStore(alpha=0.4, hop_decay=0.5)
    store.add_node(Node("a", "concept", {"text": "alpha topic"}, _emb(1.0, 0.0, 0.0)))
    store.add_node(Node("b", "concept", {"text": "beta topic"}, _emb(0.9, 0.1, 0.0)))
    store.add_node(Node("c", "entity", {"text": "gamma"}, _emb(0.0, 1.0, 0.0)))
    store.add_node(Node("d", "memory", {"text": "delta"}, _emb(0.0, 0.0, 1.0)))
    store.add_edge(Edge("a", "b", "cites", weight=1.0))
    store.add_edge(Edge("b", "c", "cites", weight=1.0))
    store.add_edge(Edge("c", "d", "part_of", weight=1.0))
    return store


def test_add_node_and_edge_basic():
    store = GraphRAGStore()
    store.add_node(Node("n1", "concept", {"text": "hello"}))
    store.add_node(Node("n2", "entity", {"text": "world"}))
    store.add_edge(Edge("n1", "n2", "mentions"))
    assert len(store) == 2
    assert store.get_node("n1") is not None
    assert store.get_node("missing") is None


def test_add_edge_requires_existing_nodes():
    store = GraphRAGStore()
    store.add_node(Node("only", "concept", {}))
    import pytest

    with pytest.raises(KeyError):
        store.add_edge(Edge("only", "ghost", "rel"))
    with pytest.raises(KeyError):
        store.add_edge(Edge("ghost", "only", "rel"))


def test_query_returns_k_results():
    store = _build_chain()
    results = store.query("alpha", k=2, max_hops=2, query_embedding=_emb(1.0, 0.0, 0.0))
    assert len(results) == 2
    # all entries are (Node, float) tuples sorted descending
    nodes = [n for n, _ in results]
    scores = [s for _, s in results]
    assert all(isinstance(n, Node) for n in nodes)
    assert scores == sorted(scores, reverse=True)
    # node "a" (exact embedding match) should rank first
    assert results[0][0].id == "a"


def test_query_k_caps_at_node_count():
    store = _build_chain()
    results = store.query("alpha", k=100, query_embedding=_emb(1.0, 0.0, 0.0))
    assert len(results) == 4


def test_max_hops_zero_disables_propagation():
    """With max_hops=0 proximity is seed-only → pure embedding ranking."""
    store = _build_chain()
    q = _emb(1.0, 0.0, 0.0)
    hop0 = dict((n.id, s) for n, s in store.query("x", k=4, max_hops=0, query_embedding=q))
    hop2 = dict((n.id, s) for n, s in store.query("x", k=4, max_hops=2, query_embedding=q))
    # node "c" has no embedding similarity to q, so at hop0 it only gets
    # proximity from itself (0), while at hop2 it receives spread from a/b.
    assert hop2["c"] > hop0["c"]
    # node "a" still ranks but hop2 != hop0 for downstream nodes
    assert hop0["d"] == 0.0 or hop2["d"] >= hop0["d"]


def test_neighbors_relation_filter():
    store = _build_chain()
    # 1-hop neighbours of "b" via any relation: a, c
    all_1 = {n.id for n in store.neighbors("b", hops=1)}
    assert all_1 == {"a", "c"}
    # only "cites" relation: still a, c (both edges are cites)
    cites = {n.id for n in store.neighbors("b", hops=1, relation_filter="cites")}
    assert cites == {"a", "c"}
    # only "part_of": none touch b directly
    part = {n.id for n in store.neighbors("b", hops=1, relation_filter="part_of")}
    assert part == set()
    # 2-hop from a reaches c (a-b-c)
    two = {n.id for n in store.neighbors("a", hops=2)}
    assert "c" in two


def test_neighbors_hops_zero_or_missing():
    store = _build_chain()
    assert store.neighbors("a", hops=0) == []
    assert store.neighbors("nonexistent", hops=2) == []


def test_to_dict_from_dict_roundtrip():
    store = _build_chain()
    d = store.to_dict()
    restored = GraphRAGStore.from_dict(d)
    assert len(restored) == len(store)
    assert restored.alpha == store.alpha
    assert restored.hop_decay == store.hop_decay
    # node payload + embedding survive
    a = restored.get_node("a")
    assert a is not None
    assert a.payload["text"] == "alpha topic"
    assert a.embedding is not None
    np.testing.assert_allclose(a.embedding, _emb(1.0, 0.0, 0.0), rtol=1e-5)
    # edges survive: b reachable from a
    assert {n.id for n in restored.neighbors("a", hops=1)} == {"b"}
    # query still works on restored store
    results = restored.query("alpha", k=2, query_embedding=_emb(1.0, 0.0, 0.0))
    assert len(results) == 2


def test_empty_store_query_returns_empty():
    store = GraphRAGStore()
    assert store.query("anything", k=5) == []
    assert store.neighbors("x") == []
    assert len(store) == 0


def test_lexical_fallback_without_embedding():
    """No query_embedding → lexical seed selection from payload."""
    store = GraphRAGStore(alpha=0.4)
    store.add_node(Node("p", "concept", {"text": "quantum entanglement"}))
    store.add_node(Node("q", "concept", {"text": "classical mechanics"}))
    store.add_edge(Edge("p", "q", "contrasts"))
    results = store.query("quantum", k=2)
    assert len(results) == 2
    # "p" matches lexically and should rank first
    assert results[0][0].id == "p"


def test_node_serialization_handles_none_embedding():
    n = Node("x", "event", {"k": "v"})
    d = n.to_dict()
    assert d["embedding"] is None
    back = Node.from_dict(d)
    assert back.id == "x"
    assert back.kind == "event"
    assert back.embedding is None
    assert back.payload == {"k": "v"}


def test_invalid_alpha_and_hop_decay():
    import pytest

    with pytest.raises(ValueError):
        GraphRAGStore(alpha=1.5)
    with pytest.raises(ValueError):
        GraphRAGStore(hop_decay=0.0)
