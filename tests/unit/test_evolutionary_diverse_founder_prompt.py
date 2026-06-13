# SPDX-License-Identifier: Apache-2.0
"""diverse founder c_prompt (affinity 由来 prompt skill 多様化) — lldarwin 初期分散向上.

Background (honest disclosure)
------------------------------
lldarwin の 12h 実 LLM 進化ラン (real-pressure / Genome3D / pop24) で best_score が
gen35 で 1.0 に早期飽和した。原因の一つが「全 founder が同一の初期 c_prompt
(:meth:`PromptChromosome.default`) から始まる」= 探索初期分散が低いこと。

本テスト群は :func:`build_founder_genome_3d` の opt-in ``diverse_prompt`` を検証する:

1. ``diverse_prompt=False`` (default): 全 founder の c_prompt が従来通り同一
   (後方互換 = base.c_prompt のまま)。
2. ``diverse_prompt=True``: founder ごとに c_prompt.skill_set が異なり、各 founder の
   skill_set がそのペルソナの factor_affinity 上位因子と整合する (対応表に基づく)。
3. 生成された PromptChromosome が全ペルソナでバリデーション (subset/duplicate) を通る。

対応表 (factor index ↔ prompt skill, インデックス同順):

==  ======================  =================
i   THOUGHT_FACTORS[i]      KNOWN_PROMPT_SKILLS[i]
==  ======================  =================
0   factor_structurize      structurize
1   factor_recompose        recompose
2   factor_closed_loop      loop
3   factor_self_extend      self_extend
4   factor_uncertainty      uncertainty
5   factor_exploration      explore
6   factor_consistency      align
7   factor_provenance       provenance
8   factor_multiview        perspective
9   factor_reality_link     ground
==  ======================  =================
"""

from __future__ import annotations

import numpy as np

from llive.perf.evolutionary.genome_3d import Genome3D
from llive.perf.evolutionary.persona import (
    PERSONA_ONTOLOGY,
    RESEARCH_METHODOLOGY_PERSONA_IDS,
    THOUGHT_FACTORS,
    get_persona,
)
from llive.perf.evolutionary.persona_evolution import (
    build_founder_genome_3d,
    build_founder_individuals_3d,
    run_persona_evolution,
)
from llive.perf.evolutionary.prompt_chromosome import (
    KNOWN_PROMPT_SKILLS,
    PromptChromosome,
)


def _expected_top_k_skills(persona_id: str, k: int = 3) -> set[str]:
    """ペルソナの factor_affinity 上位 k 因子に対応する prompt skill 集合."""
    affinity = np.asarray(get_persona(persona_id).factor_affinity, dtype=np.float64)
    # 安定ソート (降順): 同値は index 昇順で並ぶよう -affinity の argsort を使う。
    order = np.argsort(-affinity, kind="stable")
    top_idx = order[:k]
    return {KNOWN_PROMPT_SKILLS[int(i)] for i in top_idx}


# --- 整合性の前提 (対応表が成立する構造的不変条件) --------------------------


def test_factor_skill_index_alignment() -> None:
    """THOUGHT_FACTORS と KNOWN_PROMPT_SKILLS が同長・index 一対一であること."""
    assert len(THOUGHT_FACTORS) == len(KNOWN_PROMPT_SKILLS) == 10


# --- 後方互換 (default): 全 founder の c_prompt が従来通り同一 ----------------


def test_default_founders_share_identical_c_prompt() -> None:
    """diverse_prompt=False (default) で全 founder の c_prompt が base.c_prompt 同一."""
    base_prompt = Genome3D.default().c_prompt
    for pid in PERSONA_ONTOLOGY:
        g = build_founder_genome_3d(pid)  # diverse_prompt 省略 = False
        assert g.c_prompt == base_prompt


def test_default_individuals_share_identical_c_prompt() -> None:
    """build_founder_individuals_3d (default) でも c_prompt は全 founder 同一."""
    ids = list(PERSONA_ONTOLOGY)
    founders = build_founder_individuals_3d(ids)
    base_prompt = Genome3D.default().c_prompt
    for ind in founders:
        assert ind.genome.c_prompt == base_prompt


# --- diverse_prompt=True: founder ごとに skill_set が異なり affinity と整合 ----


def test_diverse_prompt_skill_set_matches_affinity_top_k() -> None:
    """diverse_prompt=True で各 founder の skill_set が affinity 上位 k 因子と整合."""
    for pid in PERSONA_ONTOLOGY:
        g = build_founder_genome_3d(pid, diverse_prompt=True)
        skill_set = set(g.c_prompt.skill_set)
        assert skill_set == _expected_top_k_skills(pid, k=3), (
            f"{pid}: skill_set {sorted(skill_set)} != "
            f"expected {sorted(_expected_top_k_skills(pid, k=3))}"
        )


def test_diverse_prompt_produces_varied_skill_sets() -> None:
    """diverse_prompt=True で founder 間の skill_set に多様性 (>=2 種) が生まれる."""
    skill_sets = {
        tuple(sorted(build_founder_genome_3d(pid, diverse_prompt=True).c_prompt.skill_set))
        for pid in PERSONA_ONTOLOGY
    }
    assert len(skill_sets) >= 2, (
        "diverse_prompt=True should yield at least 2 distinct skill_sets across personas"
    )


def test_diverse_prompt_chromosome_validates_for_all_personas() -> None:
    """全ペルソナで生成 PromptChromosome が subset/duplicate バリデーションを通る."""
    for pid in PERSONA_ONTOLOGY:
        g = build_founder_genome_3d(pid, diverse_prompt=True)
        cp = g.c_prompt
        # subset: skill_set は KNOWN_PROMPT_SKILLS のサブセット
        assert set(cp.skill_set).issubset(set(KNOWN_PROMPT_SKILLS))
        # duplicate なし
        assert len(cp.skill_set) == len(set(cp.skill_set))
        # __post_init__ 再構築でも例外を出さない (バリデーション通過の二重確認)
        PromptChromosome(
            persona_set=cp.persona_set,
            skill_set=cp.skill_set,
            rule_set=cp.rule_set,
            prompt_template_id=cp.prompt_template_id,
            language_style=cp.language_style,
            historical_quote_density=cp.historical_quote_density,
        )


def test_diverse_prompt_preserves_factor_layer() -> None:
    """diverse_prompt は c_prompt のみ変える: c_factors は従来通り affinity 由来."""
    pid = RESEARCH_METHODOLOGY_PERSONA_IDS[0]
    persona = get_persona(pid)
    g = build_founder_genome_3d(pid, diverse_prompt=True)
    mean_over_layers = g.c_factors.as_array().mean(axis=1)
    np.testing.assert_allclose(
        mean_over_layers, np.asarray(persona.factor_affinity), atol=1e-9
    )


def test_diverse_prompt_individuals_have_varied_c_prompt() -> None:
    """build_founder_individuals_3d(diverse_prompt=True) で c_prompt が founder ごと多様."""
    ids = list(PERSONA_ONTOLOGY)
    founders = build_founder_individuals_3d(ids, diverse_prompt=True)
    prompts = {tuple(sorted(ind.genome.c_prompt.skill_set)) for ind in founders}
    assert len(prompts) >= 2


# --- run_persona_evolution まで貫通 ------------------------------------------


def test_run_persona_evolution_diverse_prompt_flows_through(tmp_path) -> None:
    """run_persona_evolution(genome3d=True, diverse_founder_prompts=True) が貫通する."""
    res = run_persona_evolution(
        RESEARCH_METHODOLOGY_PERSONA_IDS,
        population_size=10,
        generations=3,
        seed=0,
        out_dir=tmp_path,
        genome3d=True,
        diverse_founder_prompts=True,
        patience=99,
        diversity_floor=0.0,
    )
    assert isinstance(res.evolution_result.best_individual.genome, Genome3D)
    assert res.used_proxy_fitness is True


def test_run_persona_evolution_diverse_prompt_default_false(tmp_path) -> None:
    """diverse_founder_prompts 省略時は従来挙動 (founder c_prompt 同一)."""
    res = run_persona_evolution(
        RESEARCH_METHODOLOGY_PERSONA_IDS,
        population_size=10,
        generations=1,
        seed=0,
        genome3d=True,
        patience=99,
        diversity_floor=0.0,
    )
    # gen0 founder の c_prompt が全て base 同一 (best が founder 由来とは限らないので
    # 集団から founder を拾って確認する)。
    base_prompt = Genome3D.default().c_prompt
    founders = [
        ind
        for ind in res.evolution_result.final_population.individuals
        if ind.individual_id.startswith("founder:")
    ]
    # gen1 で founder が生き残っていれば c_prompt は base 同一 (default 経路の回帰)。
    for ind in founders:
        assert ind.genome.c_prompt == base_prompt
