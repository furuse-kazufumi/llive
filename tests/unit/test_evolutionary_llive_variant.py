# SPDX-License-Identifier: Apache-2.0
"""v0.C llive variant 進化レイヤ — 単体テスト."""

from __future__ import annotations

import numpy as np
import pytest

from llive.perf.evolutionary import (
    BlendCrossover,
    ChainedMutation,
    ElitismSelection,
    EvolutionConfig,
    EvolutionLoop,
    GaussianMutation,
    Genome,
    GenomeBounds,
    LIVE_VARIANT_GENOME_BOUNDS,
    LIVE_VARIANT_GENOME_LABELS,
    LIVE_VARIANT_SEGMENTS,
    LlivVariantBuilder,
    LlivVariantConfig,
    MockVariantFitnessConfig,
    Population,
    SegmentCrossover,
    SegmentedScheduler,
    TournamentSelection,
    mock_variant_fitness_factory,
)


# ---------------------------------------------------------------------------
# Genome bounds / labels
# ---------------------------------------------------------------------------


def test_genome_is_19_dim() -> None:
    assert LIVE_VARIANT_GENOME_BOUNDS.n_dims == 19
    assert len(LIVE_VARIANT_GENOME_LABELS) == 19


def test_segments_cover_full_genome() -> None:
    last_end = LIVE_VARIANT_SEGMENTS[-1][1]
    assert last_end == 19
    # 各 segment が連続して全域カバー
    prev_end = 0
    for start, end in LIVE_VARIANT_SEGMENTS:
        assert start == prev_end
        assert end > start
        prev_end = end


# ---------------------------------------------------------------------------
# LlivVariantBuilder
# ---------------------------------------------------------------------------


def test_builder_produces_valid_config() -> None:
    rng = np.random.default_rng(0)
    genome = Genome.random(LIVE_VARIANT_GENOME_BOUNDS, rng, labels=LIVE_VARIANT_GENOME_LABELS)
    builder = LlivVariantBuilder(data_dir_root="/tmp/test")
    cfg = builder.build_config(genome, variant_id="abc")
    assert isinstance(cfg, LlivVariantConfig)
    # 10 思考因子
    assert len(cfg.thought_factor_weights) == 10
    assert "factor_structurize" in cfg.thought_factor_weights
    # 3 memory tier
    assert len(cfg.memory_thresholds) == 3
    # backend は 5 種のいずれか
    assert cfg.backend_name in ("mock", "openai", "anthropic", "mamba", "rwkv")
    # sampler / proactive
    assert "temperature" in cfg.sampler
    assert "gift_value_threshold" in cfg.proactive
    # data_dir に variant_id が反映
    assert "abc" in cfg.data_dir


def test_builder_clamps_backend_index() -> None:
    """backend_id が範囲外 (clip 経由で 4.99) でも有効 backend に解決される."""
    # bounds.upper の backend_id は 4.99 → int(4.99)=4 で rwkv に解決
    bounds = LIVE_VARIANT_GENOME_BOUNDS
    upper_values = list(bounds.upper)
    genome = Genome.from_values(upper_values, bounds=bounds)
    builder = LlivVariantBuilder()
    cfg = builder.build_config(genome)
    assert cfg.backend_name == "rwkv"


def test_builder_rejects_wrong_dim_genome() -> None:
    """19 dim 以外を渡したら ValueError."""
    bad_bounds = GenomeBounds(lower=(0.0,), upper=(1.0,))
    bad_genome = Genome.from_values([0.5], bounds=bad_bounds)
    builder = LlivVariantBuilder()
    with pytest.raises(ValueError):
        builder.build_config(bad_genome)


# ---------------------------------------------------------------------------
# SegmentCrossover
# ---------------------------------------------------------------------------


def test_segment_crossover_swaps_chromosomes() -> None:
    bounds = LIVE_VARIANT_GENOME_BOUNDS
    a = Genome.from_values([0.0] * 19, bounds=bounds, labels=LIVE_VARIANT_GENOME_LABELS)
    # b は backend (idx 13) を 4.0 に, それ以外を 0.5
    b_values = [0.5] * 19
    b_values[13] = 4.0
    b = Genome.from_values(b_values, bounds=bounds, labels=LIVE_VARIANT_GENOME_LABELS)

    crossover = SegmentCrossover(segments=LIVE_VARIANT_SEGMENTS, p=0.0)  # p=0 → 全 segment 親 B
    rng = np.random.default_rng(0)
    child = crossover(a, b, rng)
    arr = child.as_array()
    # 全部親 B 由来 (0.5 or 4.0)
    assert arr[13] == 4.0


def test_segment_crossover_p_one_picks_all_parent_a() -> None:
    bounds = LIVE_VARIANT_GENOME_BOUNDS
    a = Genome.from_values([0.0] * 19, bounds=bounds)
    b = Genome.from_values([0.5] * 19, bounds=bounds)
    crossover = SegmentCrossover(segments=LIVE_VARIANT_SEGMENTS, p=1.0)
    rng = np.random.default_rng(0)
    child = crossover(a, b, rng)
    # 全 segment が親 A 由来 → 全部 0.0
    assert np.allclose(child.as_array(), 0.0)


def test_segment_crossover_rejects_invalid_segments() -> None:
    # 重複
    with pytest.raises(ValueError):
        SegmentCrossover(segments=[(0, 5), (3, 8)])
    # 空
    with pytest.raises(ValueError):
        SegmentCrossover(segments=[])
    # 範囲外 (n_dims=19)
    crossover = SegmentCrossover(segments=[(0, 25)])
    rng = np.random.default_rng(0)
    a = Genome.from_values([0.0] * 19, bounds=LIVE_VARIANT_GENOME_BOUNDS)
    with pytest.raises(ValueError):
        crossover(a, a, rng)


# ---------------------------------------------------------------------------
# mock variant fitness
# ---------------------------------------------------------------------------


def test_mock_variant_fitness_8_axis_breakdown() -> None:
    rng = np.random.default_rng(0)
    genome = Genome.random(LIVE_VARIANT_GENOME_BOUNDS, rng, labels=LIVE_VARIANT_GENOME_LABELS)
    fitness_fn = mock_variant_fitness_factory()
    report = fitness_fn(genome)
    # 5 共通軸 + 3 派生固有軸
    for key in (
        "latency_ms", "quality", "stability", "safety", "honesty",
        "factor_coverage", "memory_efficiency", "proactive_balance",
    ):
        assert key in report.breakdown
    # 6 metadata 必須
    for key in (
        "llama_cpp_sha", "llama_cpp_release_tag", "gguf_spec_version",
        "sampler_chain_spec", "kv_cache_quantization", "model_quant",
    ):
        assert key in report.runtime_metadata
    assert 0.0 <= report.score <= 1.0


def test_mock_variant_fitness_factor_coverage_extremes() -> None:
    """全因子 0 と全因子 1 で factor_coverage が低くなる (中庸が良い)."""
    bounds = LIVE_VARIANT_GENOME_BOUNDS
    # 全 0 (lower bound)
    all_zero = Genome.from_values(list(bounds.lower), bounds=bounds)
    # 全 1 (思考因子のみ. 他は bounds 内中央付近にする)
    one_then_mid = [1.0] * 10 + [0.5, 0.5, 0.75, 2.5, 0.7, 0.75, 1.5, 0.6, 60.0]
    high_factors = Genome.from_values(one_then_mid, bounds=bounds)

    fn = mock_variant_fitness_factory()
    r_zero = fn(all_zero)
    r_high = fn(high_factors)
    # 全 0 は coverage 0 に近い (mean=0 ペナルティ)
    assert r_zero.breakdown["factor_coverage"] < 0.2
    # 全因子 1 は std=0 + mean=1 で coverage 1 に近い
    assert r_high.breakdown["factor_coverage"] > 0.8


# ---------------------------------------------------------------------------
# SegmentedScheduler
# ---------------------------------------------------------------------------


def test_segmented_scheduler_processes_all_individuals() -> None:
    bounds = LIVE_VARIANT_GENOME_BOUNDS
    pop = Population.random(bounds=bounds, size=12, seed=0, labels=LIVE_VARIANT_GENOME_LABELS)
    fn = mock_variant_fitness_factory()
    sched = SegmentedScheduler(segment_size=5, grace_sec=0.0)
    reports = sched(fn, pop.individuals)
    assert len(reports) == 12  # 5 + 5 + 2 = 12 全評価


def test_segmented_scheduler_rejects_invalid_segment_size() -> None:
    with pytest.raises(ValueError):
        SegmentedScheduler(segment_size=0)
    with pytest.raises(ValueError):
        SegmentedScheduler(grace_sec=-1.0)


# ---------------------------------------------------------------------------
# GA 3 世代回し
# ---------------------------------------------------------------------------


def test_variant_ga_runs_three_generations() -> None:
    pop = Population.random(
        bounds=LIVE_VARIANT_GENOME_BOUNDS,
        size=10,
        seed=42,
        labels=LIVE_VARIANT_GENOME_LABELS,
    )
    loop = EvolutionLoop(
        fitness_fn=mock_variant_fitness_factory(),
        selection=TournamentSelection(k=3),
        crossover=SegmentCrossover(segments=LIVE_VARIANT_SEGMENTS, p=0.5),
        mutation=ChainedMutation(
            mutations=(GaussianMutation(sigma=0.1, p=0.2),),
        ),
        elitism=ElitismSelection(top_n=2),
    )
    config = EvolutionConfig(max_generations=3, patience=10, log_progress=False)
    result = loop.run(pop, config)
    # 各個体に fitness 記録 + Genome は bounds 内
    for ind in pop.individuals:
        assert ind.fitness is not None
        arr = ind.genome.as_array()
        for v, lo, up in zip(
            arr, LIVE_VARIANT_GENOME_BOUNDS.lower, LIVE_VARIANT_GENOME_BOUNDS.upper, strict=True
        ):
            assert lo <= v <= up
    # best は ≥ 初期 (mock では大きく動かないかもだが下回らない)
    assert result.best_score >= result.stats_history[0].best_score - 1e-6
