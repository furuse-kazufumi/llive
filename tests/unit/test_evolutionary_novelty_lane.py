# SPDX-License-Identifier: Apache-2.0
"""Novelty Lane (v0.F EV-15/16 柱 B) — unit tests.

Coverage:

* :class:`NoveltyDescriptor` / :class:`NoveltyScore` — frozen 性 + 基本構築
* :func:`compute_novelty_scores` — k-NN 距離計算の正しさ
  - 集団 N=10, k=3 で正しい近傍距離
  - 同質集団 → 低 score / ばらけた集団 → 高 score
  - distance 切替 (euclidean / manhattan / cosine)
  - エッジケース (空集団, N=1, k > N-1, embedding mismatch)
* :class:`MultiObjectiveSelector` — fitness top + novelty top の重複除外
  - n_fitness=0 / m_novelty=0 のエッジケース
  - 同点 tie-break (ID 昇順)
* timing — N=100 でも妥当な時間で終わる (strict ではない)
"""

from __future__ import annotations

import math
import time

import pytest

from llive.perf.evolutionary import (
    MultiObjectiveSelector,
    NoveltyDescriptor,
    NoveltyScore,
    compute_novelty_scores,
)

# ---------------------------------------------------------------------------
# 1. NoveltyDescriptor / NoveltyScore data class basics
# ---------------------------------------------------------------------------


def test_descriptor_is_frozen() -> None:
    desc = NoveltyDescriptor(embedding=(1.0, 2.0, 3.0))
    with pytest.raises(Exception):  # noqa: PT011, B017 — FrozenInstanceError
        desc.embedding = (9.0, 9.0, 9.0)  # type: ignore[misc]


def test_descriptor_metadata_default_empty() -> None:
    desc = NoveltyDescriptor(embedding=(0.5, 0.5))
    assert desc.metadata == ()


def test_descriptor_with_metadata() -> None:
    desc = NoveltyDescriptor(
        embedding=(0.1, 0.2),
        metadata=(("backend", "openai"), ("persona", "polya")),
    )
    assert desc.metadata == (("backend", "openai"), ("persona", "polya"))


def test_descriptor_empty_embedding_rejected() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        NoveltyDescriptor(embedding=())


def test_descriptor_hashable() -> None:
    """frozen dataclass は hash 可能 (set / dict key で使える)."""
    a = NoveltyDescriptor(embedding=(1.0, 2.0))
    b = NoveltyDescriptor(embedding=(1.0, 2.0))
    s = {a, b}
    assert len(s) == 1


def test_score_is_frozen() -> None:
    score = NoveltyScore(individual_id="ind-001", score=0.42, k=3)
    with pytest.raises(Exception):  # noqa: PT011, B017 — FrozenInstanceError
        score.score = 0.99  # type: ignore[misc]


def test_score_fields() -> None:
    score = NoveltyScore(individual_id="x", score=1.5, k=5)
    assert score.individual_id == "x"
    assert score.score == pytest.approx(1.5)
    assert score.k == 5


# ---------------------------------------------------------------------------
# 2. compute_novelty_scores — correctness
# ---------------------------------------------------------------------------


def _grid_descriptors(n: int, dim: int = 2) -> list[tuple[str, NoveltyDescriptor]]:
    """1 直線上に等間隔で並べた descriptor 集団."""
    return [
        (
            f"ind-{i:03d}",
            NoveltyDescriptor(embedding=tuple(float(i) for _ in range(dim))),
        )
        for i in range(n)
    ]


def test_compute_novelty_returns_one_score_per_descriptor() -> None:
    descs = _grid_descriptors(10)
    scores = compute_novelty_scores(descs, k=3)
    assert len(scores) == 10
    assert all(isinstance(s, NoveltyScore) for s in scores)
    # 順序保存
    for i, s in enumerate(scores):
        assert s.individual_id == f"ind-{i:03d}"


def test_compute_novelty_k_value_in_result() -> None:
    """返り値の k は実際に使われた k_use (= min(k, N-1))."""
    descs = _grid_descriptors(10)
    scores = compute_novelty_scores(descs, k=3)
    assert all(s.k == 3 for s in scores)


def test_compute_novelty_k_clamped_when_k_exceeds_population() -> None:
    """k > N-1 のとき k_use = N - 1 に自動 fallback."""
    descs = _grid_descriptors(5)
    scores = compute_novelty_scores(descs, k=15)
    # N=5 → k_use = 4
    assert all(s.k == 4 for s in scores)


def test_compute_novelty_grid_n10_k3_correct_distance() -> None:
    """等間隔 1D grid (0..9) で k=3 → 端の個体は内側 3 個との平均距離 (1+2+3)/3=2.0."""
    descs = _grid_descriptors(10, dim=1)
    scores = compute_novelty_scores(descs, k=3)
    # ind-000 の k=3 nearest は ind-001 / ind-002 / ind-003 → 距離 1, 2, 3
    assert scores[0].score == pytest.approx((1.0 + 2.0 + 3.0) / 3.0)
    # ind-009 (端) も同様
    assert scores[9].score == pytest.approx((1.0 + 2.0 + 3.0) / 3.0)
    # 中央 ind-004 の k=3 nearest は ind-003 / ind-005 / ind-002 (or ind-006) → 1, 1, 2
    assert scores[4].score == pytest.approx((1.0 + 1.0 + 2.0) / 3.0)


def test_compute_novelty_homogeneous_population_low_score() -> None:
    """同質集団 (全員同一 embedding) → 全 score は 0 に近い."""
    descs = [
        (f"ind-{i}", NoveltyDescriptor(embedding=(1.0, 1.0, 1.0)))
        for i in range(8)
    ]
    scores = compute_novelty_scores(descs, k=3)
    for s in scores:
        assert s.score == pytest.approx(0.0, abs=1e-9)


def test_compute_novelty_heterogeneous_population_higher_score() -> None:
    """ばらけた集団 vs 同質集団で平均 score が後者より高い."""
    homo = [
        (f"h-{i}", NoveltyDescriptor(embedding=(1.0, 1.0)))
        for i in range(10)
    ]
    hetero = [
        (
            f"e-{i}",
            NoveltyDescriptor(embedding=(float(i), float(i * i))),
        )
        for i in range(10)
    ]
    homo_scores = compute_novelty_scores(homo, k=3)
    hetero_scores = compute_novelty_scores(hetero, k=3)

    homo_avg = sum(s.score for s in homo_scores) / len(homo_scores)
    hetero_avg = sum(s.score for s in hetero_scores) / len(hetero_scores)
    assert hetero_avg > homo_avg
    assert hetero_avg > 1.0


def test_compute_novelty_manhattan_distance() -> None:
    descs = [
        ("a", NoveltyDescriptor(embedding=(0.0, 0.0))),
        ("b", NoveltyDescriptor(embedding=(3.0, 4.0))),
        ("c", NoveltyDescriptor(embedding=(6.0, 8.0))),
    ]
    # Manhattan: a↔b = 7, a↔c = 14, b↔c = 7
    scores = compute_novelty_scores(descs, k=2, distance="manhattan")
    by_id = {s.individual_id: s.score for s in scores}
    # a: nearest = [b=7, c=14] → mean = 10.5
    assert by_id["a"] == pytest.approx((7.0 + 14.0) / 2.0)
    # b: nearest = [a=7, c=7] → mean = 7.0
    assert by_id["b"] == pytest.approx(7.0)
    # c: nearest = [b=7, a=14] → mean = 10.5
    assert by_id["c"] == pytest.approx((7.0 + 14.0) / 2.0)


def test_compute_novelty_cosine_distance() -> None:
    """同方向ベクトル → cosine 距離 0, 直交 → 1."""
    descs = [
        ("same1", NoveltyDescriptor(embedding=(1.0, 0.0))),
        ("same2", NoveltyDescriptor(embedding=(2.0, 0.0))),  # 同方向
        ("orth", NoveltyDescriptor(embedding=(0.0, 1.0))),   # 直交
    ]
    scores = compute_novelty_scores(descs, k=2, distance="cosine")
    by_id = {s.individual_id: s.score for s in scores}
    # same1 ↔ same2 = 0, same1 ↔ orth = 1 → mean = 0.5
    assert by_id["same1"] == pytest.approx(0.5, abs=1e-6)
    assert by_id["same2"] == pytest.approx(0.5, abs=1e-6)
    # orth ↔ same1 = 1, orth ↔ same2 = 1 → mean = 1
    assert by_id["orth"] == pytest.approx(1.0, abs=1e-6)


def test_compute_novelty_empty_input() -> None:
    assert compute_novelty_scores([], k=3) == []


def test_compute_novelty_single_individual() -> None:
    """N=1 → 比較対象なし. score=0, k=0 を返す."""
    descs = [("only", NoveltyDescriptor(embedding=(1.0, 2.0)))]
    scores = compute_novelty_scores(descs, k=5)
    assert len(scores) == 1
    assert scores[0].score == 0.0
    assert scores[0].k == 0


def test_compute_novelty_invalid_k() -> None:
    descs = _grid_descriptors(3)
    with pytest.raises(ValueError, match="k must be >= 1"):
        compute_novelty_scores(descs, k=0)


def test_compute_novelty_invalid_distance() -> None:
    descs = _grid_descriptors(3)
    with pytest.raises(ValueError, match="unsupported distance"):
        compute_novelty_scores(descs, k=2, distance="hamming")


def test_compute_novelty_embedding_dim_mismatch() -> None:
    descs = [
        ("a", NoveltyDescriptor(embedding=(1.0, 2.0))),
        ("b", NoveltyDescriptor(embedding=(1.0, 2.0, 3.0))),  # mismatch
    ]
    with pytest.raises(ValueError, match="dimension mismatch"):
        compute_novelty_scores(descs, k=1)


# ---------------------------------------------------------------------------
# 3. MultiObjectiveSelector
# ---------------------------------------------------------------------------


def test_selector_basic_no_overlap() -> None:
    """fitness top と novelty top が完全に独立な ID set のケース."""
    selector = MultiObjectiveSelector(n_fitness=2, m_novelty=2)
    fitness = {"a": 0.9, "b": 0.8, "c": 0.1, "d": 0.2}
    novelty = {"c": 0.95, "d": 0.85, "a": 0.05, "b": 0.10}
    result = selector.select(fitness, novelty)
    # fitness top-2: a, b. novelty top-2 (excl a/b): c, d
    assert result == ["a", "b", "c", "d"]


def test_selector_deduplication_when_overlap() -> None:
    """同一 ID が両 ranking 上位にいるとき, fitness 側を優先し novelty 側は他へ."""
    selector = MultiObjectiveSelector(n_fitness=2, m_novelty=2)
    # a, b が fitness top-2, novelty 上位も a, c
    fitness = {"a": 0.9, "b": 0.8, "c": 0.5, "d": 0.4, "e": 0.3}
    novelty = {"a": 0.99, "c": 0.88, "d": 0.77, "b": 0.66, "e": 0.55}
    result = selector.select(fitness, novelty)
    # fitness top-2: [a, b]
    # novelty ranking (除外 a, b 後): c, d, e → top 2 → [c, d]
    assert result == ["a", "b", "c", "d"]
    assert len(set(result)) == len(result)  # 重複なし


def test_selector_n_fitness_zero() -> None:
    """n_fitness=0 → novelty top のみ返る."""
    selector = MultiObjectiveSelector(n_fitness=0, m_novelty=3)
    fitness = {"a": 0.9, "b": 0.8, "c": 0.1}
    novelty = {"a": 0.1, "b": 0.5, "c": 0.99}
    result = selector.select(fitness, novelty)
    # novelty 降順: c, b, a
    assert result == ["c", "b", "a"]


def test_selector_m_novelty_zero() -> None:
    """m_novelty=0 → fitness top のみ返る."""
    selector = MultiObjectiveSelector(n_fitness=2, m_novelty=0)
    fitness = {"a": 0.9, "b": 0.8, "c": 0.1}
    novelty = {"a": 0.1, "b": 0.5, "c": 0.99}
    result = selector.select(fitness, novelty)
    assert result == ["a", "b"]


def test_selector_both_zero() -> None:
    """n_fitness=0 + m_novelty=0 → 空 list."""
    selector = MultiObjectiveSelector(n_fitness=0, m_novelty=0)
    assert selector.select({"a": 1.0}, {"a": 1.0}) == []


def test_selector_empty_scores() -> None:
    selector = MultiObjectiveSelector(n_fitness=3, m_novelty=3)
    assert selector.select({}, {}) == []


def test_selector_negative_args_rejected() -> None:
    with pytest.raises(ValueError, match="n_fitness must be >= 0"):
        MultiObjectiveSelector(n_fitness=-1, m_novelty=2)
    with pytest.raises(ValueError, match="m_novelty must be >= 0"):
        MultiObjectiveSelector(n_fitness=2, m_novelty=-1)


def test_selector_tie_break_id_ascending() -> None:
    """同 fitness で tie → ID 昇順 (決定論的)."""
    selector = MultiObjectiveSelector(n_fitness=2, m_novelty=0)
    fitness = {"c": 1.0, "a": 1.0, "b": 1.0}
    novelty = {"a": 0.0, "b": 0.0, "c": 0.0}
    result = selector.select(fitness, novelty)
    assert result == ["a", "b"]


def test_selector_default_ratio_06_04_realistic() -> None:
    """要件 §B-1 デフォルト N:M = 0.6:0.4 (人口 10 → N=6, M=4) を模擬."""
    selector = MultiObjectiveSelector(n_fitness=6, m_novelty=4)
    fitness = {f"ind-{i:02d}": float(10 - i) for i in range(10)}
    # novelty を逆順に: 末尾 ID ほど novel
    novelty = {f"ind-{i:02d}": float(i) for i in range(10)}
    result = selector.select(fitness, novelty)
    # fitness top 6: ind-00..ind-05
    assert result[:6] == [f"ind-{i:02d}" for i in range(6)]
    # novelty top (excl 上記): ind-09, ind-08, ind-07, ind-06
    assert result[6:] == ["ind-09", "ind-08", "ind-07", "ind-06"]


# ---------------------------------------------------------------------------
# 4. End-to-end pipeline test (compute_novelty_scores → MultiObjectiveSelector)
# ---------------------------------------------------------------------------


def test_pipeline_compute_then_select() -> None:
    """novelty 計算 → multi-objective selection の連携を確認."""
    descs = [
        (f"ind-{i}", NoveltyDescriptor(embedding=(float(i),)))
        for i in range(10)
    ]
    novelty_scores = compute_novelty_scores(descs, k=3)
    fitness = {f"ind-{i}": float(10 - i) for i in range(10)}  # 0 が最強
    novelty_map = {s.individual_id: s.score for s in novelty_scores}

    selector = MultiObjectiveSelector(n_fitness=3, m_novelty=2)
    selected = selector.select(fitness, novelty_map)

    assert len(selected) == 5
    # 先頭 3 は fitness top → ind-0, ind-1, ind-2
    assert selected[:3] == ["ind-0", "ind-1", "ind-2"]
    # novelty top の 2 個は ind-0/1/2 を除外した中で max → 端の ind-9 が novel
    # (1D grid の端は内側より平均距離が大きい)
    assert "ind-9" in selected[3:]


# ---------------------------------------------------------------------------
# 5. Scalability — N=100 でも妥当な時間で終わる
# ---------------------------------------------------------------------------


def test_compute_novelty_n100_completes_within_reasonable_time() -> None:
    """timing not strict — O(N^2) でも N=100 なら sub-second."""
    descs = [
        (
            f"ind-{i:03d}",
            NoveltyDescriptor(
                embedding=(
                    float(i),
                    float(i * 2),
                    math.sin(i),
                    math.cos(i),
                )
            ),
        )
        for i in range(100)
    ]
    t0 = time.perf_counter()
    scores = compute_novelty_scores(descs, k=15)
    elapsed = time.perf_counter() - t0
    assert len(scores) == 100
    # 緩めの上限. CI/低スペック環境でも余裕
    assert elapsed < 5.0
    # 全 score が非負
    assert all(s.score >= 0.0 for s in scores)
    # 全 k は 15
    assert all(s.k == 15 for s in scores)
