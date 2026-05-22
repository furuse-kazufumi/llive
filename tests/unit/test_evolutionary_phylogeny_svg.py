# SPDX-License-Identifier: Apache-2.0
"""PhyTree.to_animated_svg() — animated SVG renderer の単体テスト.

確認項目:

- Empty PhyTree → 最低限の SVG (背景 + 中央 placeholder text) を出力
- 1 個体 PhyTree → circle が含まれる
- 親子関係あり → edge (<path>) が含まれる
- pinned node → 二重円 (ring + main circle) または class="pinned" が含まれる
- 出力 SVG は XML として valid (xml.etree.ElementTree でパース可能)
- viewBox は 800x240 (default) で統一
- aria-label / <title> / <desc> 要素が必ず含まれる (accessibility)
- JavaScript (script tag, on* handler) を一切含まない
- layout='top_down' でも valid
- layout 不正値は ValueError
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import pytest

from llive.perf.evolutionary import (
    Genome,
    GenomeBounds,
    Individual,
    PhyTree,
)

# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _make_individual(values: tuple[float, ...], gen: int = 0) -> Individual:
    bounds = GenomeBounds(lower=(-10.0,) * len(values), upper=(10.0,) * len(values))
    genome = Genome.from_values(list(values), bounds=bounds)
    return Individual.from_genome(genome, birth_generation=gen)


def _parse_svg(svg: str) -> ET.Element:
    """SVG 文字列を ElementTree で parse して root を返す.

    parse 失敗時は AssertionError (test failure として明確化).
    """
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:
        raise AssertionError(f"SVG is not valid XML: {exc}\n---\n{svg[:500]}") from exc
    return root


# ---------------------------------------------------------------------------
# Empty tree
# ---------------------------------------------------------------------------


def test_empty_tree_renders_placeholder_svg() -> None:
    """空 PhyTree → 背景 + placeholder text を含む最低限 SVG."""
    tree = PhyTree()
    svg = tree.to_animated_svg()

    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")
    assert "viewBox=\"0 0 800 240\"" in svg
    # 背景 (linearGradient) と placeholder text を最低限含む
    assert "linearGradient" in svg
    assert "PhyTree is empty" in svg
    # placeholder text 自体は中央寄せ
    assert 'text-anchor="middle"' in svg

    # XML として valid
    root = _parse_svg(svg)
    assert root.tag.endswith("svg")


def test_empty_tree_has_accessibility_metadata() -> None:
    tree = PhyTree()
    svg = tree.to_animated_svg()
    assert 'role="img"' in svg
    assert "aria-label=" in svg
    assert "<title>" in svg
    assert "<desc>" in svg


# ---------------------------------------------------------------------------
# 1-individual tree
# ---------------------------------------------------------------------------


def test_single_individual_renders_one_circle() -> None:
    """1 個体 → 少なくとも 1 つの circle を含む."""
    tree = PhyTree()
    tree.add_individual(_make_individual((0.5, 1.2), gen=0), op="seed")

    svg = tree.to_animated_svg()
    root = _parse_svg(svg)

    # SVG namespace
    ns = "{http://www.w3.org/2000/svg}"
    circles = root.findall(f".//{ns}circle")
    # main node circle 1 個以上 (legend が含めると更に多い)
    assert len(circles) >= 1, "single individual should render at least one circle"

    # legend を除いた "node circle" は class 経由で取得しても良い
    # ここでは個体 1 体分の SVG が必ず viewBox 800x240 を踏襲
    assert 'viewBox="0 0 800 240"' in svg


# ---------------------------------------------------------------------------
# Edges (parent → child)
# ---------------------------------------------------------------------------


def test_parent_child_renders_edge_path() -> None:
    """親子関係あり → <path> による edge が含まれる."""
    tree = PhyTree()
    parent = _make_individual((0.1, 0.2), gen=0)
    child = _make_individual((0.15, 0.25), gen=1)
    pid = tree.add_individual(parent, op="seed")
    tree.add_individual(child, parents=[pid], op="mutation")

    svg = tree.to_animated_svg()
    root = _parse_svg(svg)
    ns = "{http://www.w3.org/2000/svg}"
    paths = root.findall(f".//{ns}path")
    assert len(paths) >= 1, "parent→child should yield at least one <path> edge"
    # cubic Bezier であること (d attribute に 'C' が含まれる)
    assert any("C" in (p.get("d") or "") for p in paths)


# ---------------------------------------------------------------------------
# Pinned nodes
# ---------------------------------------------------------------------------


def test_pinned_node_has_double_circle() -> None:
    """pinned node → 二重円 (outer ring + main circle) または class マーク."""
    tree = PhyTree()
    parent = _make_individual((0.1, 0.2), gen=0)
    child = _make_individual((0.15, 0.25), gen=1)
    pid = tree.add_individual(parent, op="seed")
    cid = tree.add_individual(child, parents=[pid], op="mutation")
    tree.pin(cid)

    svg = tree.to_animated_svg()
    # class="pinned" or class="phytree-node pinned" が含まれる
    assert "pinned" in svg
    # outer ring 用の class
    assert "phytree-pin-ring" in svg

    # outer ring + main circle で circle が複数 (legend も加算)
    root = _parse_svg(svg)
    ns = "{http://www.w3.org/2000/svg}"
    circles = root.findall(f".//{ns}circle")
    # 2 個体 + pinned outer ring + legend 4 = 計 7 以上
    assert len(circles) >= 3


def test_pinned_node_outer_ring_has_animation() -> None:
    """pinned outer ring は radius pulsate animation を持つ."""
    tree = PhyTree()
    parent = _make_individual((0.1, 0.2), gen=0)
    pid = tree.add_individual(parent, op="seed")
    tree.pin(pid)

    svg = tree.to_animated_svg()
    # outer ring 描画 + r attribute の animate (pulsate)
    assert "phytree-pin-ring" in svg
    assert 'attributeName="r"' in svg


# ---------------------------------------------------------------------------
# Valid XML + no JavaScript
# ---------------------------------------------------------------------------


def test_output_is_valid_xml_for_complex_tree() -> None:
    """10 個体 × 3 世代の DAG が valid XML."""
    tree = PhyTree()
    seeds = [
        tree.add_individual(_make_individual((float(i), float(i)), gen=0), op="seed")
        for i in range(4)
    ]
    gen1 = [
        tree.add_individual(
            _make_individual((float(i) + 0.1, float(i) + 0.1), gen=1),
            parents=[seeds[i]],
            op="mutation",
        )
        for i in range(4)
    ]
    tree.add_individual(
        _make_individual((1.5, 1.5), gen=2),
        parents=[gen1[0], gen1[1]],
        op="crossover",
    )
    tree.add_individual(
        _make_individual((2.5, 2.5), gen=2),
        parents=[gen1[2], gen1[3]],
        op="crossover",
    )
    tree.pin(gen1[0])

    svg = tree.to_animated_svg()
    _parse_svg(svg)  # ParseError なし
    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")


def test_no_javascript_in_output() -> None:
    """script tag / on* handler / javascript: URL は一切含まない (SMIL only)."""
    tree = PhyTree()
    parent = _make_individual((0.1, 0.2), gen=0)
    child = _make_individual((0.15, 0.25), gen=1)
    pid = tree.add_individual(parent, op="seed")
    tree.add_individual(child, parents=[pid], op="mutation")
    svg = tree.to_animated_svg()

    assert "<script" not in svg.lower()
    assert "javascript:" not in svg.lower()
    # on* attribute (onclick, onload, etc.) も無いこと
    assert re.search(r"\son[a-z]+=", svg, re.IGNORECASE) is None


# ---------------------------------------------------------------------------
# Animation (SMIL)
# ---------------------------------------------------------------------------


def test_animation_present_smil() -> None:
    """SMIL <animate> 要素が含まれる (fade-in / stagger)."""
    tree = PhyTree()
    tree.add_individual(_make_individual((0.5, 1.2), gen=0), op="seed")
    svg = tree.to_animated_svg()
    root = _parse_svg(svg)
    ns = "{http://www.w3.org/2000/svg}"
    animates = root.findall(f".//{ns}animate")
    assert len(animates) >= 1, "at least one <animate> for fade-in"
    # opacity の fade-in があるべき
    assert any(a.get("attributeName") == "opacity" for a in animates)


# ---------------------------------------------------------------------------
# viewBox / layout options
# ---------------------------------------------------------------------------


def test_default_viewbox_is_800x240() -> None:
    tree = PhyTree()
    svg = tree.to_animated_svg()
    assert 'viewBox="0 0 800 240"' in svg


def test_custom_viewbox() -> None:
    tree = PhyTree()
    tree.add_individual(_make_individual((0.5, 1.2), gen=0), op="seed")
    svg = tree.to_animated_svg(viewbox_width=1200, viewbox_height=400)
    assert 'viewBox="0 0 1200 400"' in svg


def test_layout_top_down() -> None:
    """layout='top_down' でも valid SVG."""
    tree = PhyTree()
    parent = _make_individual((0.1, 0.2), gen=0)
    child = _make_individual((0.15, 0.25), gen=1)
    pid = tree.add_individual(parent, op="seed")
    tree.add_individual(child, parents=[pid], op="mutation")
    svg = tree.to_animated_svg(layout="top_down")
    _parse_svg(svg)
    assert 'viewBox="0 0 800 240"' in svg


def test_invalid_layout_raises() -> None:
    tree = PhyTree()
    with pytest.raises(ValueError, match="unknown layout"):
        tree.to_animated_svg(layout="diagonal")


def test_invalid_max_generations_raises() -> None:
    tree = PhyTree()
    with pytest.raises(ValueError, match="max_generations"):
        tree.to_animated_svg(max_generations=0)


# ---------------------------------------------------------------------------
# Extinct ancestor (parent not in nodes but in edges)
# ---------------------------------------------------------------------------


def test_extinct_parent_renders_ghost() -> None:
    """parent が prune 済 (nodes に無い) でも edge が残っていれば ghost で描画."""
    tree = PhyTree()
    parent = _make_individual((0.1, 0.2), gen=0)
    child = _make_individual((0.15, 0.25), gen=1)
    pid = tree.add_individual(parent, op="seed")
    cid = tree.add_individual(child, parents=[pid], op="mutation")

    # parent を強制 prune (alive=child のみ, pinned 解除)
    tree.unpin(pid)
    # 通常 prune は edge も削るので, 「extinct ancestor」の表現確認のため
    # nodes だけ手動で削除
    del tree.nodes[pid]

    svg = tree.to_animated_svg()
    # ghost ring + "extinct" ラベル
    assert "phytree-ghost" in svg
    assert "extinct" in svg
    # main child circle は描画され, child の content ID prefix が含まれる
    assert cid[:8] in svg
