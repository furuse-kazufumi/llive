# SPDX-License-Identifier: Apache-2.0
"""lineage (LV-10 系統樹) — 単体テスト."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from llive.perf.evolutionary import (
    EvolutionConfig,
    EvolutionLoop,
    FitnessReport,
    Genome,
    GenomeBounds,
    Individual,
    Population,
    sphere_fitness,
)
from llive.perf.evolutionary.lineage import (
    Winner,
    _node_id,
    load_winners_jsonl,
    render_lineage_mermaid,
    write_lineage_mermaid_file,
    write_winners_jsonl,
)


def test_winner_serialize_roundtrip() -> None:
    w = Winner(generation=3, individual_id="abc123def", parent_ids=("p1", "p2"), score=0.85, rank=0)
    w2 = Winner.from_dict(w.to_dict())
    assert w2.generation == 3
    assert w2.individual_id == "abc123def"
    assert w2.parent_ids == ("p1", "p2")
    assert w2.score == 0.85
    assert w2.rank == 0


def test_write_and_load_winners_jsonl(tmp_path: Path) -> None:
    bounds = GenomeBounds(lower=(-1.0,), upper=(1.0,))
    pop = Population.random(bounds=bounds, size=5, seed=0)
    for i, ind in enumerate(pop.individuals):
        ind.record_fitness(FitnessReport(score=float(i)))

    jsonl_path = tmp_path / "winners.jsonl"
    n = write_winners_jsonl(jsonl_path, pop, top_n=3)
    assert n == 3
    winners = load_winners_jsonl(jsonl_path)
    assert len(winners) == 3
    # 上位順 (4.0, 3.0, 2.0)
    assert [w.score for w in winners] == [4.0, 3.0, 2.0]
    assert winners[0].rank == 0


def test_load_winners_jsonl_handles_missing(tmp_path: Path) -> None:
    assert load_winners_jsonl(tmp_path / "nope.jsonl") == []


def test_render_lineage_mermaid_basic() -> None:
    winners = [
        Winner(generation=0, individual_id="a1234567", parent_ids=(), score=0.5, rank=0),
        Winner(generation=0, individual_id="b1234567", parent_ids=(), score=0.4, rank=1),
        Winner(generation=1, individual_id="c1234567", parent_ids=("a1234567", "b1234567"),
               score=0.7, rank=0),
    ]
    md = render_lineage_mermaid(winners, highlight_top_rank=0, title="test lineage")
    assert "%% test lineage" in md
    assert "graph TD" in md
    assert "gen 0 #0" in md
    assert "gen 1 #0" in md
    # parent → child の edge
    assert "g0_a1234567" in md and "g1_c1234567" in md
    assert "g0_a1234567 --> g1_c1234567" in md
    # winner class definition
    assert "classDef winner" in md


def test_render_lineage_mermaid_ghost_parents() -> None:
    """親が winners に居ない場合は ghost node が生成される."""
    winners = [
        Winner(generation=2, individual_id="z1234567", parent_ids=("x1234567",), score=0.8, rank=0),
    ]
    md = render_lineage_mermaid(winners)
    assert "gh1_x1234567" in md  # parent's generation = 2 - 1 = 1
    assert "gh1_x1234567 --> g2_z1234567" in md


def test_render_lineage_mermaid_empty() -> None:
    md = render_lineage_mermaid([])
    assert "empty[No winners recorded]" in md


def test_write_lineage_mermaid_file(tmp_path: Path) -> None:
    winners = [
        Winner(generation=0, individual_id="a", parent_ids=(), score=0.5, rank=0),
    ]
    out = tmp_path / "lineage.mmd"
    write_lineage_mermaid_file(out, winners, title="test")
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "graph TD" in content


def test_winners_jsonl_integrates_with_real_ga(tmp_path: Path) -> None:
    """実 GA loop を 3 世代回しつつ世代ごとに winners.jsonl に追記."""
    bounds = GenomeBounds(lower=(-2.0, -2.0), upper=(2.0, 2.0))
    pop = Population.random(bounds=bounds, size=10, seed=42)
    loop = EvolutionLoop(fitness_fn=sphere_fitness)
    config = EvolutionConfig(max_generations=3, patience=10, log_progress=False)

    jsonl_path = tmp_path / "winners.jsonl"
    # 各世代の評価後に winners を書く (manual loop ではなく run 後の history で書く)
    result = loop.run(pop, config)
    # population は最終世代のもの. winners は run 終了時点で 1 世代分のみ書ける.
    # (将来 EvolutionLoop に hook を入れて世代ごとに書けるようにする)
    write_winners_jsonl(jsonl_path, result.final_population, top_n=2)
    winners = load_winners_jsonl(jsonl_path)
    assert len(winners) == 2
    # Mermaid 化
    md = render_lineage_mermaid(winners)
    assert "graph TD" in md
