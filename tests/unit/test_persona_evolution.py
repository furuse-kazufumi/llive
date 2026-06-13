# SPDX-License-Identifier: Apache-2.0
"""Persona 世代交代 turnkey ドライバ (persona_evolution) tests.

honest disclosure: 本ドライバの fitness は proxy (LLM を呼ばない)。テストは
proxy 前提で「機構が壊れず回る」「founder が gen0 に乗る」「履歴が書ける」
「決定論的」を検証する。
"""

from __future__ import annotations

import numpy as np
import pytest

from llive.perf.evolutionary.genome import Genome
from llive.perf.evolutionary.individual import FitnessReport
from llive.perf.evolutionary.lineage import render_lineage_mermaid
from llive.perf.evolutionary.llive_variant import THOUGHT_FACTOR_LABELS
from llive.perf.evolutionary.persona import (
    PERSONA_ONTOLOGY,
    RESEARCH_METHODOLOGY_PERSONA_IDS,
    get_persona,
)
from llive.perf.evolutionary.persona_evolution import (
    PersonaEvolutionResult,
    build_founder_genome,
    build_founder_individuals,
    compare_against_llm_baselines,
    founder_persona_id,
    is_founder,
    read_winners,
    run_persona_evolution,
)


# ---------------------------------------------------------------------------
# founder genome / individual
# ---------------------------------------------------------------------------


def test_build_founder_genome_writes_affinity_into_factor_dims() -> None:
    pid = "furuse-kazufumi"
    genome = build_founder_genome(pid)
    assert genome.n_dims == 19
    persona = get_persona(pid)
    arr = genome.as_array()
    # 思考因子 dim 0..9 が persona.factor_affinity と一致
    np.testing.assert_allclose(arr[:10], np.asarray(persona.factor_affinity))


def test_build_founder_individuals_marks_and_orders() -> None:
    ids = ("furuse-kazufumi", "friston")
    founders = build_founder_individuals(ids)
    assert len(founders) == 2
    for ind, pid in zip(founders, ids, strict=True):
        assert is_founder(ind)
        assert founder_persona_id(ind) == pid
        assert ind.birth_generation == 0
        assert ind.parent_ids == ()


def test_is_founder_false_for_random() -> None:
    rng = np.random.default_rng(0)
    from llive.perf.evolutionary.individual import Individual
    from llive.perf.evolutionary.llive_variant import LIVE_VARIANT_GENOME_BOUNDS

    ind = Individual.from_genome(Genome.random(LIVE_VARIANT_GENOME_BOUNDS, rng))
    assert not is_founder(ind)
    assert founder_persona_id(ind) is None


# ---------------------------------------------------------------------------
# run_persona_evolution — core (spec 要件)
# ---------------------------------------------------------------------------


def test_run_persona_evolution_runs_small(tmp_path) -> None:
    result = run_persona_evolution(
        population_size=6, generations=3, seed=0, out_dir=tmp_path
    )
    assert isinstance(result, PersonaEvolutionResult)
    assert result.used_proxy_fitness is True
    assert result.founder_ids == RESEARCH_METHODOLOGY_PERSONA_IDS
    assert result.evolution_result.final_population.generation >= 1


def test_gen0_contains_all_founders() -> None:
    """gen0 に founder が persona 数だけ含まれる (final population は進化後なので
    gen0 を直接組んで確認する経路を使う)."""
    founder_ids = RESEARCH_METHODOLOGY_PERSONA_IDS
    founders = build_founder_individuals(founder_ids)
    marked = [f for f in founders if is_founder(f)]
    assert len(marked) == len(founder_ids)
    assert {founder_persona_id(f) for f in marked} == set(founder_ids)


def test_run_with_zero_generations_keeps_founders_in_population() -> None:
    """generations=0 なら次世代生成が走らないため gen0 (= founders + random) が
    そのまま final population として残り、founder が全員居る."""
    founder_ids = RESEARCH_METHODOLOGY_PERSONA_IDS
    result = run_persona_evolution(
        persona_ids=founder_ids, population_size=6, generations=0, seed=0
    )
    pop = result.evolution_result.final_population
    founders_in_pop = [ind for ind in pop.individuals if is_founder(ind)]
    assert len(founders_in_pop) == len(founder_ids)
    assert {founder_persona_id(f) for f in founders_in_pop} == set(founder_ids)


def test_winners_jsonl_written_and_readable(tmp_path) -> None:
    result = run_persona_evolution(
        population_size=6, generations=3, seed=0, out_dir=tmp_path
    )
    assert result.winners_path is not None
    assert result.winners_path.exists()
    winners = read_winners(result.winners_path)
    assert winners  # 非空
    # 各 winner は generation / score を持つ
    for w in winners:
        assert isinstance(w.score, float)
        assert w.generation >= 0


def test_lineage_mmd_generated_and_nonempty(tmp_path) -> None:
    result = run_persona_evolution(
        population_size=6, generations=3, seed=0, out_dir=tmp_path
    )
    assert result.lineage_path is not None
    assert result.lineage_path.exists()
    text = result.lineage_path.read_text(encoding="utf-8")
    assert "graph TD" in text
    # render_lineage_mermaid 単体でも非空文字列
    winners = read_winners(result.winners_path)
    rendered = render_lineage_mermaid(winners)
    assert isinstance(rendered, str)
    assert rendered.strip()


def test_determinism_same_seed_reproduces_best_score(tmp_path) -> None:
    r1 = run_persona_evolution(
        population_size=6, generations=3, seed=0, out_dir=tmp_path / "a"
    )
    r2 = run_persona_evolution(
        population_size=6, generations=3, seed=0, out_dir=tmp_path / "b"
    )
    assert r1.evolution_result.best_score == pytest.approx(
        r2.evolution_result.best_score
    )


def test_population_size_below_founders_raises() -> None:
    with pytest.raises(ValueError, match="founder count"):
        run_persona_evolution(
            persona_ids=RESEARCH_METHODOLOGY_PERSONA_IDS,
            population_size=2,
            generations=1,
        )


def test_empty_personas_raises() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        run_persona_evolution(persona_ids=(), population_size=4, generations=1)


def test_roster_parameterized_historical_mix(tmp_path) -> None:
    """roster に歴史人物を足すだけで混在できる (段階的定期追加)."""
    mixed = ("furuse-kazufumi", "oka-kiyoshi", "feynman")
    result = run_persona_evolution(
        persona_ids=mixed, population_size=6, generations=2, seed=1, out_dir=tmp_path
    )
    assert result.founder_ids == mixed
    for pid in mixed:
        assert pid in PERSONA_ONTOLOGY


# ---------------------------------------------------------------------------
# custom fitness injection
# ---------------------------------------------------------------------------


def test_custom_fitness_fn_marks_not_proxy() -> None:
    def my_fitness(genome: Genome) -> FitnessReport:
        return FitnessReport(score=float(genome.as_array().sum()))

    result = run_persona_evolution(
        population_size=6, generations=2, seed=0, fitness_fn=my_fitness
    )
    assert result.used_proxy_fitness is False


# ---------------------------------------------------------------------------
# immigration fail-closed (B-LOGIC-2)
# ---------------------------------------------------------------------------


def test_immigration_without_resume_is_fail_closed() -> None:
    """inject_persona_ids 指定 + resume_from なしは silent no-op でなく ValueError.

    immigration は resume snapshot に対して行う設計。inject を指定したのに何も
    起きないと「ペルソナ段階的追加」要件が静かに無視される (B-LOGIC-2)。
    """
    with pytest.raises(ValueError, match="resume_from"):
        run_persona_evolution(
            population_size=6,
            generations=1,
            inject_persona_ids=("friston",),
            resume_from=None,
        )


def test_no_out_dir_skips_files() -> None:
    result = run_persona_evolution(population_size=6, generations=2, seed=0)
    assert result.winners_path is None
    assert result.lineage_path is None


# ---------------------------------------------------------------------------
# LLM 比較 stub (honest disclosure)
# ---------------------------------------------------------------------------


def test_compare_against_llm_baselines_is_stub() -> None:
    result = run_persona_evolution(population_size=6, generations=1, seed=0)
    with pytest.raises(NotImplementedError, match="stub"):
        compare_against_llm_baselines(result, baselines=("gpt-4o",))


def test_proxy_fitness_notes_disclose_proxy() -> None:
    from llive.perf.evolutionary.persona_evolution import _proxy_fitness
    from llive.perf.evolutionary.llive_variant import LIVE_VARIANT_GENOME_BOUNDS

    rng = np.random.default_rng(0)
    rep = _proxy_fitness(Genome.random(LIVE_VARIANT_GENOME_BOUNDS, rng))
    assert "PROXY" in rep.notes
    assert "provenance" in rep.breakdown
    assert THOUGHT_FACTOR_LABELS  # sanity: label tuple importable
