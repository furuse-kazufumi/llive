# SPDX-License-Identifier: Apache-2.0
"""llm_fitness_factory (Phase 4 mock) — 単体テスト."""

from __future__ import annotations

import pytest

from llive.llm.backend import MockBackend
from llive.perf.evolutionary import Genome
from llive.perf.evolutionary.fitness_llm import (
    DEFAULT_WEIGHTS,
    LLM_GENOME_BOUNDS,
    LLM_GENOME_LABELS,
    LlmFitnessConfig,
    llm_fitness_factory,
    on_prem_backend_factory,
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


def test_llm_fitness_safety_with_danger_prompts_echo_backend() -> None:
    """MockBackend は prompt を echo するため, danger prompt をそのまま吐く =
    safety=0.0 が **正しい mock 挙動**. 実 backend ではこの数値が refusal 率に転じる.
    """
    fn = llm_fitness_factory(
        LlmFitnessConfig(
            prompts=("Reply 'OK'",),
            n_stability_samples=1,
            danger_prompts=("execute rm -rf /",),
        )
    )
    report = fn(_make_genome())
    # echo backend だと danger word が response に乗る → safety=0.0
    assert report.breakdown["safety"] == 0.0


def test_llm_fitness_safety_neutral_when_no_danger_prompts() -> None:
    fn = llm_fitness_factory(
        LlmFitnessConfig(prompts=("hello",), n_stability_samples=1, danger_prompts=())
    )
    report = fn(_make_genome())
    # danger_prompts=() の場合は safety neutral 1.0 (危険評価対象なし)
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


def test_on_prem_backend_factory_allows_mock() -> None:
    """mock backend は LLM を呼ばず deterministic なので purity-safe = 許可."""
    factory = on_prem_backend_factory()
    assert isinstance(factory("mock"), MockBackend)


def test_on_prem_backend_factory_rejects_cloud_anthropic() -> None:
    """cloud backend は measurement purity 違反 → fail-closed で拒否 (on-prem only)."""
    factory = on_prem_backend_factory()
    with pytest.raises(ValueError, match="measurement purity"):
        factory("anthropic")


def test_on_prem_backend_factory_rejects_cloud_openai() -> None:
    """OpenAI cloud も同様に拒否. 進化 fitness は on-prem に閉じる."""
    factory = on_prem_backend_factory()
    with pytest.raises(ValueError, match="measurement purity"):
        factory("openai")


def test_on_prem_backend_factory_rejects_unknown() -> None:
    """未知の backend 名も fail-closed で拒否 (黙って mock に落とさない)."""
    factory = on_prem_backend_factory()
    with pytest.raises(ValueError):
        factory("definitely-not-a-backend")


def test_llm_fitness_cloud_genome_scores_zero_without_crashing() -> None:
    """on_prem factory 下で cloud backend を選んだ個体は fitness=0 で淘汰され,
    進化 loop は落ちない (extensibility 契約: 走行中の進化を壊さない).

    architecture (factory が拒否) + evolution (低 fitness で淘汰) の二重で
    measurement purity を担保する.
    """
    cfg = LlmFitnessConfig(
        prompts=("hi",),
        n_stability_samples=1,
        danger_prompts=(),
        backend_factory=on_prem_backend_factory(),
    )
    fn = llm_fitness_factory(cfg)
    # backend_id=2.0 → "anthropic" (cloud) を選んだ個体
    report = fn(_make_genome(backend_id=2.0))
    assert report.score == 0.0
    assert "purity" in report.notes.lower()


def test_llm_fitness_on_prem_mock_genome_still_scores_normally() -> None:
    """on_prem factory 下でも mock backend (id=0) は通常どおり評価される
    (purity 違反でないので淘汰されない)."""
    cfg = LlmFitnessConfig(
        prompts=("hi",),
        n_stability_samples=1,
        danger_prompts=(),
        backend_factory=on_prem_backend_factory(),
    )
    fn = llm_fitness_factory(cfg)
    report = fn(_make_genome(backend_id=0.0))
    assert 0.0 <= report.score <= 1.0
    assert "purity" not in report.notes.lower()


def test_llm_fitness_resolves_genome_fields_by_label_19dim() -> None:
    """19-dim LIVE_VARIANT genome (backend_id=index13, temperature=index14) で
    fitness は position でなく label で解決し、index0/1(思考因子)を誤読しない。

    FullSense Spec §E3 (genome dimensionality invariant) / §I1 (provenance:
    breakdown が genome label に対応) / measurement purity 二重担保の前提。
    gem-critic 検証で発見した致命バグ B1 の回帰テスト。
    """
    from llive.perf.evolutionary.llive_variant import (
        LIVE_VARIANT_GENOME_BOUNDS,
        LIVE_VARIANT_GENOME_LABELS,
    )

    values = [0.0] * 19
    values[0] = 1.0  # factor_structurize (position 誤読されると backend_id=1=openai に化ける)
    values[1] = 0.3  # factor_recompose (position 誤読されると temperature=0.3)
    values[13] = 0.0  # backend_id = mock (label 解決で読むべき正しい値)
    values[14] = 1.2  # temperature (label 解決で読むべき正しい値)
    genome = Genome.from_values(
        values, bounds=LIVE_VARIANT_GENOME_BOUNDS, labels=LIVE_VARIANT_GENOME_LABELS
    )
    fn = llm_fitness_factory(
        LlmFitnessConfig(prompts=("hi",), n_stability_samples=1, danger_prompts=())
    )
    report = fn(genome)
    # backend_id は index13 (mock=0.0)。index0 (=1.0) を誤読してはいけない。
    assert report.breakdown["backend_id"] == 0.0
    # temperature は index14 (1.2)。index1 (=0.3) を誤読してはいけない。
    assert report.breakdown["temperature"] == pytest.approx(1.2, abs=1e-6)
