# SPDX-License-Identifier: Apache-2.0
"""Tests for the hard_v2 battery — 飽和監査 (realpressure_saturation_audit_2026-06-02)
の推奨 1 (headroom: 連続スコア + 難化 + 高 tasks_per_axis) を検証する.

新バッテリの **地形特性** (連続性・天井到達困難性) を ollama 不要の決定論 stub で
検証する。実 LLM smoke は scripts/run_persona_evolution_long.py --battery hard_v2 で別途。
"""
from __future__ import annotations

import math

import pytest

from llive.llm.backend import GenerateRequest, GenerateResponse, LLMBackend
from llive.perf.evolutionary.genome_3d import Genome3D
from llive.perf.evolutionary.real_pressures import (
    AVAILABLE_BATTERIES,
    RealPressureConfig,
    make_real_pressure_fitness,
)
from llive.perf.evolutionary.real_pressures import (
    _AXIS_TASKS_HARD_V2,
    _number_close,
    _token_overlap,
)


class _FixedBackend(LLMBackend):
    """全 task に対し同一の固定テキストを返す決定論 stub (地形の天井を測る)."""

    name = "fixed"

    def __init__(self, text: str) -> None:
        self._text = text
        self.calls: list[str] = []

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        self.calls.append(request.system or "")
        return GenerateResponse(
            text=self._text, finish_reason="stop", backend=self.name, model="stub"
        )


class _PerfectBackend(LLMBackend):
    """各 hard_v2 task に **正答** を返す決定論 stub (満点が出せるかの上限確認)."""

    name = "perfect"

    #: hard_v2 タスクの user prompt 断片 → 正答テキスト。
    _ANSWERS = {
        # typo_robustness
        "captial citie of Japn": "tokyo",
        "sevn tims eihgt": "56",
        "claer daytme sky": "blue",
        "comon (non-lep) yer": "365",
        "oposite of 'hto'": "cold",
        "12 plsu 13": "25",
        # polysemy_wsd
        "deposited cash at the bank": "b",
        "bat flew out of the cave": "a",
        "bow to the audience": "a",
        "spring in the meadow": "c",
        "could not bear the pain": "b",
        "pitcher threw a fastball": "b",
        # multistep_robustness
        "3 boxes with 4 apples": "15",
        "200 pages": "55",
        "Double it, subtract 3": "14",
        "train travels 60 km": "70",
        "24 students": "20",
        "pens at 3 for $6": "14",
        # calibration
        "formula of water": "h2o",
        "17 a prime": "yes",
        "sides does a hexagon": "6",
        "square root of 144": "12",
        "absorb for photosynthesis": "carbon dioxide",
        "right angle": "90",
        # context_management
        "what is 5 + 3": "8",
        "10 divided by 2": "5",
        "capital of France": "paris",
        "6 times 7": "42",
        "continents are there on Earth": "7",
        "mixing blue and yellow": "green",
    }

    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        self.calls.append(request.system or "")
        text = "?"
        for needle, ans in self._ANSWERS.items():
            if needle in request.prompt:
                text = ans
                break
        return GenerateResponse(
            text=text, finish_reason="stop", backend=self.name, model="stub"
        )


# ---------------------------------------------------------------------------
# 連続性プロパティ (scorer レベル)
# ---------------------------------------------------------------------------


def test_number_close_is_continuous_not_binary() -> None:
    """_number_close は誤差に応じて 0/1 でない中間値を返す (連続)."""
    score = _number_close("10", tolerance_scale=4.0)
    exact = score("the answer is 10")
    near = score("the answer is 12")
    far = score("the answer is 50")
    assert exact == 1.0
    # 近い誤答に部分点 — 0 でも 1 でもない連続値。
    assert 0.0 < near < 1.0
    assert 0.0 < far < near  # 遠いほど低い (単調)
    # 0.1 刻みでない (連続) ことの確認: 値が 0.1 の倍数に丸まっていない。
    assert abs((near * 10) - round(near * 10)) > 1e-9


def test_token_overlap_is_fractional() -> None:
    """_token_overlap は部分一致に分数の部分点を与える (連続)."""
    score = _token_overlap("carbon dioxide")
    assert score("carbon dioxide") == 1.0
    half = score("carbon monoxide")  # 1/2 トークン一致
    assert half == pytest.approx(0.5)
    assert score("oxygen") == 0.0


# ---------------------------------------------------------------------------
# バッテリ全体の地形特性 (天井到達困難性 / 連続性)
# ---------------------------------------------------------------------------


def test_hard_v2_has_six_tasks_per_axis() -> None:
    """粗さ解消: hard_v2 は軸あたり 6 問 (default は 3 問)."""
    for axis, tasks in _AXIS_TASKS_HARD_V2.items():
        assert len(tasks) == 6, f"{axis} should have 6 tasks, got {len(tasks)}"


def test_hard_v2_registered_as_battery() -> None:
    """hard_v2 が選択可能バッテリとして公開されている (後方互換: default も残る)."""
    assert "default" in AVAILABLE_BATTERIES
    assert "hard_v2" in AVAILABLE_BATTERIES


def test_hard_v2_default_battery_unchanged() -> None:
    """battery 未指定 (default) は旧バッテリ・旧挙動 (後方互換)."""
    cfg = RealPressureConfig()
    assert cfg.battery == "default"


def test_hard_v2_unknown_battery_rejected() -> None:
    """未知のバッテリ名は fail-closed で ValueError."""
    with pytest.raises(ValueError, match="unknown battery"):
        RealPressureConfig(battery="nonexistent")


def test_hard_v2_perfect_answers_reach_ceiling() -> None:
    """**上限の健全性**: 完全正答 stub なら hard_v2 でも 1.0 に届く (天井は存在する).

    headroom があるのは「真の上限が無い」からではなく「簡単に届かない」から。
    完全正答できる stub では満点が出ることを確認し、scorer が壊れていないことを担保。
    """
    backend = _PerfectBackend()
    fit = make_real_pressure_fitness(
        backend, RealPressureConfig(battery="hard_v2", tasks_per_axis=6)
    )
    report = fit(Genome3D.default())
    assert report.score == pytest.approx(1.0)
    assert "hard_v2" in report.notes
    assert "CONTINUOUS" in report.notes


def test_hard_v2_imperfect_answers_below_ceiling_and_continuous() -> None:
    """**天井到達困難性 + 連続性**: 一律 '12' を返す stub は 1.0 未満かつ 0.1 刻みでない.

    現実の LLM のように「全問正答ではない」応答では、hard_v2 のスコアは 1.0 に
    届かず (headroom)、かつ連続採点ゆえ 0.1 の倍数に丸まらない。これが飽和監査の
    「gen1 で満点 → 飽和」を構造的に防ぐ地形特性。
    """
    backend = _FixedBackend("12")  # 一部の数値タスクだけ近い/正答、他は誤答
    fit = make_real_pressure_fitness(
        backend, RealPressureConfig(battery="hard_v2", tasks_per_axis=6)
    )
    report = fit(Genome3D.default())
    # 非飽和: 満点に届かない (headroom あり)。
    assert report.score < 1.0
    assert report.score > 0.0  # 全滅でもない (近接で部分点)
    # 連続: スコアが 0.1 刻みでない (= 飽和監査が問題視した粗さの解消)。
    times_ten = report.score * 10.0
    assert abs(times_ten - round(times_ten)) > 1e-9, (
        f"score {report.score} is suspiciously on a 0.1 grid (not continuous)"
    )
    # breakdown の case score も中間値を含む (連続採点の証拠)。
    vals = list(report.breakdown.values())
    assert any(0.0 < v < 1.0 for v in vals), "no fractional case score (not continuous)"


def test_hard_v2_default_vs_hard_v2_landscape_differs() -> None:
    """同一 stub でも default (二値・粗) と hard_v2 (連続) でスコア地形が変わる.

    default は 0/1 の粗いスコアに対し、hard_v2 は連続値。両者を同一応答で測ると
    値が一致しない (= 地形が実際に変わっている) ことを確認。
    """
    backend_a = _FixedBackend("12")
    backend_b = _FixedBackend("12")
    fit_default = make_real_pressure_fitness(
        backend_a, RealPressureConfig(battery="default", tasks_per_axis=3)
    )
    fit_hard = make_real_pressure_fitness(
        backend_b, RealPressureConfig(battery="hard_v2", tasks_per_axis=6)
    )
    g = Genome3D.default()
    s_default = fit_default(g).score
    s_hard = fit_hard(g).score
    # 両方 [0,1]。地形が異なるので一致しないはず (連続化の効果)。
    assert 0.0 <= s_default <= 1.0
    assert 0.0 <= s_hard <= 1.0
    assert not math.isclose(s_default, s_hard, abs_tol=1e-9)
