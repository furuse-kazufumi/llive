# SPDX-License-Identifier: Apache-2.0
"""MetaChromosome + MetaEvolutionLoop (v0.I EV-21/22 skeleton) — unit tests.

ユーザー指示 (2026-05-22) "TRIZ で先読みせよ / 技術的に驚かせよ" に応答した
v0.I 案 A Meta-Evolution Gene の skeleton 検証.

カバー範囲:

1. MetaChromosome バリデーション
2. serialization (to_dict / from_dict round-trip)
3. Kolmogorov proxy (gzip ベース)
4. neighborhood sampling
5. UCB1 score (cold start = +inf, 通常 score)
6. MetaEvolutionLoop selection / record_delta / scores
7. neighborhood expansion
8. apply (mock dispatch)
9. snapshot (observability)

実 sandbox AST 実行 + EvolutionLoop 統合は EV-22 残以降.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from llive.perf.evolutionary.meta_chromosome import (
    KNOWN_ALGORITHM_IDS,
    KNOWN_CROSSOVER_STRATEGIES,
    LAYER_NAMES,
    MetaChromosome,
    ucb1_score,
)
from llive.perf.evolutionary.experimental.meta_loop import (
    MetaEvolutionLoop,
)

# ===========================================================================
# 1. MetaChromosome — validation
# ===========================================================================


def test_default_constructs_valid_chromosome() -> None:
    c = MetaChromosome.default()
    assert len(c.mutation_rate_per_layer) == len(LAYER_NAMES)
    assert c.crossover_strategy in KNOWN_CROSSOVER_STRATEGIES
    assert c.algorithm_id in KNOWN_ALGORITHM_IDS
    assert 0.0 <= c.novelty_weight <= 1.0
    assert c.cluster_quota >= 1


def test_rejects_invalid_mutation_rate() -> None:
    with pytest.raises(ValueError, match="mutation rate"):
        MetaChromosome(
            mutation_rate_per_layer=(0.5, 1.5, 0.02),  # 1.5 > 1.0
            crossover_strategy="intra",
            selection_pressure=0.5,
            novelty_weight=0.0,
            cluster_quota=4,
            meta_mutation_decay=0.5,
            algorithm_id="tournament_gauss",
        )


def test_rejects_wrong_layer_count() -> None:
    with pytest.raises(ValueError, match="mutation_rate_per_layer"):
        MetaChromosome(
            mutation_rate_per_layer=(0.5, 0.5),  # 2 layers instead of 3
            crossover_strategy="intra",
            selection_pressure=0.5,
            novelty_weight=0.0,
            cluster_quota=4,
            meta_mutation_decay=0.5,
            algorithm_id="tournament_gauss",
        )


def test_rejects_unknown_crossover() -> None:
    with pytest.raises(ValueError, match="crossover_strategy"):
        MetaChromosome(
            mutation_rate_per_layer=(0.05, 0.15, 0.02),
            crossover_strategy="quantum_teleport",
            selection_pressure=0.5,
            novelty_weight=0.0,
            cluster_quota=4,
            meta_mutation_decay=0.5,
            algorithm_id="tournament_gauss",
        )


def test_rejects_unknown_algorithm_id() -> None:
    with pytest.raises(ValueError, match="algorithm_id"):
        MetaChromosome(
            mutation_rate_per_layer=(0.05, 0.15, 0.02),
            crossover_strategy="intra",
            selection_pressure=0.5,
            novelty_weight=0.0,
            cluster_quota=4,
            meta_mutation_decay=0.5,
            algorithm_id="alphazero_dreamer",  # not in KNOWN_ALGORITHM_IDS
        )


def test_rejects_invalid_selection_pressure() -> None:
    with pytest.raises(ValueError, match="selection_pressure"):
        MetaChromosome(
            mutation_rate_per_layer=(0.05, 0.15, 0.02),
            crossover_strategy="intra",
            selection_pressure=0.0,  # must be > 0
            novelty_weight=0.0,
            cluster_quota=4,
            meta_mutation_decay=0.5,
            algorithm_id="tournament_gauss",
        )


def test_rejects_cluster_quota_zero() -> None:
    with pytest.raises(ValueError, match="cluster_quota"):
        MetaChromosome(
            mutation_rate_per_layer=(0.05, 0.15, 0.02),
            crossover_strategy="intra",
            selection_pressure=0.5,
            novelty_weight=0.0,
            cluster_quota=0,
            meta_mutation_decay=0.5,
            algorithm_id="tournament_gauss",
        )


# ===========================================================================
# 2. Serialization round-trip
# ===========================================================================


def test_serialization_round_trip() -> None:
    c = MetaChromosome.default()
    restored = MetaChromosome.from_dict(c.to_dict())
    assert restored == c


def test_serialization_with_algorithm_params() -> None:
    c = MetaChromosome(
        mutation_rate_per_layer=(0.1, 0.2, 0.01),
        crossover_strategy="segment",
        selection_pressure=0.7,
        novelty_weight=0.4,
        cluster_quota=8,
        meta_mutation_decay=0.3,
        algorithm_id="nsga2_novelty",
        algorithm_params=(("temperature", 0.5), ("eta", 20.0)),
    )
    restored = MetaChromosome.from_dict(c.to_dict())
    assert restored == c
    assert restored.algorithm_params == (("temperature", 0.5), ("eta", 20.0))


def test_to_json_bytes_is_deterministic() -> None:
    """sort_keys=True で同一内容は同一 bytes になる (K proxy 再現性)."""
    c1 = MetaChromosome.default()
    c2 = MetaChromosome.default()
    assert c1.to_json_bytes() == c2.to_json_bytes()


# ===========================================================================
# 3. Kolmogorov complexity proxy (gzip)
# ===========================================================================


def test_kolmogorov_proxy_positive() -> None:
    c = MetaChromosome.default()
    k = c.kolmogorov_proxy()
    assert k > 0
    # gzip overhead を考えても 24 byte 未満になるはずがない
    assert k > 20


def test_kolmogorov_proxy_smaller_for_simpler() -> None:
    """algorithm_params 多い chromosome の方が K proxy が大きい (実用近似)."""
    simple = MetaChromosome.default()
    complex_ = MetaChromosome(
        mutation_rate_per_layer=(0.05, 0.15, 0.02),
        crossover_strategy="intra",
        selection_pressure=0.5,
        novelty_weight=0.0,
        cluster_quota=4,
        meta_mutation_decay=0.5,
        algorithm_id="tournament_gauss",
        algorithm_params=(
            ("a", 1.0), ("b", 2.0), ("c", 3.0), ("d", 4.0),
            ("e", 5.0), ("f", 6.0),
        ),
    )
    assert complex_.kolmogorov_proxy() > simple.kolmogorov_proxy()


# ===========================================================================
# 4. Neighborhood sampling
# ===========================================================================


def test_sample_neighborhood_returns_valid_chromosome() -> None:
    rng = np.random.default_rng(0)
    base = MetaChromosome.default()
    neighbor = base.sample_neighborhood(rng, step_size=0.1)
    # validation が走るので, valid chromosome である
    assert isinstance(neighbor, MetaChromosome)
    assert neighbor.cluster_quota >= 1


def test_sample_neighborhood_is_stochastic() -> None:
    """異なる rng seed で異なる結果が返る."""
    base = MetaChromosome.default()
    neighbors = [
        base.sample_neighborhood(np.random.default_rng(s), step_size=0.2)
        for s in range(10)
    ]
    # 10 個サンプリングしてすべて同一にはならない
    assert len(set(neighbors)) > 1


def test_sample_neighborhood_decay_dampens_step() -> None:
    """meta_mutation_decay = 1.0 なら effective_step = 0 になり連続 field は不変."""
    rng = np.random.default_rng(0)
    base = MetaChromosome(
        mutation_rate_per_layer=(0.05, 0.15, 0.02),
        crossover_strategy="intra",
        selection_pressure=0.5,
        novelty_weight=0.0,
        cluster_quota=4,
        meta_mutation_decay=1.0,  # full self-limit
        algorithm_id="tournament_gauss",
    )
    neighbor = base.sample_neighborhood(rng, step_size=0.5)
    # 連続 field (mutation rates, selection, novelty, decay) は ±0 → ほぼ同一
    # ただし discrete (crossover_strategy / algorithm_id / cluster_quota) は変わりうる
    assert neighbor.mutation_rate_per_layer == base.mutation_rate_per_layer
    assert neighbor.selection_pressure == base.selection_pressure
    assert neighbor.novelty_weight == base.novelty_weight
    assert neighbor.meta_mutation_decay == base.meta_mutation_decay


# ===========================================================================
# 5. UCB1 score
# ===========================================================================


def test_ucb1_cold_start_is_inf() -> None:
    assert math.isinf(ucb1_score(mean_delta=0.0, use_count=0, total_gen=5))


def test_ucb1_includes_exploration_bonus() -> None:
    # use_count = 1, total_gen = 10, c = sqrt(2)
    # score = 0.5 + sqrt(2) * sqrt(2 ln 10 / 1) = 0.5 + sqrt(2) * sqrt(2 * 2.302...)
    score = ucb1_score(mean_delta=0.5, use_count=1, total_gen=10, exploration_c=math.sqrt(2.0))
    assert score > 0.5  # bonus 加わって増える
    expected_bonus = math.sqrt(2.0) * math.sqrt(2.0 * math.log(10) / 1)
    assert math.isclose(score, 0.5 + expected_bonus, rel_tol=1e-9)


def test_ucb1_exploitation_dominates_with_many_uses() -> None:
    # use_count 大 → bonus 小 → mean_delta が支配
    # c=sqrt(2), n=10000, N=10^6: bonus = sqrt(2) * sqrt(2 * ln(1e6) / 10000) ≈ 0.074
    score = ucb1_score(mean_delta=0.5, use_count=10_000, total_gen=1_000_000)
    assert score < 0.6  # bonus は 0.1 未満


# ===========================================================================
# 6. MetaEvolutionLoop — selection / record
# ===========================================================================


def test_loop_register_and_select_cold_start() -> None:
    loop = MetaEvolutionLoop()
    c = MetaChromosome.default()
    loop.register(c)
    chosen = loop.select_next()
    assert chosen == c


def test_loop_select_raises_when_empty() -> None:
    loop = MetaEvolutionLoop()
    with pytest.raises(RuntimeError, match="no candidate"):
        loop.select_next()


def test_loop_record_delta_advances_generation() -> None:
    loop = MetaEvolutionLoop()
    c = MetaChromosome.default()
    loop.register(c)
    assert loop.state.generation == 0
    loop.record_delta(c, fitness_delta=0.1)
    assert loop.state.generation == 1
    assert loop.state.candidates[c].use_count == 1
    assert math.isclose(loop.state.candidates[c].cum_delta, 0.1)


def test_loop_scores_cold_start_all_inf() -> None:
    loop = MetaEvolutionLoop()
    c1 = MetaChromosome.default()
    c2 = c1.sample_neighborhood(np.random.default_rng(1), step_size=0.3)
    loop.register(c1)
    loop.register(c2)
    scores = loop.state.scores()
    assert all(math.isinf(s) for s in scores.values())


def test_loop_selection_prefers_better_after_warmup() -> None:
    """全 candidate を 1 回ずつ warmup させた後、 mean_Δ 大 + bonus を加味して選ぶ."""
    rng = np.random.default_rng(0)
    loop = MetaEvolutionLoop()
    good = MetaChromosome.default()
    bad = MetaChromosome(
        mutation_rate_per_layer=(0.9, 0.9, 0.9),
        crossover_strategy="bit",
        selection_pressure=0.1,
        novelty_weight=0.9,
        cluster_quota=20,
        meta_mutation_decay=0.0,
        algorithm_id="map_elites_niche",
    )
    loop.register(good)
    loop.register(bad)

    # warmup: 両 candidate を **十分均等に** 使う (cold start fairness で
    # use_count 少ない方の bonus が大きくなりすぎないように 30 回ずつ).
    # UCB1 は use_count 少ない arm を探索する性質があるため、両方を等しく
    # 試した後でないと mean_Δ の差が score に反映されにくい.
    for _ in range(30):
        loop.record_delta(good, fitness_delta=1.0)
        loop.record_delta(bad, fitness_delta=0.01)

    # この時点で good の方が UCB1 score が高い (bonus は同等, mean が支配)
    scores = loop.state.scores()
    assert scores[good] > scores[bad]
    chosen = loop.select_next(rng)
    assert chosen == good


# ===========================================================================
# 7. Neighborhood expansion
# ===========================================================================


def test_expand_neighborhood_grows_candidate_set() -> None:
    rng = np.random.default_rng(0)
    loop = MetaEvolutionLoop(expansion_threshold=0.0)
    base = MetaChromosome.default()
    loop.register(base)
    # warmup
    loop.record_delta(base, fitness_delta=0.1)

    initial_count = len(loop.state.candidates)
    new = loop.expand_neighborhood(rng, max_new=3, step_size=0.3)

    # 0 個 ~ 3 個追加されうる (近傍が偶然既存と一致した場合は skip)
    assert len(loop.state.candidates) >= initial_count
    assert len(loop.state.candidates) - initial_count == len(new)


def test_expand_neighborhood_skips_when_no_eligible() -> None:
    """use_count == 0 の candidate しか無いと expand しない."""
    rng = np.random.default_rng(0)
    loop = MetaEvolutionLoop(expansion_threshold=0.0)
    loop.register(MetaChromosome.default())
    # まだ record_delta していない → expansion 対象なし
    new = loop.expand_neighborhood(rng, max_new=3)
    assert new == []


# ===========================================================================
# 8. apply (mock dispatch)
# ===========================================================================


def test_apply_with_mock_dispatch() -> None:
    """algorithm_id 経由で callable に dispatch できる skeleton 動作."""
    rng = np.random.default_rng(0)
    loop = MetaEvolutionLoop()
    c = MetaChromosome.default()
    loop.register(c)

    captured: list[MetaChromosome] = []

    def mock_alg(chromosome: MetaChromosome, _rng: np.random.Generator) -> float:
        captured.append(chromosome)
        return 0.42

    loop.register_dispatch("tournament_gauss", mock_alg)
    delta = loop.apply(c, rng)

    assert delta == 0.42
    assert captured == [c]
    assert loop.state.candidates[c].use_count == 1


def test_apply_raises_without_dispatch() -> None:
    rng = np.random.default_rng(0)
    loop = MetaEvolutionLoop()
    c = MetaChromosome.default()
    loop.register(c)
    with pytest.raises(RuntimeError, match="no dispatch"):
        loop.apply(c, rng)


def test_register_dispatch_rejects_unknown_id() -> None:
    loop = MetaEvolutionLoop()
    with pytest.raises(ValueError, match="algorithm_id"):
        loop.register_dispatch("unknown_alg", lambda c, r: 0.0)


# ===========================================================================
# 9. snapshot (observability)
# ===========================================================================


def test_snapshot_contains_all_state() -> None:
    rng = np.random.default_rng(0)
    loop = MetaEvolutionLoop()
    c = MetaChromosome.default()
    loop.register(c)

    def mock_alg(_c: MetaChromosome, _r: np.random.Generator) -> float:
        return 0.3

    loop.register_dispatch("tournament_gauss", mock_alg)
    loop.apply(c, rng)

    snap = loop.snapshot()
    assert snap["generation"] == 1
    assert len(snap["candidates"]) == 1
    assert snap["candidates"][0]["use_count"] == 1
    assert math.isclose(snap["candidates"][0]["cum_delta"], 0.3)
    assert snap["candidates"][0]["k_proxy"] > 0
