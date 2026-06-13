#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Evolution-run **Genome3D 思考因子ヒートマップ** (P3) → 自己完結 SVG (no deps).

最終 snapshot の **best 個体** の ``c_factors`` (10 思考因子 × メモリ層) を heatmap 化。
「どんな認知プロファイルが勝ち残ったか」を一目で見せる (rich-proxy run で意味を持つ;
real-pressure run では c_factors は fitness 中立なので参考表示)。

FullSense house style (dark bg + SMIL フェードイン + honest ラベル)。

    py -3.11 scripts/evolution_genome_heatmap.py out/lldarwin_D_reservoir_2026_05_26
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

_FACTORS = (
    "structurize", "recompose", "closed_loop", "self_extend", "uncertainty",
    "exploration", "consistency", "provenance", "multiview", "reality_link",
)
W, H = 820, 460
ML, MT = 200, 90
CELL = 56


def _best_genome(run_dir: Path) -> tuple[list[list[float]], list[str], int, float]:
    snaps = sorted(run_dir.glob("snapshot_gen_*.json"), key=lambda p: int(p.stem.split("_")[-1]))
    if not snaps:
        raise ValueError(f"no snapshot_gen_*.json under {run_dir}")
    data = json.loads(snaps[-1].read_text(encoding="utf-8"))
    gen = int(data.get("generation", 0))
    best = max(
        data.get("individuals", []),
        key=lambda ind: float((ind.get("fitness") or {}).get("score", 0.0)),
    )
    score = float((best.get("fitness") or {}).get("score", 0.0))
    genome = best.get("genome", {})
    cf = genome.get("c_factors", {})
    matrix = cf.get("factor_weights")
    layers = list(cf.get("layer_names", []))
    if not matrix:
        raise ValueError(
            f"best individual has no c_factors (genome_type={best.get('genome_type')}); "
            "need a Genome3D run"
        )
    return [[float(v) for v in row] for row in matrix], layers, gen, score


def _heat(v: float) -> str:
    """value [0,1] → 色 (低=藍, 高=橙)。house style に合わせた divergent。"""
    v = max(0.0, min(1.0, v))
    # interpolate 藍(#1e3a8a) → 中(#334155) → 橙(#ea580c)
    if v < 0.5:
        t = v / 0.5
        r = int(0x1e + (0x33 - 0x1e) * t); g = int(0x3a + (0x41 - 0x3a) * t); b = int(0x8a + (0x55 - 0x8a) * t)
    else:
        t = (v - 0.5) / 0.5
        r = int(0x33 + (0xea - 0x33) * t); g = int(0x41 + (0x58 - 0x41) * t); b = int(0x55 + (0x0c - 0x55) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def render(run_dir: Path) -> str:
    matrix, layers, gen, score = _best_genome(run_dir)
    if not layers:
        layers = [f"L{i}" for i in range(len(matrix[0]))]
    manifest = {}
    mp = run_dir / "run_manifest.json"
    if mp.exists():
        try:
            manifest = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}
    fitness = str(manifest.get("fitness", "?"))
    is_proxy = "proxy" in fitness and fitness != "real-pressure"
    note = (
        f"PROXY ({fitness}) · best score={score:.3f} · gen {gen}"
        if is_proxy
        else f"REAL LLM ({fitness}) · c_factors は fitness 中立 (参考) · gen {gen}"
    )
    accent = "#c2410c" if is_proxy else "#15803d"

    n_layers = len(layers)
    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="ui-sans-serif,Segoe UI,sans-serif">'
    )
    parts.append(f'<rect width="{W}" height="{H}" fill="#0b1020"/>')
    parts.append(f'<text x="24" y="30" fill="#e5e7eb" font-size="20" font-weight="700">'
                 f'lldarwin — 勝者の思考因子プロファイル (Genome3D)</text>')
    parts.append(f'<text x="24" y="50" fill="{accent}" font-size="12" font-weight="600">{note}</text>')
    # layer headers
    for j, lname in enumerate(layers):
        x = ML + j * CELL + CELL / 2
        parts.append(f'<text x="{x:.0f}" y="{MT-10}" fill="#9ca3af" font-size="11" text-anchor="middle">{lname}</text>')
    # rows
    for i, fac in enumerate(_FACTORS[: len(matrix)]):
        y = MT + i * (CELL * 0.6)
        parts.append(f'<text x="{ML-10}" y="{y + CELL*0.3 + 4:.0f}" fill="#cbd5e1" font-size="11" text-anchor="end">{fac}</text>')
        for j in range(n_layers):
            v = matrix[i][j] if j < len(matrix[i]) else 0.0
            x = ML + j * CELL
            # 静的フォールバック: authored opacity=1 で SMIL 非実行環境でも cell が見える。
            # SMIL 実行時のみ波状フェードイン ([[feedback_animated_svg_static_fallback]])。
            parts.append(
                f'<rect x="{x}" y="{y:.0f}" width="{CELL-3}" height="{CELL*0.6-3:.0f}" '
                f'fill="{_heat(v)}" opacity="1"><animate attributeName="opacity" from="0" to="1" '
                f'dur="0.8s" begin="{(i*n_layers+j)*0.02:.2f}s" fill="freeze"/></rect>'
            )
            parts.append(f'<text x="{x + (CELL-3)/2:.0f}" y="{y + CELL*0.3 + 3:.0f}" fill="#e5e7eb" '
                         f'font-size="9" text-anchor="middle" opacity="0.85">{v:.2f}</text>')
    # legend bar
    ly = MT + len(matrix) * (CELL * 0.6) + 24
    parts.append(f'<text x="{ML}" y="{ly-6}" fill="#9ca3af" font-size="11">低 0.0</text>')
    for k in range(40):
        v = k / 39
        parts.append(f'<rect x="{ML + 60 + k*4}" y="{ly-16}" width="4" height="10" fill="{_heat(v)}"/>')
    parts.append(f'<text x="{ML + 60 + 40*4 + 6}" y="{ly-6}" fill="#9ca3af" font-size="11">1.0 高</text>')
    parts.append('</svg>')
    return "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description="evolution run → Genome3D 思考因子 heatmap SVG")
    ap.add_argument("run_dir")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    run_dir = Path(args.run_dir)
    out = Path(args.out) if args.out else run_dir / "genome_heatmap.svg"
    out.write_text(render(run_dir), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
