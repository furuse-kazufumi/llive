#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Evolution-run **response & score timeseries** viewer (observability).

ユーザー要望 (2026-05-26)
-------------------------
「複数個体が一つの (複雑な) prompt にそれぞれどう答えるかを **時系列** で見たい。
選択圧に使うスコアも見たい。先ず、ビューワーが不足している」。

本ビューワーは lldarwin の real-pressure run ディレクトリの ``snapshot_gen_*.json`` を
**世代横断** で読み、各個体について以下を **時系列 (世代 × 個体)** で表示する:

* **effective system prompt** — ``genome.c_prompt`` から
  :func:`llive.perf.evolutionary.real_pressures.genome_to_system_prompt` で再生成
  (= 評価時に実際に LLM へ被せた system prompt)。
* **per-axis breakdown** (typo / polysemy / multistep / calibration / context) と
  **total score** (= ε-lexicase 選択圧に使う値)。

``--responses`` (または run_dir 内 ``responses.jsonl`` 自動検出) があれば、各個体の
**実 LLM 応答テキスト** を system prompt キーで join して併記する (新しい response sink
= real_pressures.py の ``response_log`` で取得)。

出力:
* ターミナル表 (既定; cp932 console でも UTF-8 reconfigure)。
* ``--html`` で HTML テーブル (世代×個体×軸スコアのヒートセル + system prompt + 応答)。
* ``--svg`` で total-score 時系列の小型 SVG (個体トラジェクトリ)。

HONEST DISCLOSURE: snapshot は 5 世代ごとなので時系列は粗い。score は小バッテリ
(軸あたり 2-3 問) なのでノイジー — 一般能力主張ではなく「prompt 戦略が固定 LLM の
弱点をどれだけ緩和したか」の case-level 採点 (real_pressures.py docstring 参照)。

使い方::

    py -3.11 scripts/evolution_response_viewer.py
    py -3.11 scripts/evolution_response_viewer.py out/lldarwin_12h_realpressure_2026_05_26
    py -3.11 scripts/evolution_response_viewer.py <run_dir> --top 5 --html report.html --svg scores.svg
    py -3.11 scripts/evolution_response_viewer.py <run_dir> --responses path/to/responses.jsonl
"""
from __future__ import annotations

import argparse
import glob
import html as _html
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# RAPTOR/llive 共通: src/ を import path に (スクリプトは src 外から呼ばれる)。
_SRC = Path(__file__).resolve().parents[1] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from llive.perf.evolutionary.genome_3d import Genome3D  # noqa: E402
from llive.perf.evolutionary.real_pressures import genome_to_system_prompt  # noqa: E402


def _ensure_utf8_stdout() -> None:
    """Force stdout to UTF-8 (Windows cp932 mojibake guard).

    See memory ``feedback_cli_utf8_stdout_pattern``.
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):  # pragma: no cover
        pass


# 苦手軸の短縮ラベル (ヘッダ用)。
_AXIS_SHORT = {
    "typo_robustness": "typo",
    "polysemy_wsd": "poly",
    "multistep_robustness": "step",
    "calibration": "calib",
    "context_management": "ctx",
}


@dataclass
class EvalEntry:
    """1 個体 × 1 世代の評価エントリ."""

    generation: int
    individual_id: str
    system_prompt: str
    total_score: float
    breakdown: dict[str, float]  # "axis::tN" -> case score
    axis_scores: dict[str, float] = field(default_factory=dict)  # axis -> mean


# --------------------------------------------------------------------------
# loaders
# --------------------------------------------------------------------------
def _axis_of(key: str) -> str:
    return key.split("::", 1)[0]


def _axis_means(breakdown: dict[str, float]) -> dict[str, float]:
    by_axis: dict[str, list[float]] = defaultdict(list)
    for k, v in breakdown.items():
        by_axis[_axis_of(k)].append(float(v))
    return {a: sum(vs) / len(vs) for a, vs in by_axis.items() if vs}


def load_snapshots(run_dir: Path) -> list[EvalEntry]:
    """全 ``snapshot_gen_*.json`` を読み、世代×個体の評価エントリへ展開."""
    entries: list[EvalEntry] = []
    files = sorted(glob.glob(str(run_dir / "snapshot_gen_*.json")))
    for sf in files:
        try:
            data = json.loads(Path(sf).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        gen = data.get("generation", 0)
        for ind in data.get("individuals", []):
            fit = ind.get("fitness") or {}
            breakdown = {k: float(v) for k, v in (fit.get("breakdown") or {}).items()}
            # genome.c_prompt -> effective system prompt (評価時の真の system prompt)。
            try:
                genome = Genome3D.from_dict(ind["genome"])
                system = genome_to_system_prompt(genome)
            except Exception:
                system = "(genome reconstruction failed)"
            entries.append(
                EvalEntry(
                    generation=gen,
                    individual_id=ind.get("individual_id", "?"),
                    system_prompt=system,
                    total_score=float(fit.get("score", 0.0)),
                    breakdown=breakdown,
                    axis_scores=_axis_means(breakdown),
                )
            )
    entries.sort(key=lambda e: (e.generation, -e.total_score))
    return entries


def load_responses(path: Path | None) -> dict[str, list[dict]]:
    """responses.jsonl を system prompt キーで束ねる.

    real_pressures.py の response_log が出す record:
    ``{"system","user","axis","response","score"}``。

    Returns ``{system_prompt -> [record, ...]}``。
    """
    by_system: dict[str, list[dict]] = defaultdict(list)
    if path is None or not path.exists():
        return by_system
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        sys_key = rec.get("system", "")
        by_system[sys_key].append(rec)
    return by_system


def discover_responses(run_dir: Path) -> Path | None:
    for name in ("responses.jsonl", "response_log.jsonl"):
        p = run_dir / name
        if p.exists():
            return p
    return None


# --------------------------------------------------------------------------
# terminal table
# --------------------------------------------------------------------------
def _short(text: str, n: int) -> str:
    text = text.replace("\n", " ").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def print_terminal(
    entries: list[EvalEntry],
    axes: list[str],
    *,
    top: int,
    responses: dict[str, list[dict]],
    show_prompt: bool,
) -> None:
    gens = sorted({e.generation for e in entries})
    by_gen: dict[int, list[EvalEntry]] = defaultdict(list)
    for e in entries:
        by_gen[e.generation].append(e)

    axis_hdr = "  ".join(f"{_AXIS_SHORT.get(a, a[:4]):>5}" for a in axes)
    print("=" * 78)
    print("llive real-pressure run — per-individual score timeseries (gen × individual)")
    print(f"snapshots: {len(gens)} generations  ·  axes: {', '.join(axes)}")
    print("score = ε-lexicase selection pressure value (mean of case scores)")
    print("=" * 78)
    for g in gens:
        rows = sorted(by_gen[g], key=lambda e: -e.total_score)[: max(1, top)]
        print(f"\n── gen {g:>4}  (showing top {len(rows)} of {len(by_gen[g])}) ──")
        print(f"  {'individual':<24} {'total':>6}   {axis_hdr}")
        for e in rows:
            axis_cells = "  ".join(f"{e.axis_scores.get(a, 0.0):5.2f}" for a in axes)
            iid = _short(e.individual_id, 24)
            print(f"  {iid:<24} {e.total_score:6.3f}   {axis_cells}")
            if show_prompt:
                print(f"      sys: {_short(e.system_prompt, 92)}")
            recs = responses.get(e.system_prompt)
            if recs:
                # 1 個 sample 応答を見せる (代表)。
                r = recs[0]
                print(
                    f"      ans[{_short(str(r.get('axis')),10)}]: "
                    f"q={_short(r.get('user',''), 38)} -> a={_short(r.get('response',''), 38)}"
                )
    if not responses:
        print(
            "\n(note: no responses.jsonl found — run with real_pressures response_log to "
            "capture actual LLM answers per individual. scores shown are from snapshots.)"
        )


# --------------------------------------------------------------------------
# HTML report
# --------------------------------------------------------------------------
def _score_color(v: float) -> str:
    # 0..1 -> muted red..green (defender/researcher 中立、CLAUDE.md の赤緑禁止は
    # status indicator (🔴/🟢) の話。連続スコアのヒートは可)。
    r = int(220 - 140 * v)
    g = int(90 + 110 * v)
    b = 90
    return f"rgb({r},{g},{b})"


def render_html(
    entries: list[EvalEntry],
    axes: list[str],
    *,
    responses: dict[str, list[dict]],
    run_dir: Path,
) -> str:
    gens = sorted({e.generation for e in entries})
    by_gen: dict[int, list[EvalEntry]] = defaultdict(list)
    for e in entries:
        by_gen[e.generation].append(e)

    esc = _html.escape
    parts: list[str] = [
        "<!doctype html><meta charset='utf-8'>",
        "<title>llive real-pressure response/score viewer</title>",
        "<style>",
        "body{background:#0b1020;color:#e5e7eb;font-family:ui-sans-serif,Segoe UI,sans-serif;margin:18px;}",
        "h1{font-size:19px;} h2{font-size:15px;color:#93c5fd;margin-top:26px;}",
        ".meta{color:#9ca3af;font-size:12px;}",
        "table{border-collapse:collapse;margin:8px 0 18px;font-size:12px;width:100%;}",
        "th,td{border:1px solid #1f2937;padding:3px 6px;text-align:left;vertical-align:top;}",
        "th{background:#111827;color:#cbd5e1;}",
        "td.sc{text-align:center;font-variant-numeric:tabular-nums;color:#0b1020;font-weight:600;}",
        ".sys{color:#cbd5e1;font-size:11px;max-width:520px;}",
        ".ans{color:#a7f3d0;font-size:11px;}",
        ".q{color:#fcd34d;}",
        "code{color:#e5e7eb;}",
        "</style>",
        "<h1>llive real-pressure run — per-individual response &amp; score timeseries</h1>",
        f"<div class='meta'>run: <code>{esc(str(run_dir))}</code> · "
        f"{len(gens)} snapshot generations · axes: {esc(', '.join(axes))} · "
        "score = ε-lexicase selection pressure (mean of case scores). "
        "Heat cells: red→green = 0→1. Small batteries = noisy estimate (honest disclosure).</div>",
    ]
    for g in gens:
        rows = sorted(by_gen[g], key=lambda e: -e.total_score)
        parts.append(f"<h2>generation {g} &middot; {len(rows)} individuals</h2>")
        parts.append("<table><tr><th>individual</th><th>total</th>")
        for a in axes:
            parts.append(f"<th>{esc(_AXIS_SHORT.get(a, a))}</th>")
        parts.append("<th>effective system prompt</th><th>sample answer</th></tr>")
        for e in rows:
            parts.append("<tr>")
            parts.append(f"<td><code>{esc(_short(e.individual_id, 28))}</code></td>")
            parts.append(
                f"<td class='sc' style='background:{_score_color(e.total_score)}'>"
                f"{e.total_score:.3f}</td>"
            )
            for a in axes:
                v = e.axis_scores.get(a, 0.0)
                parts.append(
                    f"<td class='sc' style='background:{_score_color(v)}'>{v:.2f}</td>"
                )
            parts.append(f"<td class='sys'>{esc(e.system_prompt)}</td>")
            recs = responses.get(e.system_prompt)
            if recs:
                # axis ごとに 1 件まで見せる (重複圧縮)。
                seen_axis: set = set()
                bits = []
                for r in recs:
                    ax = str(r.get("axis"))
                    if ax in seen_axis:
                        continue
                    seen_axis.add(ax)
                    bits.append(
                        f"<div><span class='q'>[{esc(ax)}] "
                        f"{esc(_short(r.get('user',''), 50))}</span> → "
                        f"<span class='ans'>{esc(_short(r.get('response',''), 60))}</span></div>"
                    )
                parts.append("<td>" + "".join(bits) + "</td>")
            else:
                parts.append("<td class='meta'>—</td>")
            parts.append("</tr>")
        parts.append("</table>")
    if not responses:
        parts.append(
            "<div class='meta'>No responses.jsonl found — actual LLM answers not "
            "captured. Re-run with real_pressures response_log to populate the "
            "'sample answer' column.</div>"
        )
    return "\n".join(parts)


# --------------------------------------------------------------------------
# SVG: total-score timeseries (one polyline per tracked individual id)
# --------------------------------------------------------------------------
def render_svg(entries: list[EvalEntry], *, max_lines: int = 40) -> str:
    gens = sorted({e.generation for e in entries})
    if not gens:
        return "<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'/>"
    gmin, gmax = gens[0], gens[-1]
    # per-individual trajectory (id が世代を跨いで生存する場合のみ折れ線になる)。
    by_id: dict[str, list[tuple[int, float]]] = defaultdict(list)
    # per-generation best/mean は必ず描く (時系列の背骨)。
    best: dict[int, float] = {}
    mean: dict[int, float] = {}
    by_gen: dict[int, list[float]] = defaultdict(list)
    for e in entries:
        by_id[e.individual_id].append((e.generation, e.total_score))
        by_gen[e.generation].append(e.total_score)
    for g, scs in by_gen.items():
        best[g] = max(scs)
        mean[g] = sum(scs) / len(scs)

    W, H = 920, 420
    ML, MR, MT, MB = 56, 24, 50, 44
    x0, x1, y0, y1 = ML, W - MR, MT, H - MB

    def sx(g: float) -> float:
        return x0 + (x1 - x0) * ((g - gmin) / ((gmax - gmin) or 1))

    def sy(v: float) -> float:
        return y1 - (y1 - y0) * v  # score 0..1

    parts = [
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}' "
        f"viewBox='0 0 {W} {H}' font-family='ui-sans-serif,Segoe UI,sans-serif'>",
        f"<rect width='{W}' height='{H}' fill='#0b1020'/>",
        f"<text x='{ML}' y='28' fill='#e5e7eb' font-size='17' font-weight='700'>"
        "llive real-pressure — total score timeseries (selection pressure)</text>",
        f"<text x='{ML}' y='{MT-8}' fill='#9ca3af' font-size='11'>"
        "faint lines = individual trajectories · bold = per-gen best/mean · "
        "snapshots every 5 gens (noisy small-battery estimate)</text>",
    ]
    for v in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = sy(v)
        parts.append(f"<line x1='{x0}' y1='{y:.1f}' x2='{x1}' y2='{y:.1f}' "
                     "stroke='#1f2937' stroke-width='1'/>")
        parts.append(f"<text x='{x0-8}' y='{y+4:.1f}' fill='#6b7280' font-size='10' "
                     f"text-anchor='end'>{v:.2f}</text>")
    # individual trajectories (faint) — limit to those with >=2 points.
    multi = [(i, pts) for i, pts in by_id.items() if len(pts) >= 2]
    for _, pts in multi[:max_lines]:
        pts.sort()
        d = " ".join(f"{sx(g):.1f},{sy(s):.1f}" for g, s in pts)
        parts.append(f"<polyline points='{d}' fill='none' stroke='#64748b' "
                     "stroke-width='0.8' stroke-opacity='0.35'/>")
    # best/mean backbone.
    best_d = " ".join(f"{sx(g):.1f},{sy(best[g]):.1f}" for g in gens)
    mean_d = " ".join(f"{sx(g):.1f},{sy(mean[g]):.1f}" for g in gens)
    parts.append(f"<polyline points='{mean_d}' fill='none' stroke='#fbbf24' stroke-width='2'/>")
    parts.append(f"<polyline points='{best_d}' fill='none' stroke='#34d399' stroke-width='2.4'/>")
    # x ticks
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        g = round(gmin + (gmax - gmin) * frac)
        parts.append(f"<text x='{sx(g):.1f}' y='{y1+18:.1f}' fill='#6b7280' "
                     f"font-size='10' text-anchor='middle'>{g}</text>")
    parts.append(f"<text x='{(x0+x1)/2:.0f}' y='{y1+38:.0f}' fill='#9ca3af' "
                 "font-size='11' text-anchor='middle'>generation</text>")
    # legend
    parts.append(f"<rect x='{x1-150}' y='{MT}' width='10' height='10' fill='#34d399'/>")
    parts.append(f"<text x='{x1-135}' y='{MT+9}' fill='#cbd5e1' font-size='11'>per-gen best</text>")
    parts.append(f"<rect x='{x1-150}' y='{MT+16}' width='10' height='10' fill='#fbbf24'/>")
    parts.append(f"<text x='{x1-135}' y='{MT+25}' fill='#cbd5e1' font-size='11'>per-gen mean</text>")
    parts.append("</svg>")
    return "\n".join(parts)


# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    ap = argparse.ArgumentParser(
        prog="evolution_response_viewer",
        description="per-individual response & score timeseries viewer",
    )
    ap.add_argument(
        "run_dir",
        nargs="?",
        default="out/lldarwin_12h_realpressure_2026_05_26",
        help="run output dir (既定: 12h real-pressure run)",
    )
    ap.add_argument("--top", type=int, default=6,
                    help="ターミナル表で各世代に表示する個体数 (score 降順)")
    ap.add_argument("--responses", type=Path, default=None,
                    help="responses.jsonl (省略時は run_dir 内を自動検出)")
    ap.add_argument("--no-prompt", action="store_true",
                    help="ターミナルで system prompt 行を省略")
    ap.add_argument("--html", type=Path, default=None,
                    help="HTML レポート出力先 (例: <run_dir>/response_viewer.html)")
    ap.add_argument("--svg", type=Path, default=None,
                    help="total-score 時系列 SVG 出力先")
    args = ap.parse_args(argv)

    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        print(f"[ERROR] run dir not found: {run_dir}", file=sys.stderr)
        return 2

    entries = load_snapshots(run_dir)
    if not entries:
        print(f"[ERROR] no snapshot_gen_*.json with individuals in {run_dir}", file=sys.stderr)
        return 1

    # 軸順は最初のエントリの breakdown 出現順を尊重 (typo→poly→...→ctx)。
    axes: list[str] = []
    for k in entries[0].breakdown:
        a = _axis_of(k)
        if a not in axes:
            axes.append(a)

    resp_path = args.responses or discover_responses(run_dir)
    responses = load_responses(resp_path)

    print_terminal(entries, axes, top=args.top, responses=responses,
                   show_prompt=not args.no_prompt)

    if args.html:
        html_doc = render_html(entries, axes, responses=responses, run_dir=run_dir)
        args.html.write_text(html_doc, encoding="utf-8")
        print(f"\nwrote HTML report: {args.html}  ({len(html_doc)} bytes)")
    if args.svg:
        svg_doc = render_svg(entries)
        args.svg.write_text(svg_doc, encoding="utf-8")
        print(f"wrote SVG timeseries: {args.svg}  ({len(svg_doc)} bytes)")
    if resp_path:
        print(f"responses joined from: {resp_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
