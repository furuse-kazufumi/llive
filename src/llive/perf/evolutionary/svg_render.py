# SPDX-License-Identifier: Apache-2.0
"""進化ダイナミクスの animated SVG (SMIL) 可視化 — fitness 時系列 (llive v0.C).

``run_persona_evolution`` が出す ``metrics.jsonl`` (毎世代 1 行の
:class:`PopulationStats` ダンプ) を読んで, **世代軸 fitness 折れ線** を
animated SVG (SMIL ``<animate>``) に変換する.

設計方針 (既存 ``lineage.py`` の Mermaid writer / ``phylogeny.py`` の
``to_animated_svg`` と揃える):

* **自己完結 SVG** — 外部 CSS / JS / フォント / 画像に依存しない. 純 Python の
  文字列生成のみ. GitHub README が SMIL SVG をレンダリングできることを前提.
* **SMIL only** — CSS animation でなく ``<animate>`` / ``<set>`` を使う
  (GitHub README は SMIL を再生するが CSS keyframe は再生しないため).
* **honest disclosure** — fitness は **proxy** (LLM 評価ではない). タイトル /
  キャプション / ``<desc>`` に "proxy fitness (NOT real LLM eval)" を必ず明記.
* **accessibility** — ``role="img"`` / ``<title>`` / ``<desc>`` を含む.

公開 API:

* :func:`render_evolution_svg` — metrics.jsonl → animated SVG 文字列
* :func:`load_metrics_jsonl` — metrics.jsonl を dict list に読み込む helper
"""

from __future__ import annotations

import json
from pathlib import Path

# proxy fitness であることの注記 (honest disclosure)。
# feedback_benchmark_honest_disclosure / persona_evolution の _proxy_fitness に対応。
PROXY_NOTE = "proxy fitness (NOT real LLM eval)"

# llive 進化系で使う palette (phylogeny.to_animated_svg と統一)
_COLOR_BG_TOP = "#0e1426"
_COLOR_BG_BOTTOM = "#0a0f17"
_COLOR_BEST = "#7ee787"  # best_score: 緑
_COLOR_MEAN = "#5dd1ff"  # mean_score: 水色
_COLOR_DIVERSITY = "#ffd166"  # diversity_l2: 黄
_COLOR_AXIS = "#64748b"
_COLOR_GRID = "#1e293b"
_COLOR_TEXT = "#e6edf3"
_COLOR_TEXT_DIM = "#94a3b8"


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------


def load_metrics_jsonl(path: Path | str) -> list[dict]:
    """``metrics.jsonl`` を全件読んで dict の list を返す.

    各行は :meth:`PopulationStats.to_dict` の出力
    (``generation`` / ``best_score`` / ``mean_score`` / ``std_score`` /
    ``median_score`` / ``diversity_l2`` / ...). 空行は無視する.
    存在しないファイルは空 list を返す (呼び出し側で長さ判定可能).
    """
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _xml_escape(text: str) -> str:
    """SVG text node / attribute 用の最小限 XML エスケープ."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _downsample(rows: list[dict], max_points: int) -> list[dict]:
    """等間隔抽出で ``rows`` を最大 ``max_points`` 件に間引く.

    先頭と末尾は必ず残す (世代 0 と最終世代を欠落させない). ``max_points`` 以下
    なら何もしない.
    """
    n = len(rows)
    if max_points < 2:
        raise ValueError(f"max_points must be >= 2, got {max_points}")
    if n <= max_points:
        return list(rows)
    # 等間隔の浮動小数 index を整数化 (重複は set で除去) し, 末尾を必ず含める
    indices = sorted(
        {round(i * (n - 1) / (max_points - 1)) for i in range(max_points)}
    )
    if indices[-1] != n - 1:
        indices.append(n - 1)
    return [rows[i] for i in indices]


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _polyline_points(
    xs: list[float],
    ys: list[float],
) -> str:
    """(x, y) 列を SVG polyline ``points`` 属性文字列にする."""
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys, strict=True))


def _path_length_estimate(xs: list[float], ys: list[float]) -> float:
    """折れ線の概算全長 (stroke-dasharray の draw-on アニメ用)."""
    total = 0.0
    for i in range(1, len(xs)):
        dx = xs[i] - xs[i - 1]
        dy = ys[i] - ys[i - 1]
        total += (dx * dx + dy * dy) ** 0.5
    return total


# ---------------------------------------------------------------------------
# main renderer
# ---------------------------------------------------------------------------


def render_evolution_svg(
    metrics_path: Path | str,
    *,
    out_path: Path | str | None = None,
    title: str = "llive persona evolution — fitness over generations",
    founders: tuple[str, ...] | list[str] | None = None,
    max_points: int = 200,
    proxy: bool = True,
    viewbox_width: int = 900,
    viewbox_height: int = 360,
    loop_seconds: float = 18.0,
) -> str:
    """``metrics.jsonl`` の fitness 時系列を animated SVG (SMIL) として返す.

    上段トラックに ``best_score`` / ``mean_score`` の折れ線を世代軸で描き,
    世代進行とともに線を「描き進める」(stroke-dashoffset を 0 まで animate) +
    左→右へ走る再生ヘッド (縦線) を重ねる. 下段トラックに ``diversity_l2`` の
    帯 (area) を別軸で描く.

    Parameters
    ----------
    metrics_path : Path | str
        ``run_persona_evolution`` が出力した metrics.jsonl のパス.
    out_path : Path | str | None
        指定すると SVG をこのパスに書き込む (戻り値は常に SVG 文字列).
    title : str
        SVG タイトル. 末尾に proxy 注記が自動付与される (``proxy=True`` 時).
    founders : tuple[str, ...] | list[str] | None
        founder persona ID 列. 与えるとキャプションに列挙する (honest
        disclosure: どの種から始めたか). None なら省略.
    max_points : int
        ダウンサンプリング後の最大点数. 1001 世代は重いので default 200 点に
        等間隔抽出する (先頭/末尾は必ず残す).
    proxy : bool
        True なら "proxy fitness (NOT real LLM eval)" 注記を title / caption /
        ``<desc>`` に挿入する (default True; llive の fitness は現状 proxy).
    viewbox_width, viewbox_height : int
        SVG viewBox サイズ.
    loop_seconds : float
        アニメーション 1 周の秒数 (draw-on + 再生ヘッド走査). default 18s.

    Returns
    -------
    str
        自己完結した animated SVG 文字列 (``<svg ...>...</svg>``).

    Raises
    ------
    ValueError
        ``max_points < 2`` または metrics が空のとき.
    """
    rows = load_metrics_jsonl(metrics_path)
    if not rows:
        raise ValueError(
            f"no metrics rows loaded from {metrics_path!r}; cannot render evolution SVG"
        )

    rows = _downsample(rows, max_points)
    n = len(rows)

    generations = [int(r.get("generation", i)) for i, r in enumerate(rows)]
    best = [_safe_float(r.get("best_score")) for r in rows]
    mean = [_safe_float(r.get("mean_score")) for r in rows]
    diversity = [_safe_float(r.get("diversity_l2")) for r in rows]

    gen_min, gen_max = generations[0], generations[-1]
    gen_span = max(1, gen_max - gen_min)

    # fitness 軸 (best/mean) の値域。proxy fitness は [0,1] 想定だが
    # 念のためデータ実値からも算出して clamp しない。
    score_vals = best + mean
    score_lo = min(score_vals)
    score_hi = max(score_vals)
    best_max = max(best)
    if score_hi - score_lo < 1e-9:
        score_hi = score_lo + 1.0  # flat な場合の division-by-zero 回避

    div_lo = min(diversity)
    div_hi = max(diversity)
    if div_hi - div_lo < 1e-9:
        div_hi = div_lo + 1.0

    # ----- layout -----
    margin_l = 56
    margin_r = 130  # legend 用に右側を空ける
    margin_t = 52
    plot_w = viewbox_width - margin_l - margin_r
    # 上段 (fitness) と下段 (diversity) の 2 トラック
    fitness_top = margin_t
    fitness_h = (viewbox_height - margin_t - 70) * 0.66
    div_top = fitness_top + fitness_h + 30
    div_h = (viewbox_height - margin_t - 70) * 0.34

    def gx(gen: int) -> float:
        return margin_l + (gen - gen_min) / gen_span * plot_w

    def fy(score: float) -> float:
        # 上が高スコア
        frac = (score - score_lo) / (score_hi - score_lo)
        return fitness_top + (1.0 - frac) * fitness_h

    def dy(value: float) -> float:
        frac = (value - div_lo) / (div_hi - div_lo)
        return div_top + (1.0 - frac) * div_h

    xs = [gx(g) for g in generations]
    best_ys = [fy(v) for v in best]
    mean_ys = [fy(v) for v in mean]
    div_ys = [dy(v) for v in diversity]

    best_len = _path_length_estimate(xs, best_ys) or 1.0
    mean_len = _path_length_estimate(xs, mean_ys) or 1.0

    # ----- title / caption (honest disclosure) -----
    full_title = title
    if proxy and PROXY_NOTE not in full_title:
        full_title = f"{title} [{PROXY_NOTE}]"

    caption_bits: list[str] = []
    if founders:
        caption_bits.append("founders: " + ", ".join(founders))
    caption_bits.append(f"{gen_max - gen_min + 1} gens ({n} pts shown)")
    if proxy:
        caption_bits.append(PROXY_NOTE)
    caption = " · ".join(caption_bits)

    # ----- build SVG -----
    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {viewbox_width} {viewbox_height}" '
        f'role="img" aria-label="{_xml_escape(full_title)}">'
    )
    parts.append(f"<title>{_xml_escape(full_title)}</title>")
    desc = (
        f"Animated line chart of evolutionary fitness over {gen_max - gen_min + 1} "
        f"generations (downsampled to {n} points). Top track: best_score (green) "
        f"and mean_score (cyan). Bottom track: diversity_l2 (yellow band). "
        f"Lines draw on left-to-right via SMIL stroke-dashoffset animation; a "
        f"vertical playhead sweeps across. "
    )
    if founders:
        desc += "Founders: " + ", ".join(founders) + ". "
    if proxy:
        desc += (
            f"IMPORTANT: fitness is a {PROXY_NOTE} — it is a structural proxy "
            f"score, not a real LLM task evaluation. "
        )
    desc += "Self-contained SMIL SVG, no JavaScript."
    parts.append(f"<desc>{_xml_escape(desc)}</desc>")

    # defs: background gradient + diversity area gradient
    parts.append("<defs>")
    parts.append(
        '<linearGradient id="evo_bg" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0%" stop-color="{_COLOR_BG_TOP}"/>'
        f'<stop offset="100%" stop-color="{_COLOR_BG_BOTTOM}"/>'
        "</linearGradient>"
    )
    parts.append(
        '<linearGradient id="evo_div_fill" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{_COLOR_DIVERSITY}" stop-opacity="0.55"/>'
        f'<stop offset="100%" stop-color="{_COLOR_DIVERSITY}" stop-opacity="0.04"/>'
        "</linearGradient>"
    )
    parts.append("</defs>")

    # background
    parts.append(
        f'<rect width="{viewbox_width}" height="{viewbox_height}" fill="url(#evo_bg)"/>'
    )

    # title text
    parts.append(
        f'<text x="{margin_l}" y="26" text-anchor="start" '
        f'fill="{_COLOR_TEXT}" font-family="ui-sans-serif,system-ui,sans-serif" '
        f'font-size="16" font-weight="700">{_xml_escape(full_title)}</text>'
    )
    # caption (honest disclosure: founders + proxy)
    parts.append(
        f'<text x="{margin_l}" y="43" text-anchor="start" '
        f'fill="{_COLOR_TEXT_DIM}" font-family="ui-sans-serif,system-ui,sans-serif" '
        f'font-size="10">{_xml_escape(caption)}</text>'
    )

    # ----- fitness track gridlines + Y axis labels -----
    n_grid = 4
    for i in range(n_grid + 1):
        frac = i / n_grid
        y = fitness_top + (1.0 - frac) * fitness_h
        val = score_lo + frac * (score_hi - score_lo)
        parts.append(
            f'<line x1="{margin_l:.1f}" y1="{y:.1f}" '
            f'x2="{margin_l + plot_w:.1f}" y2="{y:.1f}" '
            f'stroke="{_COLOR_GRID}" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{margin_l - 8:.1f}" y="{y + 3:.1f}" text-anchor="end" '
            f'fill="{_COLOR_TEXT_DIM}" font-family="ui-monospace,monospace" '
            f'font-size="9">{val:.2f}</text>'
        )
    # fitness track label
    parts.append(
        f'<text x="{margin_l:.1f}" y="{fitness_top - 6:.1f}" text-anchor="start" '
        f'fill="{_COLOR_TEXT_DIM}" font-family="ui-sans-serif,system-ui,sans-serif" '
        f'font-size="10" font-weight="600">{_xml_escape("fitness (" + PROXY_NOTE + ")") if proxy else "fitness"}</text>'
    )

    # ----- diversity track baseline + label -----
    parts.append(
        f'<line x1="{margin_l:.1f}" y1="{div_top + div_h:.1f}" '
        f'x2="{margin_l + plot_w:.1f}" y2="{div_top + div_h:.1f}" '
        f'stroke="{_COLOR_AXIS}" stroke-width="1"/>'
    )
    parts.append(
        f'<text x="{margin_l:.1f}" y="{div_top - 6:.1f}" text-anchor="start" '
        f'fill="{_COLOR_TEXT_DIM}" font-family="ui-sans-serif,system-ui,sans-serif" '
        f'font-size="10" font-weight="600">diversity_l2</text>'
    )
    parts.append(
        f'<text x="{margin_l - 8:.1f}" y="{div_top + 3:.1f}" text-anchor="end" '
        f'fill="{_COLOR_TEXT_DIM}" font-family="ui-monospace,monospace" '
        f'font-size="9">{div_hi:.0f}</text>'
    )
    parts.append(
        f'<text x="{margin_l - 8:.1f}" y="{div_top + div_h + 3:.1f}" text-anchor="end" '
        f'fill="{_COLOR_TEXT_DIM}" font-family="ui-monospace,monospace" '
        f'font-size="9">{div_lo:.0f}</text>'
    )

    # ----- X axis (generation) labels -----
    x_label_y = div_top + div_h + 16
    n_xticks = min(6, n)
    for i in range(n_xticks):
        gi = round(i * (n - 1) / max(1, n_xticks - 1))
        x = xs[gi]
        parts.append(
            f'<text x="{x:.1f}" y="{x_label_y:.1f}" text-anchor="middle" '
            f'fill="{_COLOR_TEXT_DIM}" font-family="ui-monospace,monospace" '
            f'font-size="9">{generations[gi]}</text>'
        )
    parts.append(
        f'<text x="{margin_l + plot_w / 2:.1f}" y="{x_label_y + 16:.1f}" '
        f'text-anchor="middle" fill="{_COLOR_TEXT_DIM}" '
        f'font-family="ui-sans-serif,system-ui,sans-serif" '
        f'font-size="10">generation</text>'
    )

    # ----- diversity area (draw-on via opacity reveal) -----
    div_area_pts = (
        f"{xs[0]:.1f},{div_top + div_h:.1f} "
        + _polyline_points(xs, div_ys)
        + f" {xs[-1]:.1f},{div_top + div_h:.1f}"
    )
    parts.append(
        f'<polygon points="{div_area_pts}" fill="url(#evo_div_fill)" '
        f'stroke="none" opacity="0">'
        f'<animate attributeName="opacity" values="0;1" begin="0s" '
        f'dur="{loop_seconds:.1f}s" fill="freeze" repeatCount="indefinite"/>'
        "</polygon>"
    )
    parts.append(
        f'<polyline points="{_polyline_points(xs, div_ys)}" fill="none" '
        f'stroke="{_COLOR_DIVERSITY}" stroke-width="1.4" opacity="0.85"/>'
    )

    # ----- mean_score line (draw-on) -----
    parts.append(
        f'<polyline points="{_polyline_points(xs, mean_ys)}" fill="none" '
        f'stroke="{_COLOR_MEAN}" stroke-width="1.8" stroke-linejoin="round" '
        f'stroke-linecap="round" '
        f'stroke-dasharray="{mean_len:.1f}" stroke-dashoffset="{mean_len:.1f}">'
        f'<animate attributeName="stroke-dashoffset" '
        f'values="{mean_len:.1f};0" begin="0s" dur="{loop_seconds:.1f}s" '
        f'fill="freeze" repeatCount="indefinite"/>'
        "</polyline>"
    )

    # ----- best_score line (draw-on, on top) -----
    parts.append(
        f'<polyline points="{_polyline_points(xs, best_ys)}" fill="none" '
        f'stroke="{_COLOR_BEST}" stroke-width="2.4" stroke-linejoin="round" '
        f'stroke-linecap="round" '
        f'stroke-dasharray="{best_len:.1f}" stroke-dashoffset="{best_len:.1f}">'
        f'<animate attributeName="stroke-dashoffset" '
        f'values="{best_len:.1f};0" begin="0s" dur="{loop_seconds:.1f}s" '
        f'fill="freeze" repeatCount="indefinite"/>'
        "</polyline>"
    )

    # ----- playhead (vertical line sweeping left->right) -----
    playhead_x0 = xs[0]
    playhead_x1 = xs[-1]
    parts.append(
        f'<line x1="{playhead_x0:.1f}" y1="{fitness_top:.1f}" '
        f'x2="{playhead_x0:.1f}" y2="{div_top + div_h:.1f}" '
        f'stroke="{_COLOR_TEXT}" stroke-width="1" stroke-opacity="0.45">'
        f'<animate attributeName="x1" values="{playhead_x0:.1f};{playhead_x1:.1f}" '
        f'begin="0s" dur="{loop_seconds:.1f}s" repeatCount="indefinite"/>'
        f'<animate attributeName="x2" values="{playhead_x0:.1f};{playhead_x1:.1f}" '
        f'begin="0s" dur="{loop_seconds:.1f}s" repeatCount="indefinite"/>'
        "</line>"
    )

    # best_score travelling marker (dot riding the playhead along the best line)
    # 各セグメントで x が線形に進むと仮定し values 列で y を追う
    best_x_vals = ";".join(f"{x:.1f}" for x in xs)
    best_y_vals = ";".join(f"{y:.1f}" for y in best_ys)
    parts.append(
        f'<circle cx="{xs[0]:.1f}" cy="{best_ys[0]:.1f}" r="4" '
        f'fill="{_COLOR_BEST}" stroke="{_COLOR_BG_BOTTOM}" stroke-width="1">'
        f'<animate attributeName="cx" values="{best_x_vals}" '
        f'begin="0s" dur="{loop_seconds:.1f}s" repeatCount="indefinite"/>'
        f'<animate attributeName="cy" values="{best_y_vals}" '
        f'begin="0s" dur="{loop_seconds:.1f}s" repeatCount="indefinite"/>'
        "</circle>"
    )

    # ----- final-value annotations -----
    parts.append(
        f'<text x="{xs[-1] + 6:.1f}" y="{best_ys[-1] + 3:.1f}" text-anchor="start" '
        f'fill="{_COLOR_BEST}" font-family="ui-monospace,monospace" '
        f'font-size="10" font-weight="600">best {best[-1]:.3f}</text>'
    )
    parts.append(
        f'<text x="{xs[-1] + 6:.1f}" y="{mean_ys[-1] + 3:.1f}" text-anchor="start" '
        f'fill="{_COLOR_MEAN}" font-family="ui-monospace,monospace" '
        f'font-size="10">mean {mean[-1]:.3f}</text>'
    )

    # ----- legend (top-right) -----
    legend_x = viewbox_width - margin_r + 14
    legend_y = margin_t + 4
    parts.append(
        f'<g transform="translate({legend_x} {legend_y})" '
        f'font-family="ui-sans-serif,system-ui,sans-serif" font-size="10" '
        f'fill="{_COLOR_TEXT_DIM}">'
    )
    legend_items = (
        ("best_score", _COLOR_BEST),
        ("mean_score", _COLOR_MEAN),
        ("diversity_l2", _COLOR_DIVERSITY),
    )
    for i, (label, color) in enumerate(legend_items):
        ly = i * 16
        parts.append(
            f'<line x1="0" y1="{ly}" x2="16" y2="{ly}" stroke="{color}" '
            f'stroke-width="3"/>'
        )
        parts.append(f'<text x="22" y="{ly + 3}">{label}</text>')
    parts.append("</g>")

    # ----- max-best annotation (so the peak proxy value appears in SVG text) -----
    parts.append(
        f'<text x="{legend_x}" y="{legend_y + 3 * 16 + 14}" text-anchor="start" '
        f'fill="{_COLOR_TEXT_DIM}" font-family="ui-monospace,monospace" '
        f'font-size="9">peak best={best_max:.3f}</text>'
    )

    # ----- footer (honest disclosure repeated) -----
    footer = f"~{loop_seconds:.0f}s loop · SMIL · no JS"
    if proxy:
        footer += f" · {PROXY_NOTE}"
    parts.append(
        f'<text x="{viewbox_width - 12}" y="{viewbox_height - 10}" '
        f'text-anchor="end" fill="{_COLOR_AXIS}" '
        f'font-family="ui-sans-serif,system-ui,sans-serif" '
        f'font-size="9">{_xml_escape(footer)}</text>'
    )

    parts.append("</svg>")
    svg = "".join(parts)

    if out_path is not None:
        op = Path(out_path)
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(svg, encoding="utf-8")

    return svg


__all__ = [
    "PROXY_NOTE",
    "load_metrics_jsonl",
    "render_evolution_svg",
]
