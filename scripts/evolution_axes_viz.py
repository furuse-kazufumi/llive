#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Evolution-run **per-axis** view → self-contained animated SVG (no external deps).

lldarwin の多目的選択圧 (苦手軸 typo / polysemy / multistep / calibration / context)
が世代を追ってどう改善するかを、**軸ごとの母集団平均スコア**の折れ線で示す。
``--fitness pressure-proxy`` / ``real-pressure`` の run に対応 (breakdown が
``<axis>::<case>`` 形式の case を持つ run)。

データ源 = ``snapshot_gen_*.json`` (各個体の ``fitness.breakdown`` に per-axis case が
入る)。snapshot は ``--checkpoint-every`` 間隔で書かれるので解像度はその粒度。

FullSense animated-SVG house style (dark bg + SMIL reveal + honest label)。
manifest の proxy/real ラベルを焼き込み、proxy 値を実能力と誤認させない
([[feedback_benchmark_honest_disclosure]])。

    py -3.11 scripts/evolution_axes_viz.py out/lldarwin_12h_realpressure_2026_05_26
    py -3.11 scripts/evolution_axes_viz.py <run_dir> --out axes.svg
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

W, H = 900, 460
ML, MR, MT, MB = 70, 200, 70, 60
ANIM_S = 4.0

#: 軸ごとの色 (最大 8 軸)。
_PALETTE = ("#f87171", "#fbbf24", "#34d399", "#60a5fa", "#a78bfa", "#f472b6", "#22d3ee", "#fb923c")


def _axis_means_per_snapshot(run_dir: Path) -> tuple[list[int], dict[str, list[float]]]:
    """各 snapshot generation の **軸別母集団平均** を返す.

    breakdown キー ``<axis>::<case>`` を ``<axis>`` でまとめ、全 case × 全個体平均。
    """
    snaps = sorted(run_dir.glob("snapshot_gen_*.json"), key=lambda p: int(p.stem.split("_")[-1]))
    gens: list[int] = []
    series: dict[str, list[float]] = defaultdict(list)
    for snap in snaps:
        data = json.loads(snap.read_text(encoding="utf-8"))
        gen = int(data.get("generation", 0))
        axis_vals: dict[str, list[float]] = defaultdict(list)
        for ind in data.get("individuals", []):
            bd = (ind.get("fitness") or {}).get("breakdown") or {}
            for key, val in bd.items():
                if "::" not in key:
                    continue
                axis = key.split("::", 1)[0]
                try:
                    axis_vals[axis].append(float(val))
                except (TypeError, ValueError):
                    continue
        if not axis_vals:
            continue
        gens.append(gen)
        for axis, vals in axis_vals.items():
            series[axis].append(sum(vals) / len(vals))
    # 軸が途中から現れた場合に長さを揃える (短いものは前方を None 扱いせず実在分のみ)。
    return gens, dict(series)


def _load_manifest(run_dir: Path) -> dict:
    p = run_dir / "run_manifest.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _poly(xs: list[float], ys: list[float]) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))


def render(run_dir: Path) -> str:
    gens, series = _axis_means_per_snapshot(run_dir)
    if not gens or not series:
        raise ValueError(
            f"no per-axis breakdown in snapshots under {run_dir} "
            "(need a pressure-proxy / real-pressure run with snapshot_gen_*.json)"
        )
    manifest = _load_manifest(run_dir)
    fitness = str(manifest.get("fitness", "?"))
    is_proxy = "proxy" in fitness and fitness != "real-pressure"
    label = (
        f"{'PROXY (genome 振る舞い代理)' if is_proxy else 'REAL on-prem LLM eval'} "
        f"·  fitness={fitness}  ·  model={manifest.get('ollama_model', 'n/a')}  ·  "
        f"snapshots={len(gens)} (gen {gens[0]}–{gens[-1]})"
    )
    accent = "#c2410c" if is_proxy else "#15803d"

    gmax = max(gens) or 1
    gmin = min(gens)
    x0, x1 = ML, W - MR
    p_top, p_bot = MT, H - MB

    def sx(g: float) -> float:
        span = (gmax - gmin) or 1
        return x0 + (x1 - x0) * ((g - gmin) / span)

    def sy(v: float) -> float:
        v = max(0.0, min(1.0, v))
        return p_bot - (p_bot - p_top) * v

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="ui-sans-serif,Segoe UI,sans-serif">'
    )
    parts.append(f'<rect width="{W}" height="{H}" fill="#0b1020"/>')
    parts.append(
        f'<text x="{ML}" y="30" fill="#e5e7eb" font-size="20" font-weight="700">'
        f'lldarwin — LLM 苦手軸スコアの進化 (per-axis)</text>'
    )
    parts.append(
        f'<text x="{ML}" y="50" fill="{accent}" font-size="12" font-weight="600">{label}</text>'
    )

    # reveal clip (SMIL)
    parts.append(
        f'<clipPath id="reveal"><rect x="{x0}" y="0" width="0" height="{H}">'
        f'<animate attributeName="width" from="0" to="{x1 - x0:.0f}" '
        f'dur="{ANIM_S}s" fill="freeze"/></rect></clipPath>'
    )

    # gridlines + y labels
    parts.append(f'<text x="{ML}" y="{p_top-8}" fill="#9ca3af" font-size="12">axis mean score (0–1)</text>')
    for v in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = sy(v)
        parts.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="#1f2937" stroke-width="1"/>')
        parts.append(f'<text x="{x0-8}" y="{y+4:.1f}" fill="#6b7280" font-size="10" text-anchor="end">{v:.2f}</text>')

    # x ticks
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        g = round(gmin + (gmax - gmin) * frac)
        x = sx(g)
        parts.append(f'<text x="{x:.1f}" y="{p_bot+18:.1f}" fill="#6b7280" font-size="10" text-anchor="middle">{g}</text>')
    parts.append(f'<text x="{(x0+x1)/2:.0f}" y="{p_bot+38:.0f}" fill="#9ca3af" font-size="12" text-anchor="middle">generation</text>')

    # axis lines (clipped reveal)
    parts.append('<g clip-path="url(#reveal)">')
    axes_sorted = sorted(series.keys())
    color = {a: _PALETTE[i % len(_PALETTE)] for i, a in enumerate(axes_sorted)}
    for axis in axes_sorted:
        ys = series[axis]
        # 実在 snapshot 数に合わせて gens を切る (途中出現対応)。
        xs = [sx(g) for g in gens[: len(ys)]]
        pts = _poly(xs, [sy(v) for v in ys])
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{color[axis]}" stroke-width="2.5"/>')
    parts.append('</g>')

    # legend (axis names)
    lx, ly = x1 + 16, p_top + 6
    for i, axis in enumerate(axes_sorted):
        yy = ly + i * 18
        parts.append(f'<rect x="{lx}" y="{yy-9}" width="14" height="4" fill="{color[axis]}"/>')
        parts.append(f'<text x="{lx+20}" y="{yy-2}" fill="#cbd5e1" font-size="11">{axis}</text>')

    parts.append('</svg>')
    return "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description="evolution run → per-axis animated SVG")
    ap.add_argument("run_dir", help="run output dir (with snapshot_gen_*.json + per-axis breakdown)")
    ap.add_argument("--out", default=None, help="output svg (default: <run_dir>/axes.svg)")
    args = ap.parse_args()
    run_dir = Path(args.run_dir)
    out = Path(args.out) if args.out else run_dir / "axes.svg"
    svg = render(run_dir)
    out.write_text(svg, encoding="utf-8")
    print(f"wrote {out}  ({len(svg)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
