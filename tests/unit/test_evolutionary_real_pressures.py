# SPDX-License-Identifier: Apache-2.0
"""Tests for lldarwin Stage2 後半 — 実 LLM 苦手軸 fitness (real_pressures.py).

ollama 不要の決定論部分 (個体→system prompt 写像 / 採点 / キャッシュ) を検証する。
実 LLM 呼び出しは stub backend で代替 (実 ollama smoke は別途 scripts で)。
"""
from __future__ import annotations

from llive.llm.backend import GenerateRequest, GenerateResponse, LLMBackend
from llive.perf.evolutionary.genome_3d import Genome3D
from llive.perf.evolutionary.prompt_chromosome import PromptChromosome
from llive.perf.evolutionary.real_pressures import (
    RealPressureConfig,
    genome_to_system_prompt,
    make_real_pressure_fitness,
)


class _StubBackend(LLMBackend):
    """task の user prompt に応じて固定の正答/誤答を返す決定論 stub."""

    name = "stub"

    def __init__(self, answers: dict[str, str], *, calls: list[str] | None = None) -> None:
        self._answers = answers
        self.calls = calls if calls is not None else []

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        self.calls.append(request.system or "")
        text = "?"
        for needle, ans in self._answers.items():
            if needle in request.prompt:
                text = ans
                break
        return GenerateResponse(text=text, finish_reason="stop", backend=self.name, model="stub")


def test_system_prompt_reflects_prompt_chromosome() -> None:
    """c_prompt の skill / template が system prompt に反映される."""
    cp = PromptChromosome(
        persona_set=("polya",),
        skill_set=("ground", "structurize"),
        rule_set=("fail_closed",),
        prompt_template_id="chain_of_thought",
        language_style="terse",
        historical_quote_density=0.1,
    )
    base = Genome3D.default()
    g = Genome3D(c_impl=base.c_impl, c_prompt=cp, c_meta=base.c_meta, c_factors=base.c_factors)
    sys = genome_to_system_prompt(g)
    assert "Ignore irrelevant" in sys  # ground skill
    assert "step by step" in sys.lower()  # chain_of_thought
    # 異なる c_prompt は異なる system prompt → 異なる LLM 挙動 (選択信号の源)。
    cp2 = PromptChromosome(
        persona_set=(),
        skill_set=("perspective",),
        rule_set=(),
        prompt_template_id="base",
        language_style="verbose",
        historical_quote_density=0.0,
    )
    g2 = Genome3D(c_impl=base.c_impl, c_prompt=cp2, c_meta=base.c_meta, c_factors=base.c_factors)
    assert genome_to_system_prompt(g2) != sys


def test_fitness_scores_real_tasks_via_backend() -> None:
    """stub backend が全問正答すれば各 case が 1.0 になる."""
    correct = {
        "captial of Japan": "tokyo",
        "7 tims 8": "56",
        "clear daytime sky": "blue",
        "deposited cash": "b",
        "bat flew": "a",
        "bow to the audience": "a",
        "3 boxes with 4 apples": "10",
        "200 pages": "80",
        "Double it": "7",
        "formula of water": "H2O",
        "17 a prime": "yes",
        "sides does a triangle": "3",
        "5 + 3": "8",
        "10 divided by 2": "5",
        "capital of France": "paris",
    }
    backend = _StubBackend(correct)
    fit = make_real_pressure_fitness(backend)
    g = Genome3D.default()
    report = fit(g)
    assert report.score == 1.0
    assert all(v == 1.0 for v in report.breakdown.values())
    assert "REAL on-prem LLM" in report.notes


def test_cache_avoids_duplicate_backend_calls() -> None:
    """同一 system prompt は再評価せずキャッシュを使う (12h throughput の核)."""
    backend = _StubBackend({"x": "y"})  # 全問誤答だが呼び出し数だけ見る
    cache: dict = {}
    fit = make_real_pressure_fitness(backend, cache=cache)
    g = Genome3D.default()
    fit(g)
    n_after_first = len(backend.calls)
    fit(g)  # 同一 genome → 同一 system prompt → 全部キャッシュヒット
    assert len(backend.calls) == n_after_first  # 追加呼び出しゼロ
    assert n_after_first == len(cache)  # 全 task がキャッシュ済


def test_backend_failure_is_scored_zero_not_crash() -> None:
    """backend 例外は task 失点 (0) で握り潰し、12h run を止めない."""

    class _BoomBackend(LLMBackend):
        name = "boom"

        def generate(self, request: GenerateRequest) -> GenerateResponse:
            raise RuntimeError("ollama down")

    fit = make_real_pressure_fitness(_BoomBackend())
    report = fit(Genome3D.default())
    assert report.score == 0.0  # 全失点だが例外は出ない


def test_config_axes_subset() -> None:
    """axes を絞れる (評価軸の部分集合)."""
    backend = _StubBackend({})
    fit = make_real_pressure_fitness(
        backend, RealPressureConfig(axes=("typo_robustness", "calibration"))
    )
    report = fit(Genome3D.default())
    axes = {k.split("::")[0] for k in report.breakdown}
    assert axes == {"typo_robustness", "calibration"}


def test_response_log_default_off_preserves_behavior() -> None:
    """response_log 未指定なら従来挙動 (記録なし・スコア不変・追加副作用なし)."""
    backend = _StubBackend({"captial of Japan": "tokyo"})
    fit_no_sink = make_real_pressure_fitness(backend)
    report = fit_no_sink(Genome3D.default())
    # additive: 既存 report 形状 (score / breakdown / notes) は不変。
    assert isinstance(report.score, float)
    assert report.breakdown  # 軸別 case score が入る
    assert "REAL on-prem LLM" in report.notes


def test_response_log_list_sink_captures_records() -> None:
    """list sink を渡すと (system, user, axis, response, score) が記録される."""
    answers = {"captial of Japan": "tokyo", "7 tims 8": "56"}
    backend = _StubBackend(answers)
    log: list = []
    fit = make_real_pressure_fitness(
        backend,
        RealPressureConfig(axes=("typo_robustness",), tasks_per_axis=3),
        response_log=log,
    )
    fit(Genome3D.default())
    # typo_robustness の 3 task 分が記録される。
    assert len(log) == 3
    rec = log[0]
    assert set(rec) == {"system", "user", "axis", "response", "score"}
    assert rec["axis"] == "typo_robustness"
    # 実応答テキストが復元できる (これまで失われていた情報)。
    assert rec["response"] == "tokyo"
    assert rec["score"] == 1.0
    # system prompt は genome.c_prompt 由来で非空。
    assert rec["system"]


def test_response_log_jsonl_path_sink(tmp_path) -> None:
    """str/Path sink を渡すと JSONL ファイルに 1 record/line で追記される."""
    import json

    backend = _StubBackend({"captial of Japan": "tokyo"})
    out = tmp_path / "responses.jsonl"
    fit = make_real_pressure_fitness(
        backend,
        RealPressureConfig(axes=("typo_robustness",), tasks_per_axis=1),
        response_log=str(out),
    )
    fit(Genome3D.default())
    assert out.exists()
    lines = [ln for ln in out.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["response"] == "tokyo"
    assert rec["axis"] == "typo_robustness"


def test_response_log_skips_cache_hits() -> None:
    """キャッシュヒット時は LLM を再呼出ししないため record を重複させない."""
    backend = _StubBackend({"captial of Japan": "tokyo"})
    log: list = []
    cache: dict = {}
    fit = make_real_pressure_fitness(
        backend,
        RealPressureConfig(axes=("typo_robustness",), tasks_per_axis=2),
        cache=cache,
        response_log=log,
    )
    g = Genome3D.default()
    fit(g)
    n_after_first = len(log)
    assert n_after_first == 2
    fit(g)  # 同一 system prompt → 全キャッシュヒット → 新規記録ゼロ
    assert len(log) == n_after_first
