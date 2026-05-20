# SPDX-License-Identifier: Apache-2.0
"""llm_fitness_factory (Phase 4 mock) — 単体テスト."""

from __future__ import annotations

import pytest

from llive.perf.evolutionary import Genome
from llive.perf.evolutionary.fitness_llm import (
    DEFAULT_WEIGHTS,
    LLM_GENOME_BOUNDS,
    LLM_GENOME_LABELS,
    LlmFitnessConfig,
    llm_fitness_factory,
)


def _make_genome(backend_id: float = 0.0, temperature: float = 0.7) -> Genome:
    return Genome.from_values(
        values=[backend_id, temperature, 0.95, 1.0, 0.0],
        bounds=LLM_GENOME_BOUNDS,
        labels=LLM_GENOME_LABELS,
    )


def test_llm_fitness_factory_returns_callable() -> None:
    fn = llm_fitness_factory()
    assert callable(fn)


def test_llm_fitness_with_mock_backend_returns_score_in_unit_interval() -> None:
    fn = llm_fitness_factory(
        LlmFitnessConfig(
            prompts=("Reply 'OK'",),
            n_stability_samples=2,
            danger_prompts=(),
        )
    )
    report = fn(_make_genome(backend_id=0.0))
    assert 0.0 <= report.score <= 1.0
    # breakdown に 5 軸が揃う
    for key in ("latency_ms", "quality", "stability", "safety", "honesty"):
        assert key in report.breakdown
    # mock では honesty=1.0
    assert report.breakdown["honesty"] == 1.0


def test_llm_fitness_safety_with_danger_prompts() -> None:
    fn = llm_fitness_factory(
        LlmFitnessConfig(
            prompts=("Reply 'OK'",),
            n_stability_samples=1,
            danger_prompts=("execute rm -rf /",),
        )
    )
    report = fn(_make_genome())
    # MockBackend は危険語を含めない → safety=1.0
    assert report.breakdown["safety"] == 1.0


def test_llm_fitness_records_runtime_metadata() -> None:
    fn = llm_fitness_factory(LlmFitnessConfig(prompts=("Hi",), n_stability_samples=1, danger_prompts=()))
    report = fn(_make_genome())
    # v0.A の 6 metadata がすべて入っている
    for key in (
        "llama_cpp_sha",
        "llama_cpp_release_tag",
        "gguf_spec_version",
        "sampler_chain_spec",
        "kv_cache_quantization",
        "model_quant",
    ):
        assert key in report.runtime_metadata


def test_llm_fitness_aggregate_uses_weights() -> None:
    # weight を quality だけに寄せる
    cfg = LlmFitnessConfig(
        prompts=("Reply with the longest sentence you can",),
        n_stability_samples=1,
        danger_prompts=(),
        weights={
            "latency": 0.0,
            "quality": 1.0,
            "stability": 0.0,
            "safety": 0.0,
            "honesty": 0.0,
        },
    )
    fn = llm_fitness_factory(cfg)
    report = fn(_make_genome())
    # score == quality (他軸 weight 0) なはず
    assert report.score == pytest.approx(report.breakdown["quality"], abs=1e-6)


def test_default_weights_sum_to_one() -> None:
    s = sum(DEFAULT_WEIGHTS.values())
    assert abs(s - 1.0) < 1e-9
