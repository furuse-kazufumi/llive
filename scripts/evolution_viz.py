#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Evolution-run status → self-contained animated SVG (no external deps).

Reads a persona-evolution run dir (``generations.jsonl`` + ``run_manifest.json``)
and renders a single self-contained SVG: a **fitness trajectory** panel
(best / mean / median + std band) and a **diversity** panel, with a SMIL
left-to-right reveal animation that "plays" the run. Pure stdlib (json/math) so it
embeds anywhere (portal / README / article) — FullSense animated-SVG house style.

HONEST DISCLOSURE: the proxy/real-LLM label from the manifest is baked into the SVG
so a proxy run's smooth curves are never mistaken for real evolutionary progress
(feedback_benchmark_honest_disclosure). Visualization plan:
fullsense/docs/research/evolution_visualization_plan_2026_05_25.md.

    py -3.11 scripts/evolution_viz.py out/evo_run_2026_05_25
    py -3.11 scripts/evolution_viz.py <run_dir> --out custom.svg
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

W, H = 920, 560
ML, MR, MT = 70, 30, 70          # margins (left/right/top)
GAP = 46                          # gap between panels
P1_H, P2_H = 250, 120             # fitness panel height, diversity panel height
ANIM_S = 3.2                      # reveal animation seconds


def _load(run_dir: Path) -> tuple[list[dict], dict]:
    rows = []
    gpath = run_dir / "generations.jsonl"
    if not gpath.exists():
        raise FileNotFoundError(f"no generations.jsonl in {run_dir}")
    for line in gpath.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    rows.sort(key=lambda r: r.get("generation", 0))
    manifest = {}
    mpath = run_dir / "run_manifest.json"
    if mpath.exists():
        try:
            manifest = json.loads(mpath.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}
    return rows, manifest


def _label(rows: list[dict], manifest: dict) -> tuple[str, bool]:
    """Return (honest label text, is_proxy). Never includes host/secret fields."""
    cfg = manifest.get("config", manifest)
    fitness = str(cfg.get("fitness", "proxy"))
    is_proxy = fitness != "llm"
    seed = cfg.get("seed", rows[0].get("seed", "?") if rows else "?")
    gens = len(rows)
    pop = rows[0].get("n_individuals", "?") if rows else "?"
    tag = "PROXY fitness — NOT real LLM eval" if is_proxy else "real on-prem LLM fitness"
    return f"{tag}  ·  gens={gens}  pop={pop}  seed={seed}", is_proxy


def _poly(xs: list[float], ys: list[float]) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))


def render(run_dir: Path) -> str:
    rows, manifest = _load(run_dir)
    if not rows:
        raise ValueError("no generation rows to plot")
    label, is_proxy = _label(rows, manifest)
    gens = [r.get("generation", i) for i, r in enumerate(rows)]
    gmax = max(gens) or 1

    x0, x1 = ML, W - MR
    def sx(g: float) -> float:
        return x0 + (x1 - x0) * (g / gmax)

    # -- fitness panel (scores in [0,1]) --
    p1_top, p1_bot = MT, MT + P1_H
    def sy1(v: float) -> float:
        v = max(0.0, min(1.0, v))
        return p1_bot - (p1_bot - p1_top) * v

    best = [r.get("best_score", 0.0) for r in rows]
    mean = [r.get("mean_score", 0.0) for r in rows]
    median = [r.get("median_score", 0.0) for r in rows]
    std = [r.get("std_score", 0.0) for r in rows]
    xpix = [sx(g) for g in gens]

    band_up = _poly(xpix, [sy1(m + s) for m, s in zip(mean, std)])
    band_dn = _poly(list(reversed(xpix)), [sy1(m - s) for m, s in zip(reversed(mean), reversed(std))])

    # -- diversity panel --
    p2_top = p1_bot + GAP
    p2_bot = p2_top + P2_H
    div = [r.get("diversity_l2", 0.0) for r in rows]
    dmax = max(div) or 1.0
    def sy2(v: float) -> float:
        return p2_bot - (p2_bot - p2_top) * (v / dmax)

    accent = "#c2410c" if is_proxy else "#15803d"  # proxy=amber-ish, real=green

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="ui-sans-serif,Segoe UI,sans-serif">'
    )
    parts.append(f'<rect width="{W}" height="{H}" fill="#0b1020"/>')
    # title + honest label
    parts.append(f'<text x="{ML}" y="30" fill="#e5e7eb" font-size="20" font-weight="700">'
                 f'llive persona evolution — status</text>')
    parts.append(f'<text x="{ML}" y="50" fill="{accent}" font-size="13" font-weight="600">'
                 f'{label}</text>')

    # reveal clip (SMIL): rect grows left→right
    parts.append(
        # 静的フォールバック: authored width=full なので SMIL 非実行環境でも全内容が見える。
        # SMIL 実行時は 0→full の wipe 演出 (animation as enhancement, [[feedback_animated_svg_static_fallback]])。
        f'<clipPath id="reveal"><rect x="{x0}" y="0" width="{x1 - x0:.0f}" height="{H}">'
        f'<animate attributeName="width" from="0" to="{x1 - x0:.0f}" '
        f'dur="{ANIM_S}s" fill="freeze"/></rect></clipPath>'
    )

    # fitness panel frame + gridlines (y = 0,.25,.5,.75,1)
    parts.append(f'<text x="{ML}" y="{p1_top-8}" fill="#9ca3af" font-size="12">fitness (0–1)</text>')
    for v in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = sy1(v)
        parts.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="#1f2937" stroke-width="1"/>')
        parts.append(f'<text x="{x0-8}" y="{y+4:.1f}" fill="#6b7280" font-size="10" text-anchor="end">{v:.2f}</text>')

    # diversity panel frame + base/max lines
    parts.append(f'<text x="{ML}" y="{p2_top-8}" fill="#9ca3af" font-size="12">diversity (L2)</text>')
    for v in (0.0, dmax / 2, dmax):
        y = sy2(v)
        parts.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="#1f2937" stroke-width="1"/>')
        parts.append(f'<text x="{x0-8}" y="{y+4:.1f}" fill="#6b7280" font-size="10" text-anchor="end">{v:.2f}</text>')

    # x-axis ticks (generations)
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        g = round(gmax * frac)
        x = sx(g)
        parts.append(f'<text x="{x:.1f}" y="{p2_bot+18:.1f}" fill="#6b7280" font-size="10" text-anchor="middle">{g}</text>')
    parts.append(f'<text x="{(x0+x1)/2:.0f}" y="{p2_bot+38:.0f}" fill="#9ca3af" font-size="12" text-anchor="middle">generation</text>')

    # animated content group (clipped reveal)
    parts.append('<g clip-path="url(#reveal)">')
    # std band
    parts.append(f'<polygon points="{band_up} {band_dn}" fill="{accent}" fill-opacity="0.15"/>')
    # mean / median / best lines
    parts.append(f'<polyline points="{_poly(xpix, [sy1(v) for v in median])}" fill="none" stroke="#60a5fa" stroke-width="1.5" stroke-opacity="0.8"/>')
    parts.append(f'<polyline points="{_poly(xpix, [sy1(v) for v in mean])}" fill="none" stroke="#a78bfa" stroke-width="2"/>')
    parts.append(f'<polyline points="{_poly(xpix, [sy1(v) for v in best])}" fill="none" stroke="{accent}" stroke-width="2.5"/>')
    # diversity line
    parts.append(f'<polyline points="{_poly(xpix, [sy2(v) for v in div])}" fill="none" stroke="#22d3ee" stroke-width="2"/>')
    parts.append('</g>')

    # legend
    lx, ly = x1 - 250, p1_top + 6
    legend = [("best", accent), ("mean", "#a78bfa"), ("median", "#60a5fa"), ("±std", accent), ("diversity", "#22d3ee")]
    for i, (name, col) in enumerate(legend):
        yy = ly + i * 16
        parts.append(f'<rect x="{lx}" y="{yy-8}" width="12" height="3" fill="{col}"/>')
        parts.append(f'<text x="{lx+18}" y="{yy-2}" fill="#9ca3af" font-size="11">{name}</text>')

    parts.append('</svg>')
    return "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description="evolution run → self-contained animated SVG")
    ap.add_argument("run_dir", help="run output dir (with generations.jsonl)")
    ap.add_argument("--out", default=None, help="output svg path (default: <run_dir>/evolution.svg)")
    args = ap.parse_args()
    run_dir = Path(args.run_dir)
    out = Path(args.out) if args.out else run_dir / "evolution.svg"
    svg = render(run_dir)
    out.write_text(svg, encoding="utf-8")
    print(f"wrote {out}  ({len(svg)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
