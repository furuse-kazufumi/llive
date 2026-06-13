#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""進化の樹 (lineage tree / tree of life) アニメ SVG (no deps).

折れ線も積み上げも退屈。進化の醍醐味は **系統が根から枝分かれし、太り、絶滅し、
中立貯蔵庫で甦る** こと。本スクリプトは ``founder_lineage.jsonl`` を読み、各 founder
系統を「時間(世代)を右へ流れる枝(川)」として描く。枝の太さ=その世代の個体数、
枝が消える=絶滅(✕)、再び芽吹く=貯蔵庫による復活(◦)。左の根(trunk)から 9 系統へ
枝分かれする生命の樹。

- 依存なし自己完結 + SMIL で左→右に成長アニメ。
- 静的フォールバック: authored 全幅で reveal するので SMIL 無しでも樹全体が見える
  ([[feedback_animated_svg_static_fallback]])。

    py -3.11 scripts/evolution_tree.py out/lldarwin_D_reservoir_2026_05_26
    py -3.11 scripts/evolution_tree.py <run_dir> --out tree.svg
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

LANES = ("furuse-kazufumi", "friston", "millidge", "isomura-takuya",
         "oka-kiyoshi", "grothendieck", "von-neumann", "feynman", "(random)")
COLORS = {
    "furuse-kazufumi": "#f87171", "friston": "#fbbf24", "millidge": "#34d399",
    "isomura-takuya": "#60a5fa", "oka-kiyoshi": "#a78bfa", "grothendieck": "#f472b6",
    "von-neumann": "#22d3ee", "feynman": "#fb923c", "(random)": "#475569",
}


def _load(run_dir: Path):
    rows = [json.loads(l) for l in (run_dir / "founder_lineage.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    manifest = {}
    mp = run_dir / "run_manifest.json"
    if mp.exists():
        try:
            manifest = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}
    return rows, manifest


def render(run_dir: Path) -> str:
    rows, manifest = _load(run_dir)
    if not rows:
        raise ValueError(f"no founder_lineage.jsonl in {run_dir}")
    gens = [int(r["generation"]) for r in rows]
    G = len(rows)
    counts = {ln: [int(r["founder_counts"].get(ln, 0)) for r in rows] for ln in LANES}
    cmax = max((max(v) for v in counts.values()), default=1) or 1
    lanes = [ln for ln in LANES if max(counts[ln]) > 0]

    W, H = 1000, 560
    ROOTX, X0, X1 = 46, 150, W - 180
    TOP, BOT = 78, H - 46
    n = len(lanes)
    lane_y = {ln: TOP + (BOT - TOP) * (i + 0.5) / n for i, ln in enumerate(lanes)}
    lane_h = (BOT - TOP) / n * 0.46
    gx = lambda i: X0 + (X1 - X0) * (i / (G - 1 if G > 1 else 1))
    hh = lambda c: lane_h * (c / cmax)

    fitness = str(manifest.get("fitness", "?"))
    is_proxy = "proxy" in fitness and fitness != "real-pressure"
    reservoir = bool(manifest.get("lineage_reservoir", False))
    survived = sum(1 for ln in lanes if ln != "(random)" and counts[ln][-1] > 0)
    sub = (f"{'PROXY' if is_proxy else 'REAL LLM'} · {fitness} · {G} 世代 · "
           f"中立貯蔵庫 {'ON' if reservoir else 'OFF'} · 最終生存 {survived}/8 系統")

    p = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="ui-sans-serif,Segoe UI,sans-serif">']
    p.append('<defs><radialGradient id="bg" cx="20%" cy="50%" r="90%">'
             '<stop offset="0%" stop-color="#0e1530"/><stop offset="100%" stop-color="#06090f"/></radialGradient></defs>')
    p.append(f'<rect width="{W}" height="{H}" fill="url(#bg)"/>')
    p.append(f'<text x="{ROOTX}" y="30" fill="#e5e7eb" font-size="21" font-weight="700">進化の樹 — どの「始祖」の子孫が生き残るか</text>')
    p.append(f'<text x="{ROOTX}" y="50" fill="{"#34d399" if reservoir else "#f87171"}" font-size="12.5" font-weight="600">{sub}</text>')
    # 読み方パネル (自己説明: 何を見ているか)
    p.append(f'<text x="{ROOTX}" y="68" fill="#cbd5e1" font-size="11.5">'
             f'読み方: <tspan fill="#fbbf24">横=世代(時間→)</tspan> / '
             f'<tspan fill="#fbbf24">縦の色帯=8始祖の系統</tspan> / '
             f'<tspan fill="#fbbf24">帯の太さ=その系統の個体数</tspan> / '
             f'<tspan fill="#fca5a5">✕=絶滅</tspan> / <tspan fill="#fff">◦=貯蔵庫が復活させた瞬間</tspan></text>')

    p.append(f'<clipPath id="grow"><rect x="0" y="0" width="{W}" height="{H}">'
             f'<animate attributeName="width" from="{ROOTX}" to="{W}" dur="4.5s" fill="freeze"/></rect></clipPath>')
    p.append('<g clip-path="url(#grow)">')

    rooty = (TOP + BOT) / 2
    p.append(f'<circle cx="{ROOTX}" cy="{rooty:.1f}" r="7" fill="#e5e7eb"/>')
    p.append(f'<text x="{ROOTX-6}" y="{rooty+22:.1f}" fill="#9ca3af" font-size="10" text-anchor="middle">根</text>')

    for ln in lanes:
        col = COLORS.get(ln, "#475569")
        cy = lane_y[ln]
        p.append(f'<path d="M {ROOTX} {rooty:.1f} C {(ROOTX+X0)/2:.0f} {rooty:.1f}, {(ROOTX+X0)/2:.0f} {cy:.1f}, {X0} {cy:.1f}" '
                 f'fill="none" stroke="{col}" stroke-width="2" stroke-opacity="0.5"/>')
        cs = counts[ln]
        top = [(gx(i), cy - hh(c)) for i, c in enumerate(cs)]
        bot = [(gx(i), cy + hh(c)) for i, c in enumerate(cs)]
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in top) + " " + " ".join(f"{x:.1f},{y:.1f}" for x, y in reversed(bot))
        p.append(f'<polygon points="{pts}" fill="{col}" fill-opacity="0.78"/>')
        mid = " ".join(f"{gx(i):.1f},{cy:.1f}" for i in range(G))
        p.append(f'<polyline points="{mid}" fill="none" stroke="{col}" stroke-width="1" stroke-opacity="0.5"/>')
        for i in range(1, G):
            if cs[i] == 0 and cs[i-1] > 0:
                p.append(f'<text x="{gx(i):.1f}" y="{cy+4:.1f}" fill="#fca5a5" font-size="13" text-anchor="middle" font-weight="700">✕</text>')
            if cs[i] > 0 and cs[i-1] == 0:
                p.append(f'<circle cx="{gx(i):.1f}" cy="{cy:.1f}" r="5" fill="none" stroke="#fff" stroke-width="1.5">'
                         f'<animate attributeName="r" values="3;7;3" dur="1.6s" repeatCount="indefinite"/></circle>')
        p.append(f'<text x="{X1+8}" y="{cy+4:.1f}" fill="{col}" font-size="11" font-weight="600">{ln}</text>')
    p.append('</g>')

    for frac in (0, 0.5, 1.0):
        gi = round((G - 1) * frac)
        p.append(f'<text x="{gx(gi):.1f}" y="{BOT+20:.1f}" fill="#6b7280" font-size="10" text-anchor="middle">gen {gens[gi]}</text>')
    # 結論 (plain language takeaway) — 見ただけで主張が伝わるように
    if reservoir:
        takeaway = f"→ 貯蔵庫があるので、一度絶滅しかけた系統も含め {survived}/8 系統すべてが生き残った"
        tcol = "#34d399"
    else:
        takeaway = f"→ 貯蔵庫がないと枝が次々と枯れ、最後は {survived}/8 系統しか残らなかった (遺伝的浮動)"
        tcol = "#f87171"
    p.append(f'<text x="{(X0+X1)/2:.0f}" y="{BOT+38:.0f}" fill="{tcol}" font-size="13" font-weight="600" text-anchor="middle">{takeaway}</text>')
    p.append('</svg>')
    return "\n".join(p)


def main() -> int:
    ap = argparse.ArgumentParser(description="evolution lineage tree animated SVG")
    ap.add_argument("run_dir")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    run_dir = Path(args.run_dir)
    out = Path(args.out) if args.out else run_dir / "tree.svg"
    out.write_text(render(run_dir), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
