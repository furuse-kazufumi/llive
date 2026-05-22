# SPDX-License-Identifier: Apache-2.0
"""v0.F EV-17 — IndividualWithMultiplicity + parallel_mutate +
ParallelEvaluationResult / evaluate_parallel — unit tests.

ユーザー指摘 (2026-05-22 深夜) の **重複ゲノム + 並列突然変異 + 並列評価** の
skeleton を以下でカバー:

A. DuplicationOrigin enum
B. IndividualWithMultiplicity 構築 + バリデーション + round-trip
C. parallel_mutate: SIMD 風 N fork (n=8, n=1, 独立性, bounds)
D. ParallelEvaluationResult 構築 + バリデーション + round-trip
E. evaluate_parallel: 3 task 評価 + 3 種集約 (mean / median / min)
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from llive.perf.evolutionary.duplication import (
    KNOWN_DUPLICATION_ORIGINS,
    DuplicationOrigin,
    IndividualWithMultiplicity,
)
from llive.perf.evolutionary.genome_3d import Genome3D
from llive.perf.evolutionary.impl_chromosome import ImplChromosome
from llive.perf.evolutionary.parallel_mutation import (
    KNOWN_AGGREGATIONS,
    ParallelEvaluationResult,
    evaluate_parallel,
    parallel_mutate,
)

# ===========================================================================
# A. DuplicationOrigin enum
# ===========================================================================


def test_duplication_origin_has_four_values() -> None:
    values = {o.value for o in DuplicationOrigin}
    assert values == {
        "clone",
        "whole_genome_duplication",
        "horizontal_transfer",
        "parallel_fork",
    }


def test_duplication_origin_known_tuple_matches_enum() -> None:
    assert set(KNOWN_DUPLICATION_ORIGINS) == {o.value for o in DuplicationOrigin}


def test_duplication_origin_is_str_subclass() -> None:
    """``str`` 派生にしておくと JSON / 比較が自然."""
    assert DuplicationOrigin.CLONE == "clone"
    assert DuplicationOrigin.WGD == "whole_genome_duplication"
    assert DuplicationOrigin.HORIZONTAL_TRANSFER == "horizontal_transfer"
    assert DuplicationOrigin.PARALLEL_FORK == "parallel_fork"


# ===========================================================================
# B. IndividualWithMultiplicity 構築 + バリデーション + round-trip
# ===========================================================================


def test_iwm_construct_basic() -> None:
    w = IndividualWithMultiplicity(
        genome_id="abc123",
        multiplicity=1,
        duplication_origin=DuplicationOrigin.CLONE,
    )
    assert w.genome_id == "abc123"
    assert w.multiplicity == 1
    assert w.duplication_origin == DuplicationOrigin.CLONE
    assert w.parent_id is None


def test_iwm_construct_with_parent_and_multiplicity() -> None:
    w = IndividualWithMultiplicity(
        genome_id="child",
        multiplicity=5,
        duplication_origin=DuplicationOrigin.WGD,
        parent_id="parent",
    )
    assert w.multiplicity == 5
    assert w.parent_id == "parent"
    assert w.duplication_origin == DuplicationOrigin.WGD


def test_iwm_rejects_multiplicity_zero() -> None:
    with pytest.raises(ValueError, match="multiplicity"):
        IndividualWithMultiplicity(
            genome_id="g",
            multiplicity=0,
            duplication_origin=DuplicationOrigin.CLONE,
        )


def test_iwm_rejects_multiplicity_negative() -> None:
    with pytest.raises(ValueError, match="multiplicity"):
        IndividualWithMultiplicity(
            genome_id="g",
            multiplicity=-3,
            duplication_origin=DuplicationOrigin.CLONE,
        )


def test_iwm_rejects_empty_genome_id() -> None:
    with pytest.raises(ValueError, match="genome_id"):
        IndividualWithMultiplicity(
            genome_id="",
            multiplicity=1,
            duplication_origin=DuplicationOrigin.CLONE,
        )


def test_iwm_rejects_empty_parent_id() -> None:
    with pytest.raises(ValueError, match="parent_id"):
        IndividualWithMultiplicity(
            genome_id="g",
            multiplicity=1,
            duplication_origin=DuplicationOrigin.CLONE,
            parent_id="",
        )


def test_iwm_rejects_non_enum_origin() -> None:
    with pytest.raises(ValueError, match="duplication_origin"):
        IndividualWithMultiplicity(
            genome_id="g",
            multiplicity=1,
            duplication_origin="clone",  # type: ignore[arg-type]
        )


def test_iwm_is_frozen() -> None:
    w = IndividualWithMultiplicity(
        genome_id="g",
        multiplicity=1,
        duplication_origin=DuplicationOrigin.CLONE,
    )
    with pytest.raises(FrozenInstanceError):
        w.multiplicity = 2  # type: ignore[misc]


def test_iwm_round_trip_basic() -> None:
    w0 = IndividualWithMultiplicity(
        genome_id="abc",
        multiplicity=3,
        duplication_origin=DuplicationOrigin.PARALLEL_FORK,
        parent_id="parent42",
    )
    w1 = IndividualWithMultiplicity.from_dict(w0.to_dict())
    assert w0 == w1


def test_iwm_round_trip_no_parent() -> None:
    w0 = IndividualWithMultiplicity(
        genome_id="seed",
        multiplicity=1,
        duplication_origin=DuplicationOrigin.HORIZONTAL_TRANSFER,
    )
    w1 = IndividualWithMultiplicity.from_dict(w0.to_dict())
    assert w0 == w1
    assert w1.parent_id is None


def test_iwm_to_dict_keys() -> None:
    w = IndividualWithMultiplicity(
        genome_id="g",
        multiplicity=2,
        duplication_origin=DuplicationOrigin.CLONE,
    )
    d = w.to_dict()
    assert set(d.keys()) == {
        "genome_id",
        "multiplicity",
        "duplication_origin",
        "parent_id",
    }
    # origin is plain string in dict (JSON friendly)
    assert d["duplication_origin"] == "clone"


def test_iwm_from_dict_accepts_origin_string() -> None:
    """JSON 経由などで origin が plain string で来ても復元できる."""
    d = {
        "genome_id": "g",
        "multiplicity": 4,
        "duplication_origin": "whole_genome_duplication",
        "parent_id": None,
    }
    w = IndividualWithMultiplicity.from_dict(d)
    assert w.duplication_origin == DuplicationOrigin.WGD


# ===========================================================================
# C. parallel_mutate — SIMD-style N fork
# ===========================================================================


def test_parallel_mutate_returns_n_mutants() -> None:
    g = Genome3D.default()
    rng = np.random.default_rng(0)
    mutants = parallel_mutate(g, n=8, step_size=0.3, rng=rng)
    assert isinstance(mutants, tuple)
    assert len(mutants) == 8


def test_parallel_mutate_each_mutant_is_genome3d() -> None:
    g = Genome3D.default()
    rng = np.random.default_rng(7)
    mutants = parallel_mutate(g, n=5, step_size=0.5, rng=rng)
    for m in mutants:
        assert isinstance(m, Genome3D)
        # validation は __post_init__ で通過済
        assert isinstance(m.c_impl, ImplChromosome)


def test_parallel_mutate_n_equals_one() -> None:
    g = Genome3D.default()
    rng = np.random.default_rng(0)
    mutants = parallel_mutate(g, n=1, step_size=0.2, rng=rng)
    assert len(mutants) == 1
    assert isinstance(mutants[0], Genome3D)


def test_parallel_mutate_rejects_n_zero() -> None:
    g = Genome3D.default()
    with pytest.raises(ValueError, match="n"):
        parallel_mutate(g, n=0)


def test_parallel_mutate_rejects_n_negative() -> None:
    g = Genome3D.default()
    with pytest.raises(ValueError, match="n"):
        parallel_mutate(g, n=-3)


def test_parallel_mutate_rejects_genome_without_method() -> None:
    """``sample_neighborhood`` を持たない object は TypeError."""
    with pytest.raises(TypeError, match="sample_neighborhood"):
        parallel_mutate(object(), n=2)


def test_parallel_mutate_diverges_from_origin_at_large_step() -> None:
    """step_size 大では少なくとも 1 個は親と異なる."""
    g = Genome3D.default()
    rng = np.random.default_rng(1234)
    mutants = parallel_mutate(g, n=16, step_size=0.9, rng=rng)
    different = [m for m in mutants if m != g]
    assert len(different) > 0, "step=0.9 で 16 個全部が親と同一は異常"


def test_parallel_mutate_independent_runs_differ() -> None:
    """異なる seed の RNG では結果が異なる (独立 sampling の確認)."""
    g = Genome3D.default()
    rng_a = np.random.default_rng(1)
    rng_b = np.random.default_rng(2)
    a = parallel_mutate(g, n=8, step_size=0.5, rng=rng_a)
    b = parallel_mutate(g, n=8, step_size=0.5, rng=rng_b)
    # 2 batch を tuple→set 化して差を検出
    assert a != b


def test_parallel_mutate_default_rng_when_none() -> None:
    """rng=None でも例外を出さず動くこと."""
    g = Genome3D.default()
    mutants = parallel_mutate(g, n=4, step_size=0.3, rng=None)
    assert len(mutants) == 4


def test_parallel_mutate_within_batch_some_differ() -> None:
    """1 batch 内でも step_size が十分大きければ mutant 同士に差が出る."""
    g = Genome3D.default()
    rng = np.random.default_rng(20260522)
    mutants = parallel_mutate(g, n=16, step_size=0.9, rng=rng)
    unique = set(mutants)
    # 全 16 個が同一はあり得ない (step_size=0.9, 8 enum field)
    assert len(unique) > 1


# ===========================================================================
# D. ParallelEvaluationResult — 構築 + バリデーション + round-trip
# ===========================================================================


def test_per_result_construct_basic() -> None:
    r = ParallelEvaluationResult(
        individual_id="abc",
        fitness_per_task=(("t1", 1.0), ("t2", 2.0)),
        consensus_score=1.5,
        divergence=0.5,
    )
    assert r.individual_id == "abc"
    assert r.fitness_per_task == (("t1", 1.0), ("t2", 2.0))
    assert r.consensus_score == 1.5
    assert r.divergence == 0.5


def test_per_result_rejects_empty_fitness() -> None:
    with pytest.raises(ValueError, match="fitness_per_task is empty"):
        ParallelEvaluationResult(
            individual_id="abc",
            fitness_per_task=(),
            consensus_score=0.0,
            divergence=0.0,
        )


def test_per_result_rejects_empty_id() -> None:
    with pytest.raises(ValueError, match="individual_id"):
        ParallelEvaluationResult(
            individual_id="",
            fitness_per_task=(("t1", 1.0),),
            consensus_score=1.0,
            divergence=0.0,
        )


def test_per_result_rejects_duplicate_task_names() -> None:
    with pytest.raises(ValueError, match="duplicate task name"):
        ParallelEvaluationResult(
            individual_id="g",
            fitness_per_task=(("t1", 1.0), ("t1", 2.0)),
            consensus_score=1.5,
            divergence=0.5,
        )


def test_per_result_rejects_non_finite_fitness() -> None:
    with pytest.raises(ValueError, match="not finite"):
        ParallelEvaluationResult(
            individual_id="g",
            fitness_per_task=(("t1", float("nan")),),
            consensus_score=0.0,
            divergence=0.0,
        )


def test_per_result_rejects_negative_divergence() -> None:
    with pytest.raises(ValueError, match="divergence"):
        ParallelEvaluationResult(
            individual_id="g",
            fitness_per_task=(("t1", 1.0),),
            consensus_score=1.0,
            divergence=-0.1,
        )


def test_per_result_is_frozen() -> None:
    r = ParallelEvaluationResult(
        individual_id="abc",
        fitness_per_task=(("t1", 1.0),),
        consensus_score=1.0,
        divergence=0.0,
    )
    with pytest.raises(FrozenInstanceError):
        r.consensus_score = 2.0  # type: ignore[misc]


def test_per_result_round_trip() -> None:
    r0 = ParallelEvaluationResult(
        individual_id="abc",
        fitness_per_task=(("t1", -1.5), ("t2", 2.25), ("t3", 0.0)),
        consensus_score=0.25,
        divergence=1.5,
    )
    r1 = ParallelEvaluationResult.from_dict(r0.to_dict())
    assert r0 == r1


# ===========================================================================
# E. evaluate_parallel — 集約戦略
# ===========================================================================


def _build_3_task_fns() -> dict[str, callable]:  # type: ignore[name-defined]
    """returns: {t_a: ()->1.0, t_b: ()->2.0, t_c: ()->3.0}."""
    return {
        "task_a": lambda: 1.0,
        "task_b": lambda: 2.0,
        "task_c": lambda: 3.0,
    }


def test_evaluate_parallel_three_tasks_mean() -> None:
    r = evaluate_parallel(
        individual_id="g",
        fitness_fns=_build_3_task_fns(),
        aggregation="mean",
    )
    assert len(r.fitness_per_task) == 3
    names = [n for n, _ in r.fitness_per_task]
    assert names == ["task_a", "task_b", "task_c"]
    assert r.consensus_score == pytest.approx(2.0)
    # std of {1,2,3} = sqrt(2/3) ≈ 0.8165
    assert r.divergence == pytest.approx(np.std([1.0, 2.0, 3.0]), rel=1e-6)


def test_evaluate_parallel_median() -> None:
    r = evaluate_parallel(
        individual_id="g",
        fitness_fns=_build_3_task_fns(),
        aggregation="median",
    )
    assert r.consensus_score == pytest.approx(2.0)


def test_evaluate_parallel_min() -> None:
    r = evaluate_parallel(
        individual_id="g",
        fitness_fns=_build_3_task_fns(),
        aggregation="min",
    )
    assert r.consensus_score == pytest.approx(1.0)


def test_evaluate_parallel_min_with_negative_values() -> None:
    fns = {
        "a": lambda: -5.0,
        "b": lambda: 0.0,
        "c": lambda: 5.0,
    }
    r = evaluate_parallel(individual_id="g", fitness_fns=fns, aggregation="min")
    assert r.consensus_score == pytest.approx(-5.0)


def test_evaluate_parallel_single_task_divergence_zero() -> None:
    r = evaluate_parallel(
        individual_id="g",
        fitness_fns={"only": lambda: 42.0},
        aggregation="mean",
    )
    assert r.consensus_score == pytest.approx(42.0)
    assert r.divergence == pytest.approx(0.0)


def test_evaluate_parallel_rejects_empty_fitness_fns() -> None:
    with pytest.raises(ValueError, match="fitness_fns is empty"):
        evaluate_parallel(individual_id="g", fitness_fns={}, aggregation="mean")


def test_evaluate_parallel_rejects_unknown_aggregation() -> None:
    with pytest.raises(ValueError, match="aggregation"):
        evaluate_parallel(
            individual_id="g",
            fitness_fns={"t": lambda: 1.0},
            aggregation="max",  # not supported in skeleton
        )


def test_evaluate_parallel_known_aggregations_listed() -> None:
    assert set(KNOWN_AGGREGATIONS) == {"mean", "median", "min"}


def test_evaluate_parallel_divergence_is_nonneg() -> None:
    """divergence は常に >= 0 (pstdev は非負)."""
    fns = {f"t{i}": (lambda v=i: float(v)) for i in range(5)}
    r = evaluate_parallel(individual_id="g", fitness_fns=fns, aggregation="mean")
    assert r.divergence >= 0.0


def test_evaluate_parallel_all_equal_divergence_zero() -> None:
    fns = {"a": lambda: 1.0, "b": lambda: 1.0, "c": lambda: 1.0}
    r = evaluate_parallel(individual_id="g", fitness_fns=fns, aggregation="mean")
    assert r.consensus_score == pytest.approx(1.0)
    assert r.divergence == pytest.approx(0.0)
