# SPDX-License-Identifier: Apache-2.0
"""Branch predictor (SPEC-MESH-01) — unit tests.

Cover the two predictors (frequency baseline, order-1 Markov), their fail-safe
cold-start behaviour, deterministic tie-breaking, the manifest-branch contract,
and the online hit_rate measurement (including the structured-stream case where
the context model must beat the baseline).
"""

from __future__ import annotations

import pytest

from llive.evolution.branch_predictor import (
    CHANGE_OP_ACTIONS,
    FrequencyPredictor,
    HitRateResult,
    MarkovPredictor,
    evaluate_hit_rate,
    predicted_manifest_branches,
    to_manifest_branch,
)


# --- FrequencyPredictor -----------------------------------------------------


def test_frequency_cold_start_uses_vocab() -> None:
    p = FrequencyPredictor()
    assert p.predict_top_k(2) == list(CHANGE_OP_ACTIONS[:2])


def test_frequency_ranks_by_count() -> None:
    p = FrequencyPredictor()
    for action in ["x", "x", "x", "y", "y", "z"]:
        p.observe(action)
    assert p.predict_top_k(2) == ["x", "y"]


def test_frequency_tie_breaks_by_first_seen() -> None:
    p = FrequencyPredictor()
    for action in ["y", "x"]:  # equal counts; y observed first
        p.observe(action)
    assert p.predict_top_k(2) == ["y", "x"]


# --- top-k bounds (shared behaviour) ----------------------------------------


def test_predict_top_k_non_positive_is_empty() -> None:
    p = FrequencyPredictor()
    assert p.predict_top_k(0) == []
    assert p.predict_top_k(-3) == []


def test_predict_top_k_exceeding_vocab_returns_all() -> None:
    p = FrequencyPredictor()
    assert p.predict_top_k(100) == list(CHANGE_OP_ACTIONS)


# --- MarkovPredictor --------------------------------------------------------


def test_markov_learns_first_order_transition() -> None:
    p = MarkovPredictor()
    for action in ["a", "b", "a", "b", "a", "b"]:  # a->b, b->a
        p.observe(action)
    # last observed is "b"; we taught b->a
    assert p.predict_top_k(1)[0] == "a"
    p.observe("a")  # now last observed is "a"; a->b
    assert p.predict_top_k(1)[0] == "b"


def test_markov_falls_back_to_global_then_vocab_for_unseen_context() -> None:
    p = MarkovPredictor()
    p.observe("a")  # prev="a" but no a-> transitions recorded yet
    top = p.predict_top_k(2)
    assert top[0] == "a"  # from global frequency
    assert len(top) == 2  # padded by default vocab
    assert top[1] in CHANGE_OP_ACTIONS


def test_markov_cold_start_uses_vocab() -> None:
    p = MarkovPredictor()
    assert p.predict_top_k(2) == list(CHANGE_OP_ACTIONS[:2])


# --- hit_rate measurement ---------------------------------------------------


def test_markov_beats_frequency_on_structured_stream() -> None:
    # Perfectly alternating stream carries strong first-order structure.
    seq = ["insert_subblock", "remove_subblock"] * 50
    freq = evaluate_hit_rate(FrequencyPredictor(), seq, k=1)
    markov = evaluate_hit_rate(MarkovPredictor(), seq, k=1)
    assert markov.hit_rate > 0.9  # learns the alternation after warm-up
    assert freq.hit_rate < 0.6  # context-free baseline is near chance
    assert markov.hit_rate > freq.hit_rate


def test_predictors_tie_on_structureless_repeats() -> None:
    # A single repeated action has no branching: both predictors saturate.
    seq = ["insert_subblock"] * 20
    freq = evaluate_hit_rate(FrequencyPredictor(), seq, k=1)
    markov = evaluate_hit_rate(MarkovPredictor(), seq, k=1)
    assert freq.hit_rate == markov.hit_rate == 1.0


def test_evaluate_hit_rate_counts_every_step() -> None:
    seq = ["a", "b", "c"]
    res = evaluate_hit_rate(FrequencyPredictor(), seq, k=4)
    assert isinstance(res, HitRateResult)
    assert res.n_predictions == 3
    assert res.predictor == "frequency"
    assert res.k == 4


def test_evaluate_hit_rate_requires_positive_k() -> None:
    with pytest.raises(ValueError):
        evaluate_hit_rate(FrequencyPredictor(), ["a"], 0)


def test_hit_rate_guards_empty_sequence() -> None:
    res = evaluate_hit_rate(FrequencyPredictor(), [], k=1)
    assert res.n_predictions == 0
    assert res.hits == 0
    assert res.hit_rate == 0.0


# --- manifest branch contract -----------------------------------------------


def test_to_manifest_branch_minimal_shape() -> None:
    branch = to_manifest_branch("insert_subblock", target_container="root")
    assert branch == {"action": "insert_subblock", "target_container": "root"}


def test_to_manifest_branch_carries_extra_fields() -> None:
    branch = to_manifest_branch("insert_subblock", target_container="c", after="head")
    assert branch["after"] == "head"
    assert branch["action"] == "insert_subblock"


def test_predicted_manifest_branches_best_first() -> None:
    p = FrequencyPredictor()
    branches = predicted_manifest_branches(p, 2, target_container="root")
    assert len(branches) == 2
    assert branches[0]["action"] == CHANGE_OP_ACTIONS[0]
    assert all({"action", "target_container"} <= set(b) for b in branches)
