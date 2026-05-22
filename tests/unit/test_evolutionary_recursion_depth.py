# SPDX-License-Identifier: Apache-2.0
"""RecursionDepthGene + run_recursive_inference (v0.F EV-19 skeleton) — unit tests.

ユーザー指摘 (2026-05-22 深夜) "重複 = 個体内 output→input 再帰" を遺伝子化した
v0.F EV-19 の skeleton 検証.

カバー範囲:

1. default 構築 / バリデーション (per_layer / per_factor / threshold / max)
2. serialization round-trip (tuple-of-tuple 含む)
3. Kolmogorov proxy (gzip ベース)
4. neighborhood sampling
5. total_expected_recursion
6. run_recursive_inference (identity / divergent / early-stop / max クリップ / layer dispatch)
7. RecursionTrace 構造

実 LLM inference_fn 統合は次フェーズ.
"""

from __future__ import annotations

import numpy as np
import pytest

from llive.perf.evolutionary.persona import THOUGHT_FACTORS
from llive.perf.evolutionary.recursion_depth import (
    DEFAULT_EARLY_STOP_THRESHOLD,
    DEFAULT_MAX_TOTAL_RECURSION,
    EXPECTED_THOUGHT_FACTORS,
    KNOWN_REFINE_STRATEGIES,
    NUM_LAYER_BOUNDARIES,
    RecursionDepthGene,
    RefineStrategy,
)
from llive.perf.evolutionary.recursive_inference import (
    RecursionTrace,
    run_recursive_inference,
)

# ===========================================================================
# 1. RecursionDepthGene — default + validation
# ===========================================================================


def test_default_constructs_valid_gene() -> None:
    g = RecursionDepthGene.default()
    assert g.per_layer == (1, 1, 1)
    assert len(g.per_factor) == len(THOUGHT_FACTORS) == 10
    factor_names = tuple(name for name, _ in g.per_factor)
    assert factor_names == EXPECTED_THOUGHT_FACTORS
    for _, count in g.per_factor:
        assert count == 1
    assert g.max_total_recursion == DEFAULT_MAX_TOTAL_RECURSION
    assert g.refine_strategy == RefineStrategy.SELF_CRITIQUE
    assert g.early_stop_threshold == DEFAULT_EARLY_STOP_THRESHOLD


def test_default_uses_ssot_thought_factors() -> None:
    """persona.THOUGHT_FACTORS を SSoT として参照していること."""
    g = RecursionDepthGene.default()
    factor_names = tuple(name for name, _ in g.per_factor)
    assert factor_names == THOUGHT_FACTORS


def test_rejects_per_layer_zero() -> None:
    with pytest.raises(ValueError, match="per_layer"):
        RecursionDepthGene(
            per_layer=(0, 1, 1),
            per_factor=tuple((f, 1) for f in EXPECTED_THOUGHT_FACTORS),
            max_total_recursion=50,
            refine_strategy=RefineStrategy.SELF_CRITIQUE,
            early_stop_threshold=0.01,
        )


def test_rejects_per_layer_negative() -> None:
    with pytest.raises(ValueError, match="per_layer"):
        RecursionDepthGene(
            per_layer=(1, -1, 1),
            per_factor=tuple((f, 1) for f in EXPECTED_THOUGHT_FACTORS),
            max_total_recursion=50,
            refine_strategy=RefineStrategy.SELF_CRITIQUE,
            early_stop_threshold=0.01,
        )


def test_rejects_wrong_per_layer_length() -> None:
    with pytest.raises(ValueError, match="per_layer"):
        RecursionDepthGene(
            per_layer=(1, 1),  # only 2
            per_factor=tuple((f, 1) for f in EXPECTED_THOUGHT_FACTORS),
            max_total_recursion=50,
            refine_strategy=RefineStrategy.SELF_CRITIQUE,
            early_stop_threshold=0.01,
        )


def test_rejects_negative_factor_count() -> None:
    with pytest.raises(ValueError, match="per_factor"):
        RecursionDepthGene(
            per_layer=(1, 1, 1),
            per_factor=(("factor_structurize", -1),),
            max_total_recursion=50,
            refine_strategy=RefineStrategy.SELF_CRITIQUE,
            early_stop_threshold=0.01,
        )


def test_rejects_duplicate_factor_names() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        RecursionDepthGene(
            per_layer=(1, 1, 1),
            per_factor=(("factor_structurize", 1), ("factor_structurize", 2)),
            max_total_recursion=50,
            refine_strategy=RefineStrategy.SELF_CRITIQUE,
            early_stop_threshold=0.01,
        )


def test_rejects_threshold_out_of_range() -> None:
    with pytest.raises(ValueError, match="early_stop_threshold"):
        RecursionDepthGene(
            per_layer=(1, 1, 1),
            per_factor=tuple((f, 1) for f in EXPECTED_THOUGHT_FACTORS),
            max_total_recursion=50,
            refine_strategy=RefineStrategy.SELF_CRITIQUE,
            early_stop_threshold=1.5,
        )


def test_rejects_threshold_negative() -> None:
    with pytest.raises(ValueError, match="early_stop_threshold"):
        RecursionDepthGene(
            per_layer=(1, 1, 1),
            per_factor=tuple((f, 1) for f in EXPECTED_THOUGHT_FACTORS),
            max_total_recursion=50,
            refine_strategy=RefineStrategy.SELF_CRITIQUE,
            early_stop_threshold=-0.01,
        )


def test_rejects_max_total_zero() -> None:
    with pytest.raises(ValueError, match="max_total_recursion"):
        RecursionDepthGene(
            per_layer=(1, 1, 1),
            per_factor=tuple((f, 1) for f in EXPECTED_THOUGHT_FACTORS),
            max_total_recursion=0,
            refine_strategy=RefineStrategy.SELF_CRITIQUE,
            early_stop_threshold=0.01,
        )


def test_rejects_non_enum_strategy() -> None:
    with pytest.raises(ValueError, match="refine_strategy"):
        RecursionDepthGene(
            per_layer=(1, 1, 1),
            per_factor=tuple((f, 1) for f in EXPECTED_THOUGHT_FACTORS),
            max_total_recursion=50,
            refine_strategy="self_critique",  # type: ignore[arg-type]
            early_stop_threshold=0.01,
        )


# ===========================================================================
# 2. Serialization round-trip
# ===========================================================================


def test_serialization_round_trip_default() -> None:
    g = RecursionDepthGene.default()
    restored = RecursionDepthGene.from_dict(g.to_dict())
    assert restored == g


def test_serialization_round_trip_custom() -> None:
    g = RecursionDepthGene(
        per_layer=(3, 5, 2),
        per_factor=(
            ("factor_structurize", 2),
            ("factor_recompose", 4),
            ("factor_closed_loop", 1),
        ),
        max_total_recursion=30,
        refine_strategy=RefineStrategy.PERSPECTIVE_SHIFT,
        early_stop_threshold=0.05,
    )
    restored = RecursionDepthGene.from_dict(g.to_dict())
    assert restored == g
    assert restored.refine_strategy == RefineStrategy.PERSPECTIVE_SHIFT
    # tuple-of-tuple が正しく往復していること
    assert isinstance(restored.per_factor, tuple)
    assert all(isinstance(p, tuple) and len(p) == 2 for p in restored.per_factor)


def test_to_json_bytes_deterministic() -> None:
    g1 = RecursionDepthGene.default()
    g2 = RecursionDepthGene.default()
    assert g1.to_json_bytes() == g2.to_json_bytes()


# ===========================================================================
# 3. Kolmogorov complexity proxy
# ===========================================================================


def test_kolmogorov_proxy_positive() -> None:
    g = RecursionDepthGene.default()
    k = g.kolmogorov_proxy()
    assert k > 0
    assert k > 20  # gzip overhead 込みで最低 20 byte 以上


def test_kolmogorov_proxy_grows_with_factors() -> None:
    """per_factor を多く持つ gene は K proxy が大きい (実用近似)."""
    minimal = RecursionDepthGene(
        per_layer=(1, 1, 1),
        per_factor=(("factor_structurize", 1),),
        max_total_recursion=10,
        refine_strategy=RefineStrategy.SELF_CRITIQUE,
        early_stop_threshold=0.01,
    )
    full = RecursionDepthGene.default()
    assert full.kolmogorov_proxy() > minimal.kolmogorov_proxy()


# ===========================================================================
# 4. Neighborhood sampling
# ===========================================================================


def test_sample_neighborhood_returns_valid_gene() -> None:
    rng = np.random.default_rng(0)
    base = RecursionDepthGene.default()
    neighbor = base.sample_neighborhood(rng, step_size=0.1)
    assert isinstance(neighbor, RecursionDepthGene)
    # post_init validation を通っているので各 layer >= 1
    for depth in neighbor.per_layer:
        assert depth >= 1
    for _, count in neighbor.per_factor:
        assert count >= 0
    assert neighbor.max_total_recursion >= 1
    assert 0.0 <= neighbor.early_stop_threshold <= 1.0


def test_sample_neighborhood_is_stochastic() -> None:
    """異なる rng seed で異なる結果が返る (高 step で discrete switch 含む)."""
    base = RecursionDepthGene.default()
    neighbors = [
        base.sample_neighborhood(np.random.default_rng(s), step_size=0.8)
        for s in range(20)
    ]
    # 20 個 sample してすべて同一にはならない
    assert len({n.to_json_bytes() for n in neighbors}) > 1


def test_sample_neighborhood_zero_step_keeps_threshold() -> None:
    """step_size=0 なら threshold の Gaussian perturbation は σ=0 で不変."""
    rng = np.random.default_rng(0)
    base = RecursionDepthGene.default()
    neighbor = base.sample_neighborhood(rng, step_size=0.0)
    assert neighbor.early_stop_threshold == base.early_stop_threshold
    # step_size=0 なら refine_strategy も不変
    assert neighbor.refine_strategy == base.refine_strategy


def test_sample_neighborhood_can_switch_strategy_at_high_step() -> None:
    """step_size 大きいと refine_strategy が変わりうる."""
    rng = np.random.default_rng(42)
    base = RecursionDepthGene.default()
    strategies = {
        base.sample_neighborhood(np.random.default_rng(s), step_size=1.0).refine_strategy
        for s in range(50)
    }
    # 50 sample中で 2 種類以上の strategy が現れる (確率的)
    assert len(strategies) >= 2


# ===========================================================================
# 5. total_expected_recursion
# ===========================================================================


def test_total_expected_recursion_default() -> None:
    g = RecursionDepthGene.default()
    # per_layer (1+1+1) + per_factor (1*10) = 13
    assert g.total_expected_recursion() == 3 + 10


def test_total_expected_recursion_custom() -> None:
    g = RecursionDepthGene(
        per_layer=(2, 3, 5),
        per_factor=(("factor_structurize", 4), ("factor_recompose", 6)),
        max_total_recursion=50,
        refine_strategy=RefineStrategy.SELF_CRITIQUE,
        early_stop_threshold=0.01,
    )
    # (2+3+5) + (4+6) = 20
    assert g.total_expected_recursion() == 20


# ===========================================================================
# 6. run_recursive_inference — identity (early-stop)
# ===========================================================================


def test_run_recursive_inference_identity_early_stops() -> None:
    """identity function なら delta=0 で 1 iter 後に early-stop."""
    g = RecursionDepthGene(
        per_layer=(10, 1, 1),  # layer 0 は 10 回まで回る設定
        per_factor=tuple((f, 1) for f in EXPECTED_THOUGHT_FACTORS),
        max_total_recursion=50,
        refine_strategy=RefineStrategy.SELF_CRITIQUE,
        early_stop_threshold=0.01,
    )
    out, traces = run_recursive_inference(
        initial_input="hello",
        inference_fn=lambda x: x,
        gene=g,
        layer=0,
    )
    assert out == "hello"
    # delta=0 < 0.01 → 1 iter で停止
    assert len(traces) == 1
    assert traces[0].delta == 0.0
    assert traces[0].iteration == 0


# ===========================================================================
# 7. run_recursive_inference — divergent (runs to per_layer limit)
# ===========================================================================


def test_run_recursive_inference_divergent_runs_to_layer_limit() -> None:
    """毎回大きく変わる関数なら per_layer[layer] 回まで回る."""
    g = RecursionDepthGene(
        per_layer=(5, 1, 1),
        per_factor=tuple((f, 1) for f in EXPECTED_THOUGHT_FACTORS),
        max_total_recursion=50,
        refine_strategy=RefineStrategy.SELF_CRITIQUE,
        early_stop_threshold=0.01,
    )
    # 毎回 random 文字列を append → hash 大変化
    counter = {"n": 0}

    def divergent(x: str) -> str:
        counter["n"] += 1
        # 毎回 prefix を付け替えて hash を大幅変化させる
        return f"step{counter['n']}_{x}"

    out, traces = run_recursive_inference(
        initial_input="seed",
        inference_fn=divergent,
        gene=g,
        layer=0,
    )
    # 5 回回ったはず
    assert len(traces) == 5
    assert out == "step5_step4_step3_step2_step1_seed"
    # 全 delta が threshold より大きい
    for t in traces:
        assert t.delta >= g.early_stop_threshold


# ===========================================================================
# 8. run_recursive_inference — max_total_recursion clip
# ===========================================================================


def test_run_recursive_inference_max_total_clips_per_layer() -> None:
    """per_layer[layer] > max_total_recursion なら max_total で停止."""
    g = RecursionDepthGene(
        per_layer=(100, 1, 1),    # layer 0 で 100 回希望
        per_factor=tuple((f, 0) for f in EXPECTED_THOUGHT_FACTORS),
        max_total_recursion=7,    # しかし上限 7
        refine_strategy=RefineStrategy.SELF_CRITIQUE,
        early_stop_threshold=0.0001,  # ほぼ early-stop しない
    )
    counter = {"n": 0}

    def divergent(x: str) -> str:
        counter["n"] += 1
        return f"v{counter['n']}_{x}"

    _, traces = run_recursive_inference(
        initial_input="seed",
        inference_fn=divergent,
        gene=g,
        layer=0,
    )
    # min(100, 7) = 7 回で停止
    assert len(traces) == 7


# ===========================================================================
# 9. run_recursive_inference — early_stop_threshold が効く
# ===========================================================================


def test_run_recursive_inference_early_stop_threshold_works() -> None:
    """threshold が大きければ早く停止, 小さければ長く回る."""
    counter_lo = {"n": 0}
    counter_hi = {"n": 0}

    def divergent_lo(x: str) -> str:
        counter_lo["n"] += 1
        return f"v{counter_lo['n']}_{x}"

    def divergent_hi(x: str) -> str:
        counter_hi["n"] += 1
        return f"v{counter_hi['n']}_{x}"

    g_strict = RecursionDepthGene(
        per_layer=(20, 1, 1),
        per_factor=tuple((f, 0) for f in EXPECTED_THOUGHT_FACTORS),
        max_total_recursion=50,
        refine_strategy=RefineStrategy.SELF_CRITIQUE,
        early_stop_threshold=0.99,  # ほぼ即 early-stop (delta 0.5 程度 < 0.99)
    )
    g_loose = RecursionDepthGene(
        per_layer=(20, 1, 1),
        per_factor=tuple((f, 0) for f in EXPECTED_THOUGHT_FACTORS),
        max_total_recursion=50,
        refine_strategy=RefineStrategy.SELF_CRITIQUE,
        early_stop_threshold=0.0001,  # 早期停止しない
    )

    _, traces_strict = run_recursive_inference(
        initial_input="seed",
        inference_fn=divergent_lo,
        gene=g_strict,
        layer=0,
    )
    _, traces_loose = run_recursive_inference(
        initial_input="seed",
        inference_fn=divergent_hi,
        gene=g_loose,
        layer=0,
    )

    # strict threshold = 0.99 なら hash の Hamming distance は典型的に
    # 0.5 程度なので即停止 → 1 iter
    assert len(traces_strict) == 1
    # loose threshold = 0.0001 なら止まらず per_layer[0] = 20 まで回る
    assert len(traces_loose) == 20


# ===========================================================================
# 10. run_recursive_inference — layer dispatch
# ===========================================================================


def test_run_recursive_inference_layer_dispatch() -> None:
    """layer 引数で per_layer[layer] が使われる."""
    g = RecursionDepthGene(
        per_layer=(2, 4, 6),
        per_factor=tuple((f, 0) for f in EXPECTED_THOUGHT_FACTORS),
        max_total_recursion=50,
        refine_strategy=RefineStrategy.SELF_CRITIQUE,
        early_stop_threshold=0.0001,
    )

    def make_divergent() -> "object":
        counter = {"n": 0}

        def fn(x: str) -> str:
            counter["n"] += 1
            return f"v{counter['n']}_{x}"

        return fn

    _, traces0 = run_recursive_inference(
        initial_input="s",
        inference_fn=make_divergent(),
        gene=g,
        layer=0,
    )
    _, traces1 = run_recursive_inference(
        initial_input="s",
        inference_fn=make_divergent(),
        gene=g,
        layer=1,
    )
    _, traces2 = run_recursive_inference(
        initial_input="s",
        inference_fn=make_divergent(),
        gene=g,
        layer=2,
    )
    assert len(traces0) == 2
    assert len(traces1) == 4
    assert len(traces2) == 6


def test_run_recursive_inference_rejects_invalid_layer() -> None:
    g = RecursionDepthGene.default()
    with pytest.raises(ValueError, match="layer"):
        run_recursive_inference(
            initial_input="x",
            inference_fn=lambda v: v,
            gene=g,
            layer=NUM_LAYER_BOUNDARIES,  # out of range
        )
    with pytest.raises(ValueError, match="layer"):
        run_recursive_inference(
            initial_input="x",
            inference_fn=lambda v: v,
            gene=g,
            layer=-1,
        )


# ===========================================================================
# 11. RecursionTrace structure
# ===========================================================================


def test_recursion_trace_structure() -> None:
    g = RecursionDepthGene(
        per_layer=(3, 1, 1),
        per_factor=tuple((f, 0) for f in EXPECTED_THOUGHT_FACTORS),
        max_total_recursion=50,
        refine_strategy=RefineStrategy.EVIDENCE_SEEK,
        early_stop_threshold=0.0001,
    )

    counter = {"n": 0}

    def divergent(x: str) -> str:
        counter["n"] += 1
        return f"v{counter['n']}_{x}"

    _, traces = run_recursive_inference(
        initial_input="seed",
        inference_fn=divergent,
        gene=g,
        layer=0,
    )
    assert len(traces) == 3
    for idx, t in enumerate(traces):
        assert isinstance(t, RecursionTrace)
        assert t.iteration == idx
        assert isinstance(t.input_hash, str) and len(t.input_hash) == 64
        assert isinstance(t.output_hash, str) and len(t.output_hash) == 64
        assert 0.0 <= t.delta <= 1.0
        assert t.refine_applied == RefineStrategy.EVIDENCE_SEEK
        assert t.elapsed_ms >= 0.0
    # 連続 trace の chain (前回 output_hash == 今回 input_hash)
    for prev, curr in zip(traces[:-1], traces[1:], strict=True):
        assert prev.output_hash == curr.input_hash


# ===========================================================================
# 12. KNOWN_REFINE_STRATEGIES export sanity
# ===========================================================================


def test_known_refine_strategies_complete() -> None:
    assert len(KNOWN_REFINE_STRATEGIES) == 6
    assert "self_critique" in KNOWN_REFINE_STRATEGIES
    assert "perspective_shift" in KNOWN_REFINE_STRATEGIES
    assert "constraint_tighten" in KNOWN_REFINE_STRATEGIES
    assert "evidence_seek" in KNOWN_REFINE_STRATEGIES
    assert "abstraction_lift" in KNOWN_REFINE_STRATEGIES
    assert "detail_drill" in KNOWN_REFINE_STRATEGIES
