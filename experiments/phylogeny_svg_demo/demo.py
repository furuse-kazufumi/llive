#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""PhyTree.to_animated_svg() のデモ.

10 個体 × 3 世代の小さな系統樹を構築し, animated SVG (800x240 hero bar)
として ``sample_phylogeny.svg`` に書き出す.

Run:
    py -3.11 experiments/phylogeny_svg_demo/demo.py

Output:
    - sample_phylogeny.svg (animated, SMIL only, no JS)
    - sample_phylogeny_topdown.svg (top_down layout variant)
"""
from __future__ import annotations

import pathlib

from llive.perf.evolutionary.genome import Genome, GenomeBounds
from llive.perf.evolutionary.individual import Individual
from llive.perf.evolutionary.phylogeny import PhyTree, compute_individual_id

HERE = pathlib.Path(__file__).resolve().parent


def _make_individual(values: tuple[float, ...], gen: int) -> Individual:
    bounds = GenomeBounds(
        lower=(-10.0,) * len(values), upper=(10.0,) * len(values)
    )
    genome = Genome.from_values(list(values), bounds=bounds)
    return Individual.from_genome(genome, birth_generation=gen)


def build_demo_tree() -> PhyTree:
    """10 個体 × 3 世代 (4 seed → 4 mutated → 2 crossover) のサンプル."""
    tree = PhyTree()

    # gen 0: 4 seed individuals
    seeds: list[str] = []
    for i, vals in enumerate(
        [(0.1, 0.2), (0.5, -0.3), (-0.8, 0.4), (0.9, 0.9)]
    ):
        ind = _make_individual(vals, gen=0)
        sid = tree.add_individual(ind, op="seed", metadata={"slot": str(i)})
        seeds.append(sid)

    # gen 1: 4 mutated children
    gen1_ids: list[str] = []
    for i, (parent_sid, vals) in enumerate(
        [
            (seeds[0], (0.15, 0.25)),
            (seeds[1], (0.55, -0.25)),
            (seeds[2], (-0.75, 0.45)),
            (seeds[3], (0.85, 0.85)),
        ]
    ):
        ind = _make_individual(vals, gen=1)
        cid = tree.add_individual(
            ind, parents=[parent_sid], op="mutation",
            metadata={"generation": "1", "rate": "0.05"},
        )
        gen1_ids.append(cid)

    # gen 2: 2 crossover offspring
    gen2_ids: list[str] = []
    for parents_pair, vals in [
        ((gen1_ids[0], gen1_ids[1]), (0.35, 0.0)),
        ((gen1_ids[2], gen1_ids[3]), (0.05, 0.65)),
    ]:
        ind = _make_individual(vals, gen=2)
        cid = tree.add_individual(
            ind, parents=list(parents_pair), op="crossover",
            metadata={"generation": "2"},
        )
        gen2_ids.append(cid)

    # pin 2 best (gen 1 top-2)
    tree.pin(gen1_ids[0])
    tree.pin(gen2_ids[0])

    return tree


def main() -> None:
    tree = build_demo_tree()

    # default layout (left_to_right)
    svg = tree.to_animated_svg()
    out_lr = HERE / "sample_phylogeny.svg"
    out_lr.write_text(svg, encoding="utf-8")
    print(f"SVG saved: {out_lr.as_posix()}, {len(svg)} chars")

    # top_down variant
    svg_td = tree.to_animated_svg(layout="top_down")
    out_td = HERE / "sample_phylogeny_topdown.svg"
    out_td.write_text(svg_td, encoding="utf-8")
    print(f"SVG saved: {out_td.as_posix()}, {len(svg_td)} chars")

    # 統計
    print(f"  nodes  = {len(tree.nodes)}")
    print(f"  edges  = {len(tree.edges)}")
    print(f"  pinned = {len(tree.pinned)}")

    # content-addressable check
    seed0_id = next(iter(tree.nodes))
    print(f"  sample ID (SHA-256 hex): {seed0_id[:16]}...")
    _ = compute_individual_id  # re-export sanity


if __name__ == "__main__":
    main()
