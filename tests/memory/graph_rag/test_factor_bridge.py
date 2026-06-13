# SPDX-License-Identifier: Apache-2.0
"""GraphRAG factor-strength bridge — DIV-02 pytest.

addendum §DIV-02: GraphRAG Node/Edge/Store を ThoughtFactorPerLayerChromosome の
層別 factor strength に写像する bridge。(10,4) shape / 空 store で zero /
hop_decay 効果 / 既存 chromosome に prior を供給 (新 chromosome を作らない)。
"""
from __future__ import annotations

import numpy as np
import pytest

from llive.memory.graph_rag import Edge, GraphRAGStore, Node
from llive.memory.graph_rag.factor_bridge import (
    factor_strength,
    factor_strength_mutation_bias,
    factor_strength_prior,
)
from llive.perf.evolutionary.thought_factor_per_layer import (
    NUM_MEMORY_LAYERS,
    NUM_THOUGHT_FACTORS,
    ThoughtFactorPerLayerChromosome,
)


def _store(hop_decay: float = 0.5) -> GraphRAGStore:
    s = GraphRAGStore(hop_decay=hop_decay)
    s.add_node(Node(id="a", kind="memory", payload={"layer": "working"}))
    s.add_node(Node(id="b", kind="concept", payload={"layer": "long_term"}))
    s.add_node(Node(id="c", kind="concept", payload={}))
    s.add_edge(Edge(src="a", dst="b", relation="factor_structurize", weight=2.0))
    s.add_edge(Edge(src="b", dst="c", relation="factor_exploration", weight=1.0))
    return s


# ---------------------------------------------------------------------------
# shape (10, 4)
# ---------------------------------------------------------------------------


def test_factor_strength_shape() -> None:
    m = factor_strength(_store())
    assert m.shape == (NUM_THOUGHT_FACTORS, NUM_MEMORY_LAYERS) == (10, 4)


def test_factor_strength_dtype_and_range_normalized() -> None:
    m = factor_strength(_store(), normalize=True)
    assert m.dtype == np.float64
    assert m.min() >= 0.0
    assert m.max() <= 1.0


# ---------------------------------------------------------------------------
# 空 store → zero
# ---------------------------------------------------------------------------


def test_empty_store_returns_zero() -> None:
    m = factor_strength(GraphRAGStore())
    assert m.shape == (10, 4)
    assert np.all(m == 0.0)


def test_store_without_layer_payload_returns_zero() -> None:
    """layer 帰属が無い Node のみなら集約 0。"""
    s = GraphRAGStore()
    s.add_node(Node(id="x", kind="concept", payload={}))
    s.add_node(Node(id="y", kind="concept", payload={}))
    s.add_edge(Edge(src="x", dst="y", relation="factor_structurize", weight=5.0))
    assert np.all(factor_strength(s) == 0.0)


# ---------------------------------------------------------------------------
# factor タグ → 正しい行に集約
# ---------------------------------------------------------------------------


def test_structurize_relation_routes_to_factor_row() -> None:
    m = factor_strength(_store(), normalize=False)
    # factor_structurize は THOUGHT_FACTORS[0], factor_exploration は [5]
    assert m[0].sum() > 0.0  # structurize 行に寄与あり
    assert m[5].sum() > 0.0  # exploration 行に寄与あり
    # 他の因子行は寄与なし
    for fi in (1, 2, 3, 4, 6, 7, 8, 9):
        assert m[fi].sum() == pytest.approx(0.0)


def test_payload_factor_tags_fallback() -> None:
    """relation が factor 名でない場合 payload['factor_tags'] を見る。"""
    s = GraphRAGStore()
    s.add_node(
        Node(id="a", kind="memory", payload={"layer": "working", "factor_tags": ["factor_uncertainty"]})
    )
    s.add_node(
        Node(id="b", kind="concept", payload={"layer": "working", "factor_tags": "factor_uncertainty"})
    )
    s.add_edge(Edge(src="a", dst="b", relation="cites", weight=1.0))
    m = factor_strength(s, normalize=False)
    # factor_uncertainty は THOUGHT_FACTORS[4]
    assert m[4].sum() > 0.0


# ---------------------------------------------------------------------------
# hop_decay 効果
# ---------------------------------------------------------------------------


def test_hop_decay_effect_monotonic() -> None:
    """hop_decay が大きいほど遠 hop の寄与が増え総和が大きくなる。"""
    lo = factor_strength(_store(hop_decay=0.2), normalize=False).sum()
    hi = factor_strength(_store(hop_decay=0.9), normalize=False).sum()
    assert hi > lo


def test_max_hops_zero_truncates() -> None:
    """max_hops=1 と max_hops=2 で多 hop 寄与が変わる。"""
    s = _store(hop_decay=0.5)
    near = factor_strength(s, max_hops=1, normalize=False).sum()
    far = factor_strength(s, max_hops=2, normalize=False).sum()
    assert far >= near


# ---------------------------------------------------------------------------
# 既存 chromosome に prior を供給 (新 chromosome を作らない / 40-dim 維持)
# ---------------------------------------------------------------------------


def test_prior_returns_existing_chromosome_type() -> None:
    prior = factor_strength_prior(_store())
    assert isinstance(prior, ThoughtFactorPerLayerChromosome)
    # 40-dim 維持 (10 * 4)
    assert prior.as_flat().shape == (40,)


def test_prior_empty_store_is_baseline() -> None:
    prior = factor_strength_prior(GraphRAGStore(), baseline=0.5)
    assert np.allclose(prior.as_array(), 0.5)


def test_prior_blend_bounds() -> None:
    with pytest.raises(ValueError):
        factor_strength_prior(_store(), blend=1.5)


def test_prior_values_in_unit_range() -> None:
    prior = factor_strength_prior(_store(), blend=1.0)
    arr = prior.as_array()
    assert arr.min() >= 0.0
    assert arr.max() <= 1.0


def test_mutation_bias_inverse_of_strength() -> None:
    """mutation bias は strength が高いほど小さい (1 - strength)。"""
    bias = factor_strength_mutation_bias(_store())
    assert bias.shape == (10, 4)
    assert bias.min() >= 0.0
    assert bias.max() <= 1.0
    strength = factor_strength(_store(), normalize=True)
    assert np.allclose(bias, np.clip(1.0 - strength, 0.0, 1.0))


def test_unknown_factor_tag_rejected() -> None:
    with pytest.raises(ValueError, match="unknown thought factor"):
        factor_strength(_store(), factor_tags=("not_a_factor",))
