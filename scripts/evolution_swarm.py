#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""進化を「生きた集団」として見せる swarm アニメ SVG (no deps).

折れ線は退屈。進化の本質は **集団が動き・広がり・絶滅し・中立貯蔵庫で甦る** こと。
本スクリプトは短い rich-proxy 進化を回し、各世代の全個体を **2D 投影した点**として
記録し、**系統(founder)色つきで世代送りアニメ**する SVG を生成する。中立貯蔵庫 ON では
絶滅系統の点が再投入で「再点灯」するのが見える。

- 点 = 個体 / 色 = 由来 founder 系統 (LineageReservoir.lineage_of から) / 位置 = genome の 2D 投影
- アニメ = 世代を順に明滅 (flipbook)。静的フォールバック = 全世代の薄い残像 (軌跡)。
  ([[feedback_animated_svg_static_fallback]] 準拠: SMIL 無しでも軌跡が見える)

    py -3.11 scripts/evolution_swarm.py --reservoir --out out/swarm.svg
    py -3.11 scripts/evolution_swarm.py --no-reservoir   # 崩壊 (色が消える) を見る
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from llive.perf.evolutionary.fitness_rich import make_rich_proxy_fitness
from llive.perf.evolutionary.genome_3d import genome_flat_vector
from llive.perf.evolutionary.genome_3d_operators import Genome3DCrossover, Genome3DMutation
from llive.perf.evolutionary.individual import Individual
from llive.perf.evolutionary.lineage_reservoir import LineageReservoir
from llive.perf.evolutionary.lldarwin import MultiPressureSelector
from llive.perf.evolutionary.persona_evolution import build_founder_genome_3d
from llive.perf.evolutionary.population import Population

FOUNDERS = ("furuse-kazufumi", "friston", "millidge", "isomura-takuya",
            "oka-kiyoshi", "grothendieck", "von-neumann", "feynman")
# 系統色 (8 founders + random)。視認性の高い離散色。
COLORS = {
    "furuse-kazufumi": "#f87171", "friston": "#fbbf24", "millidge": "#34d399",
    "isomura-takuya": "#60a5fa", "oka-kiyoshi": "#a78bfa", "grothendieck": "#f472b6",
    "von-neumann": "#22d3ee", "feynman": "#fb923c", "(random)": "#475569",
}


def run_and_record(generations: int, population: int, seed: int, use_reservoir: bool):
    rng = np.random.default_rng(seed)
    fitness = make_rich_proxy_fitness(FOUNDERS)
    crossover = Genome3DCrossover(mode="intra")
    mutation = Genome3DMutation(step_size=0.12)
    selector = MultiPressureSelector(epsilon=0.01, use_novelty=True)
    lineage_of: dict[str, str] = {}

    inds = []
    for i in range(population):
        pid = FOUNDERS[i % len(FOUNDERS)]
        ind = Individual(genome=build_founder_genome_3d(pid), birth_generation=0)
        lineage_of[ind.individual_id] = pid
        inds.append(ind)
    pop = Population(individuals=inds, generation=0)
    reservoir = LineageReservoir(lineage_of=lineage_of,
                                 protected_lineages=frozenset(FOUNDERS)) if use_reservoir else None

    # 固定 2D 投影軸 (genome_flat_vector → 2D)。
    dim = genome_flat_vector(inds[0].genome).shape[0]
    proj = np.random.default_rng(7).standard_normal((dim, 2))
    proj /= np.linalg.norm(proj, axis=0, keepdims=True)

    frames = []  # 各世代: list of (x, y, lineage, score)
    for gen in range(generations):
        for ind in pop.individuals:
            if ind.fitness is None:
                ind.record_fitness(fitness(ind.genome))
        frame = []
        for ind in pop.individuals:
            xy = genome_flat_vector(ind.genome) @ proj
            lin = lineage_of.get(ind.individual_id, "(random)")
            frame.append((float(xy[0]), float(xy[1]), lin, float(ind.fitness.score)))
        frames.append(frame)

        nxt = []
        while len(nxt) < population:
            pa = selector(pop, rng); pb = selector(pop, rng)
            cg = mutation(crossover(pa.genome, pb.genome, rng), rng)
            child = Individual.from_genome(cg, parent_ids=(pa.individual_id, pb.individual_id),
                                           birth_generation=gen + 1)
            lineage_of[child.individual_id] = lineage_of.get(pa.individual_id, "(random)")
            nxt.append(child)
        bred_pop = Population(individuals=nxt, generation=gen + 1)
        if reservoir is not None:
            nxt = reservoir(nxt, pop, rng)
            bred_pop = Population(individuals=nxt, generation=gen + 1)
        pop = bred_pop
    return frames


def render(frames, use_reservoir: bool) -> str:
    W, H = 900, 600
    PAD, TOP = 40, 70
    G = len(frames)
    allpts = [(x, y) for f in frames for (x, y, _, _) in f]
    xs = [p[0] for p in allpts]; ys = [p[1] for p in allpts]
    xmin, xmax = min(xs), max(xs); ymin, ymax = min(ys), max(ys)
    sx = lambda x: PAD + (W - 2 * PAD) * (x - xmin) / ((xmax - xmin) or 1)
    sy = lambda y: TOP + (H - TOP - PAD) * (y - ymin) / ((ymax - ymin) or 1)
    TOTAL = max(8.0, G * 0.45)  # ループ秒数

    label = "中立貯蔵庫 ON — 全系統が生き続ける" if use_reservoir else "貯蔵庫なし — 色が消えていく (系統崩壊)"
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="ui-sans-serif,Segoe UI,sans-serif">']
    # 背景 (微グラデで宇宙感)
    p.append('<defs><radialGradient id="bg" cx="50%" cy="40%" r="75%">'
             '<stop offset="0%" stop-color="#10162e"/><stop offset="100%" stop-color="#070a17"/></radialGradient></defs>')
    p.append(f'<rect width="{W}" height="{H}" fill="url(#bg)"/>')
    p.append(f'<text x="{PAD}" y="32" fill="#e5e7eb" font-size="21" font-weight="700">lldarwin — 生きた集団の進化 (swarm)</text>')
    p.append(f'<text x="{PAD}" y="52" fill="{"#34d399" if use_reservoir else "#f87171"}" font-size="13" font-weight="600">PROXY · 8 founders · {G} 世代 · {label}</text>')

    # 各世代を group にし、flipbook で順に明滅。base opacity を低く残し静的フォールバック=軌跡。
    for g, frame in enumerate(frames):
        # 1 世代の表示窓 (keyTimes)。前後に薄く残す。
        c = (g + 0.5) / G
        w = 0.5 / G
        kt = f"0;{max(0,c-w):.4f};{c:.4f};{min(1,c+w):.4f};1"
        vals = "0.10;0.10;1;0.10;0.10"
        p.append(f'<g opacity="0.10"><animate attributeName="opacity" dur="{TOTAL}s" '
                 f'repeatCount="indefinite" keyTimes="{kt}" values="{vals}" calcMode="spline" '
                 f'keySplines="0.4 0 0.2 1;0.4 0 0.2 1;0.4 0 0.2 1;0.4 0 0.2 1"/>')
        for (x, y, lin, score) in frame:
            r = 4 + 6 * score  # 適応度で大きさ
            col = COLORS.get(lin, "#475569")
            p.append(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="{r:.1f}" fill="{col}" '
                     f'fill-opacity="0.85" stroke="#0b1020" stroke-width="0.6"/>')
        p.append('</g>')

    # 進行バー (世代の進みを下部で sweep)
    bx0, bx1, by = PAD, W - PAD, H - 16
    p.append(f'<line x1="{bx0}" y1="{by}" x2="{bx1}" y2="{by}" stroke="#1f2937" stroke-width="3"/>')
    p.append(f'<circle cx="{bx0}" cy="{by}" r="5" fill="#e5e7eb">'
             f'<animate attributeName="cx" from="{bx0}" to="{bx1}" dur="{TOTAL}s" repeatCount="indefinite"/></circle>')
    p.append(f'<text x="{bx0}" y="{by-8}" fill="#6b7280" font-size="10">gen 0</text>')
    p.append(f'<text x="{bx1}" y="{by-8}" fill="#6b7280" font-size="10" text-anchor="end">gen {G-1}</text>')

    # 凡例 (系統色)
    lx, ly = W - 168, TOP
    for i, f in enumerate(FOUNDERS):
        yy = ly + i * 20
        p.append(f'<circle cx="{lx}" cy="{yy-4}" r="5" fill="{COLORS[f]}"/>')
        p.append(f'<text x="{lx+12}" y="{yy}" fill="#cbd5e1" font-size="11">{f}</text>')
    p.append('</svg>')
    return "\n".join(p)


def main() -> int:
    ap = argparse.ArgumentParser(description="evolution swarm animated SVG")
    ap.add_argument("--generations", type=int, default=36)
    ap.add_argument("--population", type=int, default=30)
    ap.add_argument("--seed", type=int, default=0)
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--reservoir", dest="reservoir", action="store_true", default=True)
    grp.add_argument("--no-reservoir", dest="reservoir", action="store_false")
    ap.add_argument("--out", type=Path, default=Path("out/swarm.svg"))
    args = ap.parse_args()
    frames = run_and_record(args.generations, args.population, args.seed, args.reservoir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(frames, args.reservoir), encoding="utf-8")
    print(f"wrote {args.out}  ({args.out.stat().st_size} bytes, {len(frames)} gens)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
