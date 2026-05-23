# SPDX-License-Identifier: Apache-2.0
"""GraphRAG factor-strength bridge — llive v0.F DIV-02 (genome diversity addendum).

``src/llive/memory/graph_rag/`` の Node / Edge / GraphRAGStore を
:class:`~llive.perf.evolutionary.thought_factor_per_layer.ThoughtFactorPerLayerChromosome`
の **層別 factor strength** に写像する **bridge**。新 chromosome は作らず、
既存 chromosome の **初期化 prior / mutation bias** を供給する形に限定する。

> **independence / extend-only (addendum §1-3 / premap §2.3-4)**
>
> 本 module は GraphRAGStore (`store.py`) と ThoughtFactorPerLayerChromosome を
> **import して使うのみ**。両者を結ぶ ``factor_strength`` 関数を add するだけで、
> どちらの class も改変しない。**4 層メモリ × factor 進化を結ぶ llive 独自の発想**
> (mainstream GA には無い)。40-dim を維持し新 dim を足さない。

# 写像 (addendum §DIV-02)

各 memory layer に属する Node 集合 ``N_L`` を取り、thought-factor タグ
(Node.payload / Edge.relation 内) ごとに edge weight を hop_decay 累乗で集約:

    s(f, L) = Σ_{e ∈ Edges(N_L), tag(e)=f} e.weight · hop_decay^{hop(e)}

正規化して ``c_factors[f, L]`` への bias / prior として供給する。結果 shape は
``(NUM_THOUGHT_FACTORS, NUM_MEMORY_LAYERS)`` = (10, 4)。

# layer / factor タグの読み出し規約

* **layer 帰属**: ``Node.payload["layer"]`` が ``layer_names`` のいずれかに一致
  する Node を ``N_L`` とみなす。未指定 / 不一致 Node はどの層にも属さない。
* **factor タグ**: edge の factor タグは以下の優先順で読む:
    1. ``Edge.relation`` が thought factor 名 (``factor_*``) と一致 → そのタグ。
    2. それ以外は端点 Node の ``payload["factor_tags"]`` (str or list[str]) を見る。
  どの factor タグにも紐付かない edge は集約に寄与しない。
* **hop**: bridge は seed Node から hop 距離を BFS で測り ``hop_decay^hop`` で減衰。
  store の ``hop_decay`` をそのまま使う (新 retrieval API を足さない)。

References:
* addendum: ``docs/requirements_v0.F_genome_diversity_addendum.md`` §DIV-02.
* premap: ``docs/SPEC_COHERENCE_v0.J_premap.md`` §2.2, §2.3-4.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Sequence

import numpy as np

# --- 既存資産 (import only — 改変しない) -----------------------------------
from llive.memory.graph_rag.store import GraphRAGStore
from llive.perf.evolutionary.persona import THOUGHT_FACTORS
from llive.perf.evolutionary.thought_factor_per_layer import (
    DEFAULT_MEMORY_LAYER_NAMES,
    NUM_MEMORY_LAYERS,
    NUM_THOUGHT_FACTORS,
    ThoughtFactorPerLayerChromosome,
)

#: Edge.relation / payload tag をどの factor index に対応づけるか (THOUGHT_FACTORS 順)。
_FACTOR_INDEX: dict[str, int] = {name: i for i, name in enumerate(THOUGHT_FACTORS)}


def _node_layer(node, layer_names: Sequence[str]) -> str | None:
    """Node の所属 layer 名を返す。``payload["layer"]`` を見る。不一致は None。"""
    layer = node.payload.get("layer")
    if isinstance(layer, str) and layer in layer_names:
        return layer
    return None


def _edge_factor_tags(store: GraphRAGStore, edge) -> set[str]:
    """1 edge の factor タグ集合を返す (relation → 端点 payload の順)。"""
    tags: set[str] = set()
    if edge.relation in _FACTOR_INDEX:
        tags.add(edge.relation)
    if tags:
        return tags
    # fallback: 端点 Node の payload["factor_tags"]
    for nid in (edge.src, edge.dst):
        node = store.get_node(nid)
        if node is None:
            continue
        raw = node.payload.get("factor_tags")
        if isinstance(raw, str):
            if raw in _FACTOR_INDEX:
                tags.add(raw)
        elif isinstance(raw, (list, tuple)):
            for t in raw:
                if isinstance(t, str) and t in _FACTOR_INDEX:
                    tags.add(t)
    return tags


def _hop_distances(store: GraphRAGStore, seed_id: str, max_hops: int) -> dict[str, int]:
    """seed から各 Node への最短 hop 距離 (undirected BFS, <= max_hops)。"""
    if seed_id not in store._nodes:  # noqa: SLF001 — bridge は store の隣接を読む
        return {}
    dist: dict[str, int] = {seed_id: 0}
    frontier: deque[tuple[str, int]] = deque([(seed_id, 0)])
    while frontier:
        cur, d = frontier.popleft()
        if d >= max_hops:
            continue
        for edge in store._out.get(cur, []) + store._in.get(cur, []):  # noqa: SLF001
            other = edge.dst if edge.src == cur else edge.src
            if other in dist:
                continue
            dist[other] = d + 1
            frontier.append((other, d + 1))
    return dist


def factor_strength(
    store: GraphRAGStore,
    layer_names: Sequence[str] = DEFAULT_MEMORY_LAYER_NAMES,
    factor_tags: Sequence[str] = THOUGHT_FACTORS,
    *,
    max_hops: int = 2,
    normalize: bool = True,
) -> np.ndarray:
    """GraphRAG store → (10, 4) factor strength matrix。

    各 memory layer に属する Node を seed として、その近傍 edge を thought-factor
    タグごとに ``edge.weight * hop_decay^hop`` で集約する。

    Args:
        store: GraphRAGStore (既存実装、改変しない)。
        layer_names: 列順となる memory layer 名 (default 4 層)。
        factor_tags: 行順となる factor 名 (default THOUGHT_FACTORS 10 個)。
        max_hops: seed からの集約 hop 上限。
        normalize: True なら matrix 全体を最大値で割り [0, 1] に正規化する。
            空 store / 全 0 のときは zero matrix のまま返す。

    Returns:
        np.ndarray shape ``(len(factor_tags), len(layer_names))``。
        空 store では全要素 0。``ThoughtFactorPerLayerChromosome.from_array()`` の
        prior / mutation bias に渡せる形 (値域 [0, 1])。

    Raises:
        ValueError: factor_tags に未知の factor 名が含まれる場合。
    """
    n_f = len(factor_tags)
    n_l = len(layer_names)
    factor_pos: dict[str, int] = {}
    for fi, fname in enumerate(factor_tags):
        if fname not in _FACTOR_INDEX:
            raise ValueError(f"unknown thought factor tag: {fname!r}")
        factor_pos[fname] = fi

    strength = np.zeros((n_f, n_l), dtype=np.float64)
    if len(store) == 0:
        return strength

    hop_decay = store.hop_decay
    layer_pos = {name: j for j, name in enumerate(layer_names)}

    # 各 layer の seed Node を起点に集約
    for node_id, node in store._nodes.items():  # noqa: SLF001 — bridge reads adjacency
        layer = _node_layer(node, layer_names)
        if layer is None:
            continue
        li = layer_pos[layer]
        dist = _hop_distances(store, node_id, max_hops)
        # seed の近傍 edge を走査
        for other_id, hop in dist.items():
            if hop == 0:
                continue
            for edge in store._out.get(other_id, []) + store._in.get(other_id, []):  # noqa: SLF001
                tags = _edge_factor_tags(store, edge)
                if not tags:
                    continue
                contribution = max(edge.weight, 0.0) * (hop_decay ** hop)
                for tag in tags:
                    fi = factor_pos.get(tag)
                    if fi is not None:
                        strength[fi, li] += contribution
        # seed Node 自身に直結する edge (hop 1 相当の direct weight)
        for edge in store._out.get(node_id, []) + store._in.get(node_id, []):  # noqa: SLF001
            tags = _edge_factor_tags(store, edge)
            if not tags:
                continue
            contribution = max(edge.weight, 0.0) * hop_decay
            for tag in tags:
                fi = factor_pos.get(tag)
                if fi is not None:
                    strength[fi, li] += contribution

    if normalize:
        peak = float(strength.max())
        if peak > 0.0:
            strength = strength / peak
    return strength


def factor_strength_prior(
    store: GraphRAGStore,
    layer_names: Sequence[str] = DEFAULT_MEMORY_LAYER_NAMES,
    *,
    max_hops: int = 2,
    blend: float = 1.0,
    baseline: float = 0.5,
) -> ThoughtFactorPerLayerChromosome:
    """factor_strength を既存 chromosome の **初期化 prior** に変換する。

    新 chromosome は作らず、既存 ``ThoughtFactorPerLayerChromosome.from_array()``
    に prior matrix を渡す (extend-only)。空 store では全 cell が ``baseline`` の
    中立 chromosome を返す。

    Args:
        store: GraphRAGStore。
        layer_names: メモリ層名。
        max_hops: 集約 hop 上限。
        blend: prior と baseline の混合比 ``blend*strength + (1-blend)*baseline``。
            1.0 で strength のみ、0.0 で baseline のみ。
        baseline: prior が無い cell の中立値 (chromosome default と同じ 0.5)。

    Returns:
        ThoughtFactorPerLayerChromosome (40-dim 維持、値域 [0, 1])。

    Raises:
        ValueError: blend が [0, 1] 外 / layer 数が NUM_MEMORY_LAYERS 不一致時は
            chromosome 側 __post_init__ が検証する。
    """
    if not (0.0 <= blend <= 1.0):
        raise ValueError(f"blend must be in [0, 1], got {blend}")
    strength = factor_strength(
        store, layer_names=layer_names, max_hops=max_hops, normalize=True
    )
    prior = blend * strength + (1.0 - blend) * baseline
    prior = np.clip(prior, 0.0, 1.0)
    return ThoughtFactorPerLayerChromosome.from_array(
        prior, layer_names=tuple(layer_names)
    )


def factor_strength_mutation_bias(
    store: GraphRAGStore,
    layer_names: Sequence[str] = DEFAULT_MEMORY_LAYER_NAMES,
    *,
    max_hops: int = 2,
) -> np.ndarray:
    """mutation step-size bias 用の (10, 4) 重み matrix を返す。

    factor strength が高い cell ほど探索を絞る (= 1 - strength を bias とする)
    使い方を想定。chromosome は改変せず、呼び出し側が step_size に掛けて使う。

    Returns:
        np.ndarray shape (10, 4)、値域 [0, 1]。strength が高いほど小さい値。
    """
    strength = factor_strength(
        store, layer_names=layer_names, max_hops=max_hops, normalize=True
    )
    return np.clip(1.0 - strength, 0.0, 1.0)


__all__ = [
    "NUM_MEMORY_LAYERS",
    "NUM_THOUGHT_FACTORS",
    "factor_strength",
    "factor_strength_mutation_bias",
    "factor_strength_prior",
]
