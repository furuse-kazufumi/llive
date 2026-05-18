# SPDX-License-Identifier: Apache-2.0
"""Tests for COG-MESH-10 Mesh5W1H + Granularity Hierarchy.

requirements_v0.8_cognitive_mesh.md §3 COG-MESH-10 の API 凍結.
"""

from __future__ import annotations

import pytest

from llive.cognitive_mesh.mesh_5w1h import (
    ALL_CHANNELS,
    GRANULARITY_ORDER,
    Granularity,
    Mesh5W1HEdge,
    Mesh5W1HGraph,
    Mesh5W1HNode,
    annotate_5w1h,
    channel_name,
    granularity_of,
    is_finer,
)

# ---------------------------------------------------------------------------
# Enum + namespace 定数
# ---------------------------------------------------------------------------


def test_all_5w1h_nodes_present() -> None:
    assert {n.value for n in Mesh5W1HNode} == {
        "who", "what", "when", "where", "why", "how"
    }


def test_channel_name_format() -> None:
    assert channel_name(Mesh5W1HNode.WHO) == "mesh.who"
    assert channel_name(Mesh5W1HNode.HOW) == "mesh.how"


def test_all_channels_count() -> None:
    assert len(ALL_CHANNELS) == 6
    assert "mesh.who" in ALL_CHANNELS
    assert "mesh.how" in ALL_CHANNELS


def test_granularity_order_count() -> None:
    assert len(GRANULARITY_ORDER) == 6
    assert GRANULARITY_ORDER[0] == Granularity.WORD
    assert GRANULARITY_ORDER[-1] == Granularity.TOPIC


def test_is_finer() -> None:
    assert is_finer(Granularity.WORD, Granularity.SENTENCE) is True
    assert is_finer(Granularity.TOPIC, Granularity.WORD) is False
    assert is_finer(Granularity.PHRASE, Granularity.PHRASE) is False


# ---------------------------------------------------------------------------
# annotate_5w1h
# ---------------------------------------------------------------------------


def test_annotate_finds_who_keywords() -> None:
    result = annotate_5w1h("私が build を完了した")
    assert "私" in result[Mesh5W1HNode.WHO]


def test_annotate_finds_when_keywords() -> None:
    result = annotate_5w1h("今日 build を完了した")
    assert any("今日" in kw for kw in result[Mesh5W1HNode.WHEN])


def test_annotate_returns_empty_for_unrelated_text() -> None:
    result = annotate_5w1h("foo bar baz")
    # 全部空のはず (短いキーワードに引っかからない)
    total = sum(len(v) for v in result.values())
    assert total == 0


def test_annotate_finds_multiple_nodes() -> None:
    result = annotate_5w1h("私は今日ここで build を完了した")
    # 私 (WHO) + 今日 (WHEN) + ここ (WHERE) が拾える
    assert result[Mesh5W1HNode.WHO]
    assert result[Mesh5W1HNode.WHEN]
    assert result[Mesh5W1HNode.WHERE]


# ---------------------------------------------------------------------------
# granularity_of
# ---------------------------------------------------------------------------


def test_granularity_word_for_short_token() -> None:
    assert granularity_of("hello") == Granularity.WORD


def test_granularity_phrase_for_medium_token() -> None:
    assert granularity_of("a short phrase here") == Granularity.PHRASE


def test_granularity_paragraph_for_long_text() -> None:
    text = "a" * 200
    assert granularity_of(text) == Granularity.PARAGRAPH


def test_granularity_topic_for_very_long() -> None:
    text = "a" * 500
    assert granularity_of(text) == Granularity.TOPIC


# ---------------------------------------------------------------------------
# Mesh5W1HGraph
# ---------------------------------------------------------------------------


def test_graph_link_and_weight() -> None:
    g = Mesh5W1HGraph()
    g.link(Mesh5W1HNode.WHO, Mesh5W1HNode.WHAT, weight=0.5)
    g.link(Mesh5W1HNode.WHO, Mesh5W1HNode.WHAT, weight=0.3)
    assert g.weight(Mesh5W1HNode.WHO, Mesh5W1HNode.WHAT) == pytest.approx(0.8)
    assert g.weight(Mesh5W1HNode.WHAT, Mesh5W1HNode.WHO) == 0.0


def test_graph_rejects_self_loop() -> None:
    g = Mesh5W1HGraph()
    with pytest.raises(ValueError, match="self-loops"):
        g.link(Mesh5W1HNode.WHO, Mesh5W1HNode.WHO)


def test_graph_neighbors() -> None:
    g = Mesh5W1HGraph()
    g.link(Mesh5W1HNode.WHO, Mesh5W1HNode.WHAT)
    g.link(Mesh5W1HNode.WHO, Mesh5W1HNode.WHEN)
    neighbors = set(g.neighbors(Mesh5W1HNode.WHO))
    assert neighbors == {Mesh5W1HNode.WHAT, Mesh5W1HNode.WHEN}


def test_graph_edges_export() -> None:
    g = Mesh5W1HGraph()
    g.link(Mesh5W1HNode.WHO, Mesh5W1HNode.WHAT, 0.6)
    edges = g.edges()
    assert len(edges) == 1
    edge = edges[0]
    assert isinstance(edge, Mesh5W1HEdge)
    assert edge.src == Mesh5W1HNode.WHO
    assert edge.dst == Mesh5W1HNode.WHAT
    assert edge.weight == 0.6
