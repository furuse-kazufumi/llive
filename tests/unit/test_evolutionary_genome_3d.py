# SPDX-License-Identifier: Apache-2.0
"""Genome3D (v0.F EV-13 + v0.I EV-21 join) — unit tests.

3 階建てゲノム結合 dataclass の skeleton カバー範囲:

1. default 生成 + 3 chromosome 全件 OK
2. serialization round-trip (nested dict)
3. kolmogorov_proxy が 3 chromosome の合計と一致
4. sample_neighborhood が valid Genome3D を返す
5. intra_layer_crossover: 各層が独立に 50/50 (統計的検証)
6. cross_layer_crossover: c_impl=a, c_prompt=b 固定 / c_meta 確率的
7. frozen / hashable 性
"""

from __future__ import annotations

import numpy as np
import pytest

from llive.perf.evolutionary.genome_3d import (
    Genome3D,
    cross_layer_crossover,
    intra_layer_crossover,
)
from llive.perf.evolutionary.impl_chromosome import ImplChromosome
from llive.perf.evolutionary.meta_chromosome import MetaChromosome
from llive.perf.evolutionary.prompt_chromosome import PromptChromosome

# ===========================================================================
# A. default factory
# ===========================================================================


def test_default_constructs_valid_3d() -> None:
    g = Genome3D.default()
    assert isinstance(g.c_impl, ImplChromosome)
    assert isinstance(g.c_prompt, PromptChromosome)
    assert isinstance(g.c_meta, MetaChromosome)


def test_default_matches_chromosome_defaults() -> None:
    g = Genome3D.default()
    assert g.c_impl == ImplChromosome.default()
    assert g.c_prompt == PromptChromosome.default()
    assert g.c_meta == MetaChromosome.default()


# ===========================================================================
# B. serialization round-trip
# ===========================================================================


def test_to_dict_is_nested_dict() -> None:
    g = Genome3D.default()
    d = g.to_dict()
    assert set(d.keys()) == {"c_impl", "c_prompt", "c_meta"}
    assert isinstance(d["c_impl"], dict)
    assert isinstance(d["c_prompt"], dict)
    assert isinstance(d["c_meta"], dict)


def test_from_dict_round_trip() -> None:
    g0 = Genome3D.default()
    g1 = Genome3D.from_dict(g0.to_dict())
    assert g0 == g1


def test_round_trip_after_neighborhood_sample() -> None:
    rng = np.random.default_rng(42)
    g0 = Genome3D.default().sample_neighborhood(rng, step_size=0.3)
    g1 = Genome3D.from_dict(g0.to_dict())
    assert g0 == g1


# ===========================================================================
# C. Kolmogorov proxy = 3 chromosome 合計
# ===========================================================================


def test_kolmogorov_proxy_equals_sum_of_chromosomes() -> None:
    g = Genome3D.default()
    expected = (
        g.c_impl.kolmogorov_proxy()
        + g.c_prompt.kolmogorov_proxy()
        + g.c_meta.kolmogorov_proxy()
    )
    assert g.kolmogorov_proxy() == expected


def test_kolmogorov_proxy_is_positive() -> None:
    g = Genome3D.default()
    assert g.kolmogorov_proxy() > 0


# ===========================================================================
# D. sample_neighborhood
# ===========================================================================


def test_sample_neighborhood_returns_valid_genome3d() -> None:
    rng = np.random.default_rng(0)
    g0 = Genome3D.default()
    g1 = g0.sample_neighborhood(rng, step_size=0.2)
    # validation は __post_init__ で実行されているはず
    assert isinstance(g1, Genome3D)
    assert isinstance(g1.c_impl, ImplChromosome)
    assert isinstance(g1.c_prompt, PromptChromosome)
    assert isinstance(g1.c_meta, MetaChromosome)


def test_sample_neighborhood_zero_step_impl_prompt_identity() -> None:
    """step_size=0 では impl / prompt 層は完全に identity になる.

    meta 層は仕様上 discrete field (crossover_strategy / algorithm_id) が
    step_size とは独立に 1/3 確率で switch するため identity を保証しない —
    これは MetaChromosome 側の意図的設計 (Promptbreeder Fernando 2023 流の
    meta-layer 自己揺動).
    """
    rng = np.random.default_rng(0)
    g0 = Genome3D.default()
    g1 = g0.sample_neighborhood(rng, step_size=0.0)
    assert g1.c_impl == g0.c_impl
    assert g1.c_prompt == g0.c_prompt


def test_sample_neighborhood_does_diverge_with_large_step() -> None:
    rng = np.random.default_rng(123)
    g0 = Genome3D.default()
    # 多数試行のうち少なくとも 1 回は変化していることを確認
    any_changed = False
    for _ in range(20):
        g1 = g0.sample_neighborhood(rng, step_size=0.8)
        if g1 != g0:
            any_changed = True
            break
    assert any_changed, "step_size=0.8 で 20 回試行しても全く変化しないのは異常"


# ===========================================================================
# E. intra_layer_crossover — 各層独立に 50/50
# ===========================================================================


def _make_distinct_parents() -> tuple[Genome3D, Genome3D]:
    """各層で明確に異なる 2 個体を作る (識別容易な値で)."""
    parent_a = Genome3D(
        c_impl=ImplChromosome(
            impl_language="python",
            algorithm_family="genetic",
            parallel_strategy="single",
            agi_usage_ratio=0.1,
            orchestration_mode="sequential",
            memory_backend="dict",
            selector_class="UCB1",
            judge_model="self",
        ),
        c_prompt=PromptChromosome(
            persona_set=("oka",),
            skill_set=("structurize",),
            rule_set=("fail_closed",),
            prompt_template_id="base",
            language_style="terse",
            historical_quote_density=0.2,
        ),
        c_meta=MetaChromosome(
            mutation_rate_per_layer=(0.01, 0.02, 0.03),
            crossover_strategy="intra",
            selection_pressure=0.3,
            novelty_weight=0.1,
            cluster_quota=2,
            meta_mutation_decay=0.4,
            algorithm_id="tournament_gauss",
        ),
    )
    parent_b = Genome3D(
        c_impl=ImplChromosome(
            impl_language="rust",
            algorithm_family="mcts",
            parallel_strategy="process",
            agi_usage_ratio=0.9,
            orchestration_mode="actor_model",
            memory_backend="lmdb",
            selector_class="Thompson",
            judge_model="external",
        ),
        c_prompt=PromptChromosome(
            persona_set=("polya", "triz"),
            skill_set=("recompose", "loop"),
            rule_set=("honest_disclosure",),
            prompt_template_id="debate",
            language_style="academic",
            historical_quote_density=0.8,
        ),
        c_meta=MetaChromosome(
            mutation_rate_per_layer=(0.5, 0.6, 0.7),
            crossover_strategy="cross",
            selection_pressure=0.9,
            novelty_weight=0.5,
            cluster_quota=10,
            meta_mutation_decay=0.1,
            algorithm_id="nsga2_novelty",
        ),
    )
    return parent_a, parent_b


def test_intra_layer_crossover_child_layers_from_parents() -> None:
    rng = np.random.default_rng(0)
    pa, pb = _make_distinct_parents()
    child = intra_layer_crossover(pa, pb, rng)
    # 各層は親 A / 親 B のいずれかと一致する
    assert child.c_impl in (pa.c_impl, pb.c_impl)
    assert child.c_prompt in (pa.c_prompt, pb.c_prompt)
    assert child.c_meta in (pa.c_meta, pb.c_meta)


def test_intra_layer_crossover_each_layer_independent_50_50() -> None:
    """seed 固定 + 多数試行で各層が独立に ~50/50 になることを統計的に確認."""
    rng = np.random.default_rng(20260522)
    pa, pb = _make_distinct_parents()
    n_trials = 2000
    impl_from_a = 0
    prompt_from_a = 0
    meta_from_a = 0
    for _ in range(n_trials):
        child = intra_layer_crossover(pa, pb, rng)
        if child.c_impl == pa.c_impl:
            impl_from_a += 1
        if child.c_prompt == pa.c_prompt:
            prompt_from_a += 1
        if child.c_meta == pa.c_meta:
            meta_from_a += 1
    # 50% ± 5% に収まれば独立 50/50 と判定 (n=2000 で十分なゆるめ)
    for label, count in [
        ("c_impl", impl_from_a),
        ("c_prompt", prompt_from_a),
        ("c_meta", meta_from_a),
    ]:
        ratio = count / n_trials
        assert 0.45 <= ratio <= 0.55, f"{label}: {ratio:.3f} not in [0.45, 0.55]"


def test_intra_layer_crossover_all_8_combinations_appear() -> None:
    """seed 固定 + 多数試行で 2^3 = 8 通りの組合せが少なくとも 1 回は出る."""
    rng = np.random.default_rng(7)
    pa, pb = _make_distinct_parents()
    seen: set[tuple[bool, bool, bool]] = set()
    for _ in range(500):
        child = intra_layer_crossover(pa, pb, rng)
        key = (
            child.c_impl == pa.c_impl,
            child.c_prompt == pa.c_prompt,
            child.c_meta == pa.c_meta,
        )
        seen.add(key)
        if len(seen) == 8:
            break
    assert len(seen) == 8, f"8 通り出るはずが {len(seen)} 通りしか出ない: {seen}"


# ===========================================================================
# F. cross_layer_crossover — impl=A 固定 / prompt=B 固定 / meta 50/50
# ===========================================================================


def test_cross_layer_crossover_impl_always_from_a() -> None:
    rng = np.random.default_rng(0)
    pa, pb = _make_distinct_parents()
    for _ in range(100):
        child = cross_layer_crossover(pa, pb, rng)
        assert child.c_impl == pa.c_impl


def test_cross_layer_crossover_prompt_always_from_b() -> None:
    rng = np.random.default_rng(0)
    pa, pb = _make_distinct_parents()
    for _ in range(100):
        child = cross_layer_crossover(pa, pb, rng)
        assert child.c_prompt == pb.c_prompt


def test_cross_layer_crossover_meta_is_50_50() -> None:
    """meta 層は片親優位 50/50 (統計的検証)."""
    rng = np.random.default_rng(99)
    pa, pb = _make_distinct_parents()
    n_trials = 2000
    meta_from_a = 0
    for _ in range(n_trials):
        child = cross_layer_crossover(pa, pb, rng)
        # impl / prompt は固定済 (上のテストで保証)
        assert child.c_impl == pa.c_impl
        assert child.c_prompt == pb.c_prompt
        if child.c_meta == pa.c_meta:
            meta_from_a += 1
    ratio = meta_from_a / n_trials
    assert 0.45 <= ratio <= 0.55, f"meta from_a ratio {ratio:.3f} not 50/50"


# ===========================================================================
# G. frozen / hashable
# ===========================================================================


def test_genome3d_is_frozen() -> None:
    """frozen dataclass — 属性再代入は FrozenInstanceError を投げる."""
    from dataclasses import FrozenInstanceError

    g = Genome3D.default()
    with pytest.raises(FrozenInstanceError):
        g.c_impl = ImplChromosome.default()  # type: ignore[misc]


def test_genome3d_is_hashable() -> None:
    g0 = Genome3D.default()
    g1 = Genome3D.default()
    s = {g0, g1}
    # 同じ default 値同士は単一 hash
    assert len(s) == 1


def test_genome3d_equality() -> None:
    g0 = Genome3D.default()
    g1 = Genome3D.default()
    assert g0 == g1
