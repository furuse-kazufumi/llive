# SPDX-License-Identifier: Apache-2.0
"""COG-MESH-02 factory テスト — default_embedding_similarity()."""

from __future__ import annotations

from llive.cognitive_mesh.embedding_similarity import (
    EmbeddingSimilarityFn,
    default_embedding_similarity,
)
from llive.cognitive_mesh.title_recall import (
    RecallStatus,
    TitleRecallPlanner,
)


def test_default_factory_returns_embedding_similarity_fn() -> None:
    sim = default_embedding_similarity()
    assert isinstance(sim, EmbeddingSimilarityFn)
    # encoder は MemoryEncoder
    assert hasattr(sim.encoder, "encode")


def test_default_factory_returns_callable_in_unit_range() -> None:
    sim = default_embedding_similarity()
    # 完全一致テキストは類似度 1.0 (hash fallback でも MemoryEncoder で固定)
    score = sim("hello world", "hello world")
    assert 0.0 <= score <= 1.0
    assert score > 0.5  # 同一テキストなら最低でも 0.5


def test_default_factory_integrates_with_title_recall() -> None:
    """factory で作った sim_fn を TitleRecallPlanner に注入し、
    token match だけでは recovered にならないペアも score がつくこと."""
    sim = default_embedding_similarity()
    planner = TitleRecallPlanner(similarity_fn=sim)
    planner.setup(text="ベンチ品質", tag="t1")
    # token match では recover しない (token 共有なし)
    # similarity_fn 経由で何かしらの score が得られる (hash fallback でも)
    report = planner.evaluate("品質ベンチ完了")
    # similarity_fn が動いている = recovered_weight > 0 or
    # similar 範囲内で評価される (正の数)
    assert report.total_weight == 1.0
    # status は recover/miss どちらでもよい、重要なのは sim_fn が
    # exception で落ちないこと
    assert planner.all_foreshadows()[0].status in (
        RecallStatus.RECOVERED, RecallStatus.MISSED,
    )


def test_default_factory_independent_instances() -> None:
    """factory を 2 回呼ぶと別 instance が返る (state 干渉しない)."""
    sim1 = default_embedding_similarity()
    sim2 = default_embedding_similarity()
    assert sim1 is not sim2
    assert sim1.encoder is not sim2.encoder
