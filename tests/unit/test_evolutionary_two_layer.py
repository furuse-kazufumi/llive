# SPDX-License-Identifier: Apache-2.0
"""ImplChromosome + PromptChromosome (v0.F EV-13 柱 A skeleton) — unit tests.

ユーザー指示 (2026-05-22) v0.F 2 階建てゲノム skeleton:

> ゲノムに関しては、コーディングレベル (実装方法やアルゴリズムや並列実行や
> AGI やオーケストラや実装言語の違いも含む) とプロンプトレベルでの偉人の
> 思想を取り込んだスキルやルールなども含めた構造になっていて、交配や突然
> 変異が起こりやすい感じになっているといいでしょうね.

カバー範囲:

1. default 生成 (両 chromosome)
2. validation (invalid enum / subset 違反)
3. serialization round-trip (to_dict / from_dict)
4. Kolmogorov complexity proxy (gzip ベース)
5. neighborhood sampling (probabilistic switch)
6. persona_set / skill_set / rule_set の subset 検証 (重複 / 未知メンバ拒否)
"""

from __future__ import annotations

import numpy as np
import pytest

from llive.perf.evolutionary.impl_chromosome import (
    KNOWN_IMPL_ALGORITHM_FAMILIES,
    KNOWN_IMPL_JUDGE_MODELS,
    KNOWN_IMPL_LANGUAGES,
    KNOWN_IMPL_MEMORY_BACKENDS,
    KNOWN_IMPL_ORCHESTRATION_MODES,
    KNOWN_IMPL_PARALLEL_STRATEGIES,
    KNOWN_IMPL_SELECTOR_CLASSES,
    ImplChromosome,
)
from llive.perf.evolutionary.prompt_chromosome import (
    KNOWN_PROMPT_LANGUAGE_STYLES,
    KNOWN_PROMPT_PERSONAS,
    KNOWN_PROMPT_RULES,
    KNOWN_PROMPT_SKILLS,
    KNOWN_PROMPT_TEMPLATES,
    PromptChromosome,
)

# ===========================================================================
# A. ImplChromosome — defaults & validation
# ===========================================================================


def test_impl_default_constructs_valid() -> None:
    c = ImplChromosome.default()
    assert c.impl_language in KNOWN_IMPL_LANGUAGES
    assert c.algorithm_family in KNOWN_IMPL_ALGORITHM_FAMILIES
    assert c.parallel_strategy in KNOWN_IMPL_PARALLEL_STRATEGIES
    assert 0.0 <= c.agi_usage_ratio <= 1.0
    assert c.orchestration_mode in KNOWN_IMPL_ORCHESTRATION_MODES
    assert c.memory_backend in KNOWN_IMPL_MEMORY_BACKENDS
    assert c.selector_class in KNOWN_IMPL_SELECTOR_CLASSES
    assert c.judge_model in KNOWN_IMPL_JUDGE_MODELS


def test_impl_rejects_unknown_language() -> None:
    with pytest.raises(ValueError, match="impl_language"):
        ImplChromosome(
            impl_language="brainfuck",
            algorithm_family="genetic",
            parallel_strategy="single",
            agi_usage_ratio=0.0,
            orchestration_mode="sequential",
            memory_backend="dict",
            selector_class="UCB1",
            judge_model="self",
        )


def test_impl_rejects_unknown_algorithm_family() -> None:
    with pytest.raises(ValueError, match="algorithm_family"):
        ImplChromosome(
            impl_language="python",
            algorithm_family="quantum_anneal",
            parallel_strategy="single",
            agi_usage_ratio=0.0,
            orchestration_mode="sequential",
            memory_backend="dict",
            selector_class="UCB1",
            judge_model="self",
        )


def test_impl_rejects_unknown_parallel_strategy() -> None:
    with pytest.raises(ValueError, match="parallel_strategy"):
        ImplChromosome(
            impl_language="python",
            algorithm_family="genetic",
            parallel_strategy="warp_drive",
            agi_usage_ratio=0.0,
            orchestration_mode="sequential",
            memory_backend="dict",
            selector_class="UCB1",
            judge_model="self",
        )


def test_impl_rejects_invalid_agi_usage_ratio() -> None:
    with pytest.raises(ValueError, match="agi_usage_ratio"):
        ImplChromosome(
            impl_language="python",
            algorithm_family="genetic",
            parallel_strategy="single",
            agi_usage_ratio=1.5,  # > 1.0
            orchestration_mode="sequential",
            memory_backend="dict",
            selector_class="UCB1",
            judge_model="self",
        )


def test_impl_rejects_unknown_orchestration_mode() -> None:
    with pytest.raises(ValueError, match="orchestration_mode"):
        ImplChromosome(
            impl_language="python",
            algorithm_family="genetic",
            parallel_strategy="single",
            agi_usage_ratio=0.0,
            orchestration_mode="orchestral_maneuvers",
            memory_backend="dict",
            selector_class="UCB1",
            judge_model="self",
        )


def test_impl_rejects_unknown_memory_backend() -> None:
    with pytest.raises(ValueError, match="memory_backend"):
        ImplChromosome(
            impl_language="python",
            algorithm_family="genetic",
            parallel_strategy="single",
            agi_usage_ratio=0.0,
            orchestration_mode="sequential",
            memory_backend="quantum_ram",
            selector_class="UCB1",
            judge_model="self",
        )


def test_impl_rejects_unknown_selector_class() -> None:
    with pytest.raises(ValueError, match="selector_class"):
        ImplChromosome(
            impl_language="python",
            algorithm_family="genetic",
            parallel_strategy="single",
            agi_usage_ratio=0.0,
            orchestration_mode="sequential",
            memory_backend="dict",
            selector_class="AlphaZero",
            judge_model="self",
        )


def test_impl_rejects_unknown_judge_model() -> None:
    with pytest.raises(ValueError, match="judge_model"):
        ImplChromosome(
            impl_language="python",
            algorithm_family="genetic",
            parallel_strategy="single",
            agi_usage_ratio=0.0,
            orchestration_mode="sequential",
            memory_backend="dict",
            selector_class="UCB1",
            judge_model="oracle",
        )


# ===========================================================================
# B. ImplChromosome — serialization & K proxy
# ===========================================================================


def test_impl_serialization_round_trip() -> None:
    c = ImplChromosome.default()
    restored = ImplChromosome.from_dict(c.to_dict())
    assert restored == c


def test_impl_to_json_bytes_is_deterministic() -> None:
    c1 = ImplChromosome.default()
    c2 = ImplChromosome.default()
    assert c1.to_json_bytes() == c2.to_json_bytes()


def test_impl_kolmogorov_proxy_positive() -> None:
    c = ImplChromosome.default()
    k = c.kolmogorov_proxy()
    assert k > 0
    # gzip header overhead だけでも 20+ byte 出る
    assert k > 20


# ===========================================================================
# C. ImplChromosome — neighborhood sampling
# ===========================================================================


def test_impl_sample_neighborhood_returns_valid() -> None:
    rng = np.random.default_rng(0)
    base = ImplChromosome.default()
    neighbor = base.sample_neighborhood(rng, step_size=0.3)
    assert isinstance(neighbor, ImplChromosome)
    # validation 通過していれば全 field が known set 内
    assert neighbor.impl_language in KNOWN_IMPL_LANGUAGES
    assert neighbor.algorithm_family in KNOWN_IMPL_ALGORITHM_FAMILIES
    assert 0.0 <= neighbor.agi_usage_ratio <= 1.0


def test_impl_sample_neighborhood_zero_step_is_identity_on_discrete() -> None:
    """step_size=0.0 で discrete field は不変 (continuous も σ=0 で不変)."""
    rng = np.random.default_rng(0)
    base = ImplChromosome.default()
    neighbor = base.sample_neighborhood(rng, step_size=0.0)
    assert neighbor.impl_language == base.impl_language
    assert neighbor.algorithm_family == base.algorithm_family
    assert neighbor.parallel_strategy == base.parallel_strategy
    assert neighbor.orchestration_mode == base.orchestration_mode
    assert neighbor.memory_backend == base.memory_backend
    assert neighbor.selector_class == base.selector_class
    assert neighbor.judge_model == base.judge_model
    # Gaussian σ=0 なので連続も完全に同じ
    assert neighbor.agi_usage_ratio == base.agi_usage_ratio


def test_impl_sample_neighborhood_is_stochastic() -> None:
    base = ImplChromosome.default()
    neighbors = {
        base.sample_neighborhood(np.random.default_rng(s), step_size=0.5)
        for s in range(20)
    }
    # 20 個サンプリングして全て同一にはならない
    assert len(neighbors) > 1


# ===========================================================================
# D. PromptChromosome — defaults & validation
# ===========================================================================


def test_prompt_default_constructs_valid() -> None:
    c = PromptChromosome.default()
    # subset 検証
    assert set(c.persona_set).issubset(set(KNOWN_PROMPT_PERSONAS))
    assert set(c.skill_set).issubset(set(KNOWN_PROMPT_SKILLS))
    assert set(c.rule_set).issubset(set(KNOWN_PROMPT_RULES))
    assert c.prompt_template_id in KNOWN_PROMPT_TEMPLATES
    assert c.language_style in KNOWN_PROMPT_LANGUAGE_STYLES
    assert 0.0 <= c.historical_quote_density <= 1.0


def test_prompt_rejects_unknown_persona() -> None:
    with pytest.raises(ValueError, match="persona_set"):
        PromptChromosome(
            persona_set=("polya", "darth_vader"),  # darth_vader unknown
            skill_set=("structurize",),
            rule_set=("fail_closed",),
            prompt_template_id="base",
            language_style="terse",
            historical_quote_density=0.1,
        )


def test_prompt_rejects_unknown_skill() -> None:
    with pytest.raises(ValueError, match="skill_set"):
        PromptChromosome(
            persona_set=("polya",),
            skill_set=("structurize", "warp_factor_nine"),
            rule_set=("fail_closed",),
            prompt_template_id="base",
            language_style="terse",
            historical_quote_density=0.1,
        )


def test_prompt_rejects_unknown_rule() -> None:
    with pytest.raises(ValueError, match="rule_set"):
        PromptChromosome(
            persona_set=("polya",),
            skill_set=("structurize",),
            rule_set=("fail_closed", "anarchy"),
            prompt_template_id="base",
            language_style="terse",
            historical_quote_density=0.1,
        )


def test_prompt_rejects_duplicate_persona() -> None:
    with pytest.raises(ValueError, match="duplicate persona_set"):
        PromptChromosome(
            persona_set=("polya", "polya"),
            skill_set=("structurize",),
            rule_set=("fail_closed",),
            prompt_template_id="base",
            language_style="terse",
            historical_quote_density=0.1,
        )


def test_prompt_rejects_unknown_template() -> None:
    with pytest.raises(ValueError, match="prompt_template_id"):
        PromptChromosome(
            persona_set=("polya",),
            skill_set=("structurize",),
            rule_set=("fail_closed",),
            prompt_template_id="hieroglyphic",
            language_style="terse",
            historical_quote_density=0.1,
        )


def test_prompt_rejects_unknown_language_style() -> None:
    with pytest.raises(ValueError, match="language_style"):
        PromptChromosome(
            persona_set=("polya",),
            skill_set=("structurize",),
            rule_set=("fail_closed",),
            prompt_template_id="base",
            language_style="emoji_only",
            historical_quote_density=0.1,
        )


def test_prompt_rejects_invalid_quote_density() -> None:
    with pytest.raises(ValueError, match="historical_quote_density"):
        PromptChromosome(
            persona_set=("polya",),
            skill_set=("structurize",),
            rule_set=("fail_closed",),
            prompt_template_id="base",
            language_style="terse",
            historical_quote_density=2.0,
        )


def test_prompt_allows_empty_subsets() -> None:
    """空 subset (persona_set=() 等) は許容. 全 bit off も valid state."""
    c = PromptChromosome(
        persona_set=(),
        skill_set=(),
        rule_set=(),
        prompt_template_id="base",
        language_style="terse",
        historical_quote_density=0.0,
    )
    assert c.persona_set == ()
    assert c.skill_set == ()
    assert c.rule_set == ()


# ===========================================================================
# E. PromptChromosome — serialization & K proxy
# ===========================================================================


def test_prompt_serialization_round_trip() -> None:
    c = PromptChromosome.default()
    restored = PromptChromosome.from_dict(c.to_dict())
    assert restored == c


def test_prompt_serialization_round_trip_full() -> None:
    """全 persona / skill / rule を有効化した chromosome の round-trip."""
    c = PromptChromosome(
        persona_set=KNOWN_PROMPT_PERSONAS,
        skill_set=KNOWN_PROMPT_SKILLS,
        rule_set=KNOWN_PROMPT_RULES,
        prompt_template_id="debate",
        language_style="academic",
        historical_quote_density=0.9,
    )
    restored = PromptChromosome.from_dict(c.to_dict())
    assert restored == c


def test_prompt_kolmogorov_proxy_positive() -> None:
    c = PromptChromosome.default()
    k = c.kolmogorov_proxy()
    assert k > 0
    assert k > 20


def test_prompt_kolmogorov_proxy_larger_for_full_set() -> None:
    """全 bit on の chromosome は default より K proxy が大きい."""
    simple = PromptChromosome.default()
    complex_ = PromptChromosome(
        persona_set=KNOWN_PROMPT_PERSONAS,
        skill_set=KNOWN_PROMPT_SKILLS,
        rule_set=KNOWN_PROMPT_RULES,
        prompt_template_id="debate",
        language_style="academic",
        historical_quote_density=0.9,
    )
    assert complex_.kolmogorov_proxy() > simple.kolmogorov_proxy()


# ===========================================================================
# F. PromptChromosome — neighborhood sampling
# ===========================================================================


def test_prompt_sample_neighborhood_returns_valid() -> None:
    rng = np.random.default_rng(0)
    base = PromptChromosome.default()
    neighbor = base.sample_neighborhood(rng, step_size=0.3)
    assert isinstance(neighbor, PromptChromosome)
    assert set(neighbor.persona_set).issubset(set(KNOWN_PROMPT_PERSONAS))
    assert set(neighbor.skill_set).issubset(set(KNOWN_PROMPT_SKILLS))
    assert set(neighbor.rule_set).issubset(set(KNOWN_PROMPT_RULES))


def test_prompt_sample_neighborhood_zero_step_is_identity() -> None:
    """step_size=0.0 で flip 確率 0 → 全 field 不変 (σ=0 で連続も不変)."""
    rng = np.random.default_rng(0)
    base = PromptChromosome.default()
    neighbor = base.sample_neighborhood(rng, step_size=0.0)
    assert neighbor == base


def test_prompt_sample_neighborhood_full_step_flips_all() -> None:
    """step_size=1.0 で各 bit が確実に flip → bitmask が完全反転."""
    rng = np.random.default_rng(0)
    base = PromptChromosome.default()
    neighbor = base.sample_neighborhood(rng, step_size=1.0)
    # default persona_set=("polya","triz") → 残り 5 個に反転
    base_persona = set(base.persona_set)
    flipped_persona = set(KNOWN_PROMPT_PERSONAS) - base_persona
    assert set(neighbor.persona_set) == flipped_persona


def test_prompt_sample_neighborhood_is_stochastic() -> None:
    base = PromptChromosome.default()
    neighbors = {
        base.sample_neighborhood(np.random.default_rng(s), step_size=0.5)
        for s in range(20)
    }
    assert len(neighbors) > 1


# ===========================================================================
# G. Subset validation edge cases
# ===========================================================================


def test_prompt_subset_validation_rejects_non_string() -> None:
    with pytest.raises(ValueError, match="persona_set element must be str"):
        PromptChromosome(
            persona_set=("polya", 42),  # type: ignore[arg-type]
            skill_set=("structurize",),
            rule_set=("fail_closed",),
            prompt_template_id="base",
            language_style="terse",
            historical_quote_density=0.1,
        )


def test_impl_and_prompt_are_distinct_types() -> None:
    """両 chromosome が独立した dataclass type であることを確認."""
    impl = ImplChromosome.default()
    prompt = PromptChromosome.default()
    assert type(impl) is not type(prompt)
    assert impl != prompt
