# SPDX-License-Identifier: Apache-2.0
"""render_evolution_svg() — animated SVG (SMIL) fitness renderer の単体テスト.

確認項目:

- 合成 metrics (10-20 世代) で render → ``<svg`` 開始 / ``</svg>`` 終了
- ``xml.dom.minidom.parseString`` で well-formed (parse 成功)
- ``<animate`` を含む (アニメーションがある)
- SMIL のみ — JavaScript (script / on* / javascript:) を一切含まない
- best_score の最大値が SVG テキストに反映される
- proxy 注記 ("proxy fitness (NOT real LLM eval)") が含まれる
- founder 注記が含まれる (指定時)
- max_points で点数が制限される (ダウンサンプリング)
- out_path 指定でファイルが書かれ, 戻り値と一致する
- 空 metrics は ValueError
"""

from __future__ import annotations

import re
import xml.dom.minidom as minidom

import pytest

from llive.perf.evolutionary import (
    PROXY_NOTE,
    load_metrics_jsonl,
    render_evolution_svg,
)
from llive.perf.evolutionary.svg_render import _downsample


# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------


def _synthetic_rows(n: int = 15) -> list[dict]:
    """単調増加 best / mean + 変動 diversity の合成 metrics 行."""
    rows: list[dict] = []
    for g in range(n):
        frac = g / max(1, n - 1)
        best = 0.70 + 0.30 * frac  # 0.70 → 1.00
        mean = 0.50 + 0.45 * frac
        rows.append(
            {
                "generation": g,
                "n_individuals": 32,
                "best_score": round(best, 6),
                "mean_score": round(mean, 6),
                "std_score": round(0.12 * (1 - frac), 6),
                "median_score": round(mean, 6),
                "diversity_l2": round(28.0 - 18.0 * frac + (g % 3) * 2.0, 6),
                "seed": g * 7,
            }
        )
    return rows


def _write_metrics(path, rows: list[dict]) -> None:
    import json

    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _parse_svg(svg: str) -> minidom.Document:
    """minidom で parse して Document を返す (失敗時は AssertionError)."""
    try:
        return minidom.parseString(svg)
    except Exception as exc:  # noqa: BLE001 - test では明確化目的
        raise AssertionError(f"SVG is not well-formed XML: {exc}\n---\n{svg[:600]}") from exc


# ---------------------------------------------------------------------------
# basic shape / well-formedness
# ---------------------------------------------------------------------------


def test_svg_starts_and_ends_correctly(tmp_path) -> None:
    metrics = tmp_path / "metrics.jsonl"
    _write_metrics(metrics, _synthetic_rows(15))
    svg = render_evolution_svg(metrics)
    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")


def test_svg_is_well_formed_xml(tmp_path) -> None:
    metrics = tmp_path / "metrics.jsonl"
    _write_metrics(metrics, _synthetic_rows(20))
    svg = render_evolution_svg(metrics)
    doc = _parse_svg(svg)
    assert doc.documentElement.tagName == "svg"


def test_svg_contains_animate(tmp_path) -> None:
    metrics = tmp_path / "metrics.jsonl"
    _write_metrics(metrics, _synthetic_rows(12))
    svg = render_evolution_svg(metrics)
    assert "<animate" in svg
    # well-formed XML 上でも 1 個以上の <animate> がある
    doc = _parse_svg(svg)
    assert len(doc.getElementsByTagName("animate")) >= 1


def test_no_javascript(tmp_path) -> None:
    metrics = tmp_path / "metrics.jsonl"
    _write_metrics(metrics, _synthetic_rows(15))
    svg = render_evolution_svg(metrics)
    assert "<script" not in svg.lower()
    assert "javascript:" not in svg.lower()
    assert re.search(r"\son[a-z]+=", svg, re.IGNORECASE) is None


# ---------------------------------------------------------------------------
# content reflects data (best score, proxy note, founders)
# ---------------------------------------------------------------------------


def test_best_score_max_in_svg(tmp_path) -> None:
    rows = _synthetic_rows(15)
    metrics = tmp_path / "metrics.jsonl"
    _write_metrics(metrics, rows)
    svg = render_evolution_svg(metrics)
    best_max = max(r["best_score"] for r in rows)
    # peak best=X.XXX 注記に最大値が 3 桁で出る
    assert f"{best_max:.3f}" in svg


def test_proxy_note_present_by_default(tmp_path) -> None:
    metrics = tmp_path / "metrics.jsonl"
    _write_metrics(metrics, _synthetic_rows(10))
    svg = render_evolution_svg(metrics)
    assert PROXY_NOTE in svg
    # title / desc の両方に注記が入る
    doc = _parse_svg(svg)
    desc = doc.getElementsByTagName("desc")[0].firstChild.data
    assert "proxy" in desc.lower()


def test_proxy_note_can_be_disabled(tmp_path) -> None:
    metrics = tmp_path / "metrics.jsonl"
    _write_metrics(metrics, _synthetic_rows(10))
    svg = render_evolution_svg(metrics, proxy=False)
    # proxy=False では注記文を出さない
    assert PROXY_NOTE not in svg
    # それでも well-formed
    _parse_svg(svg)


def test_founders_annotation_present(tmp_path) -> None:
    metrics = tmp_path / "metrics.jsonl"
    _write_metrics(metrics, _synthetic_rows(10))
    founders = ("furuse-kazufumi", "friston", "millidge", "isomura-takuya")
    svg = render_evolution_svg(metrics, founders=founders)
    for f in founders:
        assert f in svg


# ---------------------------------------------------------------------------
# downsampling
# ---------------------------------------------------------------------------


def test_max_points_limits_polyline_vertices(tmp_path) -> None:
    """1000 世代を max_points=50 に間引くと polyline 頂点が 50 程度になる."""
    metrics = tmp_path / "metrics.jsonl"
    _write_metrics(metrics, _synthetic_rows(1000))
    svg = render_evolution_svg(metrics, max_points=50)
    doc = _parse_svg(svg)
    # best_score polyline は最大 stroke-width 2.4 のもの。頂点数で判定する代わりに
    # 全 polyline のうち最大頂点数が max_points+α 以下であることを確認
    polylines = doc.getElementsByTagName("polyline")
    assert polylines, "expected at least one polyline"
    max_vertices = max(
        len(pl.getAttribute("points").split()) for pl in polylines
    )
    # 末尾を必ず含める実装上 +1 まで許容
    assert max_vertices <= 51, f"downsample failed: {max_vertices} vertices"


def test_downsample_keeps_endpoints() -> None:
    rows = _synthetic_rows(1000)
    ds = _downsample(rows, 100)
    assert len(ds) <= 101
    assert ds[0]["generation"] == 0
    assert ds[-1]["generation"] == 999


def test_downsample_noop_when_small() -> None:
    rows = _synthetic_rows(10)
    ds = _downsample(rows, 200)
    assert len(ds) == 10


def test_max_points_below_two_raises(tmp_path) -> None:
    metrics = tmp_path / "metrics.jsonl"
    _write_metrics(metrics, _synthetic_rows(10))
    with pytest.raises(ValueError, match="max_points"):
        render_evolution_svg(metrics, max_points=1)


# ---------------------------------------------------------------------------
# file output
# ---------------------------------------------------------------------------


def test_out_path_writes_file(tmp_path) -> None:
    metrics = tmp_path / "metrics.jsonl"
    _write_metrics(metrics, _synthetic_rows(15))
    out = tmp_path / "sub" / "evolution.svg"
    svg = render_evolution_svg(metrics, out_path=out)
    assert out.exists()
    written = out.read_text(encoding="utf-8")
    assert written == svg
    _parse_svg(written)


# ---------------------------------------------------------------------------
# edge cases
# ---------------------------------------------------------------------------


def test_empty_metrics_raises(tmp_path) -> None:
    metrics = tmp_path / "empty.jsonl"
    metrics.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="no metrics rows"):
        render_evolution_svg(metrics)


def test_missing_file_raises(tmp_path) -> None:
    metrics = tmp_path / "does_not_exist.jsonl"
    with pytest.raises(ValueError, match="no metrics rows"):
        render_evolution_svg(metrics)


def test_flat_scores_no_division_error(tmp_path) -> None:
    """全世代同一スコア (flat) でも division-by-zero せず well-formed."""
    rows = [
        {
            "generation": g,
            "best_score": 1.0,
            "mean_score": 1.0,
            "diversity_l2": 5.0,
        }
        for g in range(8)
    ]
    metrics = tmp_path / "flat.jsonl"
    _write_metrics(metrics, rows)
    svg = render_evolution_svg(metrics)
    _parse_svg(svg)
    assert "<animate" in svg


def test_load_metrics_jsonl_roundtrip(tmp_path) -> None:
    rows = _synthetic_rows(5)
    metrics = tmp_path / "m.jsonl"
    _write_metrics(metrics, rows)
    loaded = load_metrics_jsonl(metrics)
    assert len(loaded) == 5
    assert loaded[0]["generation"] == 0
    assert load_metrics_jsonl(tmp_path / "nope.jsonl") == []
