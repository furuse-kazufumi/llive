# SPDX-License-Identifier: Apache-2.0
"""PhyTree (EV-26 phylogenetic memory) — 単体テスト.

確認項目:

- Individual ID 計算 (同じ genome は同じ ID; content-addressable)
- 親子関係の record / query (get_parents / get_children)
- ancestors / descendants の正しさ (depth 制御含む)
- pin / restore_extinct の動作
- prune の動作 (pinned は残る, unpinned dead は消える)
- Mermaid 生成のフォーマット
- to_dict / from_dict roundtrip
"""

from __future__ import annotations

import json

import pytest

from llive.perf.evolutionary import (
    Genome,
    GenomeBounds,
    Individual,
    PhyEdge,
    PhyNode,
    PhyTree,
    compute_individual_id,
)

# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _make_individual(values: tuple[float, ...], gen: int = 0) -> Individual:
    bounds = GenomeBounds(lower=(-10.0,) * len(values), upper=(10.0,) * len(values))
    genome = Genome.from_values(list(values), bounds=bounds)
    return Individual.from_genome(genome, birth_generation=gen)


# ---------------------------------------------------------------------------
# content-addressable ID
# ---------------------------------------------------------------------------


def test_compute_individual_id_deterministic() -> None:
    """同じ genome → 同じ ID (uuid とは独立)."""
    ind1 = _make_individual((0.5, 1.2))
    ind2 = _make_individual((0.5, 1.2))
    assert ind1.individual_id != ind2.individual_id, "uuid は別であるべき"
    id1 = compute_individual_id(ind1)
    id2 = compute_individual_id(ind2)
    assert id1 == id2
    assert len(id1) == 64  # SHA-256 hex


def test_compute_individual_id_differs_for_different_genomes() -> None:
    ind1 = _make_individual((0.5, 1.2))
    ind2 = _make_individual((0.5, 1.3))
    assert compute_individual_id(ind1) != compute_individual_id(ind2)


# ---------------------------------------------------------------------------
# PhyEdge / PhyNode
# ---------------------------------------------------------------------------


def test_phyedge_validates_op() -> None:
    with pytest.raises(ValueError, match="unknown op"):
        PhyEdge(parent_id="a" * 64, child_id="b" * 64, op="invalid")


def test_phynode_roundtrip() -> None:
    ind = _make_individual((0.5, 1.2), gen=2)
    nid = compute_individual_id(ind)
    node = PhyNode(individual_id=nid, individual=ind)
    node2 = PhyNode.from_dict(node.to_dict())
    assert node2.individual_id == nid
    assert node2.individual.birth_generation == 2
    assert node2.individual.genome.values == (0.5, 1.2)


def test_phyedge_roundtrip() -> None:
    edge = PhyEdge(
        parent_id="a" * 64,
        child_id="b" * 64,
        op="crossover",
        metadata=(("generation", "3"), ("mutation_rate", "0.05")),
    )
    edge2 = PhyEdge.from_dict(edge.to_dict())
    assert edge2 == edge


# ---------------------------------------------------------------------------
# add_individual + parent/child queries
# ---------------------------------------------------------------------------


def test_add_individual_returns_content_id() -> None:
    tree = PhyTree()
    ind = _make_individual((0.5,))
    nid = tree.add_individual(ind, op="seed")
    assert nid == compute_individual_id(ind)
    assert nid in tree.nodes


def test_add_individual_dedup_same_genome() -> None:
    """同じ genome を 2 回 add すると node は 1 つ (content-addressable)."""
    tree = PhyTree()
    ind1 = _make_individual((0.5,))
    ind2 = _make_individual((0.5,))
    id1 = tree.add_individual(ind1, op="seed")
    id2 = tree.add_individual(ind2, op="seed")
    assert id1 == id2
    assert len(tree.nodes) == 1


def test_add_individual_with_parents() -> None:
    tree = PhyTree()
    parent = _make_individual((0.1,))
    parent_id = tree.add_individual(parent, op="seed")
    child = _make_individual((0.2,))
    child_id = tree.add_individual(child, parents=[parent], op="mutation")

    assert tree.get_parents(child_id) == [parent_id]
    assert tree.get_children(parent_id) == [child_id]
    assert tree.edges[-1].op == "mutation"


def test_add_individual_crossover_two_parents() -> None:
    tree = PhyTree()
    p1 = _make_individual((0.1,))
    p2 = _make_individual((0.2,))
    p1_id = tree.add_individual(p1, op="seed")
    p2_id = tree.add_individual(p2, op="seed")
    child = _make_individual((0.15,))
    child_id = tree.add_individual(child, parents=[p1, p2], op="crossover")

    parents = set(tree.get_parents(child_id))
    assert parents == {p1_id, p2_id}


def test_add_individual_rejects_unknown_op() -> None:
    tree = PhyTree()
    ind = _make_individual((0.5,))
    with pytest.raises(ValueError, match="unknown op"):
        tree.add_individual(ind, op="teleport")


def test_add_individual_dedup_edges() -> None:
    """同じ (parent, child, op, metadata) edge は重複しない."""
    tree = PhyTree()
    parent = _make_individual((0.1,))
    tree.add_individual(parent, op="seed")
    child = _make_individual((0.2,))
    tree.add_individual(child, parents=[parent], op="mutation")
    tree.add_individual(child, parents=[parent], op="mutation")
    # mutation edge は 1 つ (seed edge は parents 空なので edge なし)
    assert len(tree.edges) == 1


# ---------------------------------------------------------------------------
# ancestors / descendants
# ---------------------------------------------------------------------------


def _build_lineage_chain(tree: PhyTree, n: int) -> list[str]:
    """0 → 1 → 2 → ... → n-1 の直系 chain. ID の list を返す."""
    ids: list[str] = []
    prev: Individual | None = None
    for i in range(n):
        ind = _make_individual((float(i),), gen=i)
        parents = [prev] if prev is not None else []
        nid = tree.add_individual(ind, parents=parents, op="seed" if i == 0 else "mutation")
        ids.append(nid)
        prev = ind
    return ids


def test_get_ancestors_full() -> None:
    tree = PhyTree()
    ids = _build_lineage_chain(tree, 5)
    # ids[4] の先祖は ids[0..3]
    ancestors = tree.get_ancestors(ids[4])
    assert ancestors == set(ids[:4])


def test_get_ancestors_depth_limited() -> None:
    tree = PhyTree()
    ids = _build_lineage_chain(tree, 5)
    # depth=2 → 直接の親 + 祖父 のみ
    ancestors = tree.get_ancestors(ids[4], depth=2)
    assert ancestors == {ids[3], ids[2]}


def test_get_ancestors_depth_zero_returns_empty() -> None:
    tree = PhyTree()
    ids = _build_lineage_chain(tree, 3)
    assert tree.get_ancestors(ids[2], depth=0) == set()


def test_get_descendants_full() -> None:
    tree = PhyTree()
    ids = _build_lineage_chain(tree, 5)
    descendants = tree.get_descendants(ids[0])
    assert descendants == set(ids[1:])


def test_get_descendants_depth_limited() -> None:
    tree = PhyTree()
    ids = _build_lineage_chain(tree, 5)
    descendants = tree.get_descendants(ids[0], depth=2)
    assert descendants == {ids[1], ids[2]}


def test_get_ancestors_rejects_negative_depth() -> None:
    tree = PhyTree()
    ids = _build_lineage_chain(tree, 2)
    with pytest.raises(ValueError, match="depth"):
        tree.get_ancestors(ids[1], depth=-1)


# ---------------------------------------------------------------------------
# pin / restore_extinct
# ---------------------------------------------------------------------------


def test_pin_and_unpin() -> None:
    tree = PhyTree()
    ind = _make_individual((0.5,))
    nid = tree.add_individual(ind, op="seed")
    assert nid not in tree.pinned
    tree.pin(nid)
    assert nid in tree.pinned
    tree.unpin(nid)
    assert nid not in tree.pinned


def test_pin_unknown_id_raises() -> None:
    tree = PhyTree()
    with pytest.raises(KeyError):
        tree.pin("0" * 64)


def test_restore_extinct_returns_individual() -> None:
    tree = PhyTree()
    ind = _make_individual((0.7,), gen=3)
    nid = tree.add_individual(ind, op="seed")
    restored = tree.restore_extinct(nid)
    assert restored.birth_generation == 3
    assert restored.genome.values == (0.7,)


def test_restore_extinct_missing_id_raises() -> None:
    tree = PhyTree()
    with pytest.raises(KeyError, match="truly extinct"):
        tree.restore_extinct("0" * 64)


# ---------------------------------------------------------------------------
# prune
# ---------------------------------------------------------------------------


def test_prune_removes_dead_unpinned() -> None:
    tree = PhyTree()
    ids = _build_lineage_chain(tree, 5)
    # ids[4] のみ alive
    deleted = tree.prune({ids[4]}, keep_pinned=True)
    assert deleted == set(ids[:4])
    assert set(tree.nodes) == {ids[4]}
    # 全 edge は両端 (parent も child も) 必要なので全削除
    assert tree.edges == []


def test_prune_keeps_pinned() -> None:
    tree = PhyTree()
    ids = _build_lineage_chain(tree, 5)
    tree.pin(ids[0])
    tree.pin(ids[2])
    deleted = tree.prune({ids[4]}, keep_pinned=True)
    # ids[0], ids[2] は pinned で残る. ids[1], ids[3] は削除.
    assert ids[0] in tree.nodes
    assert ids[2] in tree.nodes
    assert ids[4] in tree.nodes
    assert ids[1] not in tree.nodes
    assert ids[3] not in tree.nodes
    assert deleted == {ids[1], ids[3]}


def test_prune_keep_pinned_false_deletes_everything_unrelated() -> None:
    tree = PhyTree()
    ids = _build_lineage_chain(tree, 3)
    tree.pin(ids[0])
    deleted = tree.prune({ids[2]}, keep_pinned=False)
    assert ids[0] not in tree.nodes  # pinned でも削除
    assert ids[0] not in tree.pinned  # pin も解除
    assert deleted == {ids[0], ids[1]}


def test_prune_restore_after_pin() -> None:
    """pin + prune の後でも restore_extinct で取り出せる."""
    tree = PhyTree()
    ids = _build_lineage_chain(tree, 5)
    tree.pin(ids[0])
    tree.prune({ids[4]}, keep_pinned=True)
    # ids[0] は pinned なので残っている → restore 可能
    restored = tree.restore_extinct(ids[0])
    assert restored.birth_generation == 0


# ---------------------------------------------------------------------------
# Mermaid render
# ---------------------------------------------------------------------------


def test_to_mermaid_empty_tree() -> None:
    tree = PhyTree()
    md = tree.to_mermaid()
    assert "graph TD" in md
    assert "empty[No individuals]" in md


def test_to_mermaid_contains_nodes_and_edges() -> None:
    tree = PhyTree()
    parent = _make_individual((0.1,), gen=0)
    parent_id = tree.add_individual(parent, op="seed")
    child = _make_individual((0.2,), gen=1)
    child_id = tree.add_individual(child, parents=[parent], op="mutation")

    md = tree.to_mermaid(title="test tree")
    assert "%% test tree" in md
    assert "graph TD" in md
    # 短縮 ID で node が出る
    assert f"n_{parent_id[:8]}" in md
    assert f"n_{child_id[:8]}" in md
    # edge label に op
    assert "|mutation|" in md


def test_to_mermaid_highlights_pinned() -> None:
    tree = PhyTree()
    ind = _make_individual((0.5,), gen=0)
    nid = tree.add_individual(ind, op="seed")
    tree.pin(nid)
    md = tree.to_mermaid()
    assert f"class n_{nid[:8]} pinned" in md
    assert "classDef pinned" in md


def test_to_mermaid_ghost_for_extinct_parent() -> None:
    """parent が prune 済 + 未 pin の場合, edge には ghost node が出る."""
    tree = PhyTree()
    ids = _build_lineage_chain(tree, 3)
    # ids[0] を絶滅させる (pin せず prune)
    # ids[1], ids[2] を alive にする
    tree.prune({ids[1], ids[2]}, keep_pinned=False)
    # ids[0] → ids[1] の edge は ids[0] が消えたので edge も消える (prune の仕様)
    # よって ghost が出るのは別シナリオ: 直接 edge 追加して node なし parent を作る
    tree2 = PhyTree()
    child = _make_individual((0.5,))
    child_id = tree2.add_individual(child, op="seed")
    # 後付けで「ghost parent からの edge」を直接 inject
    tree2.edges.append(
        PhyEdge(parent_id="f" * 64, child_id=child_id, op="mutation")
    )
    md = tree2.to_mermaid()
    assert "ghost_" in md
    assert "(extinct)" in md


# ---------------------------------------------------------------------------
# serialize roundtrip
# ---------------------------------------------------------------------------


def test_to_dict_from_dict_roundtrip() -> None:
    tree = PhyTree()
    ids = _build_lineage_chain(tree, 4)
    tree.pin(ids[1])

    data = tree.to_dict()
    # JSON 化できることも確認
    json_str = json.dumps(data)
    restored_data = json.loads(json_str)
    tree2 = PhyTree.from_dict(restored_data)

    assert set(tree2.nodes) == set(tree.nodes)
    assert len(tree2.edges) == len(tree.edges)
    assert tree2.pinned == tree.pinned
    # ancestors も保たれる
    assert tree2.get_ancestors(ids[3]) == tree.get_ancestors(ids[3])
