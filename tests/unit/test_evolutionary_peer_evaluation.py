# SPDX-License-Identifier: Apache-2.0
"""PeerEvaluationMatrix + PeerFitnessAdapter (v0.E CE-01) — unit tests."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from llive.perf.evolutionary import (
    ElitismSelection,
    EvolutionConfig,
    EvolutionLoop,
    FitnessReport,
    GaussianMutation,
    Genome,
    GenomeBounds,
    Individual,
    PeerEvaluationMatrix,
    PeerFitnessAdapter,
    Population,
    TournamentSelection,
    UniformCrossover,
)


# ---------------------------------------------------------------------------
# 1. Matrix basic
# ---------------------------------------------------------------------------


def test_empty_matrix_shape() -> None:
    m = PeerEvaluationMatrix.empty(["a", "b", "c"])
    assert m.matrix.shape == (3, 3)
    assert np.isnan(m.matrix).all()


def test_init_rejects_shape_mismatch() -> None:
    with pytest.raises(ValueError, match="matrix shape"):
        PeerEvaluationMatrix(
            agent_ids=("a", "b"),
            matrix=np.zeros((3, 3)),
        )


def test_record_and_column_mean() -> None:
    m = PeerEvaluationMatrix.empty(["a", "b", "c"])
    # a が b を 0.8, a が c を 0.6
    m.record("a", "b", 0.8)
    m.record("a", "c", 0.6)
    # b が a を 0.5, b が c を 0.7
    m.record("b", "a", 0.5)
    m.record("b", "c", 0.7)
    # c が a を 0.4, c が b を 0.9
    m.record("c", "a", 0.4)
    m.record("c", "b", 0.9)
    col_mean = m.column_mean()
    assert col_mean[0] == pytest.approx((0.5 + 0.4) / 2, abs=1e-6)  # a が受けた
    assert col_mean[1] == pytest.approx((0.8 + 0.9) / 2, abs=1e-6)  # b が受けた
    assert col_mean[2] == pytest.approx((0.6 + 0.7) / 2, abs=1e-6)  # c が受けた


def test_row_mean_excludes_self() -> None:
    m = PeerEvaluationMatrix.empty(["a", "b"])
    m.record("a", "b", 0.8)
    m.record("b", "a", 0.3)
    row_mean = m.row_mean()
    assert row_mean[0] == pytest.approx(0.8, abs=1e-6)
    assert row_mean[1] == pytest.approx(0.3, abs=1e-6)


# ---------------------------------------------------------------------------
# 2. to_fitness_reports
# ---------------------------------------------------------------------------


def test_to_fitness_reports_column_mean() -> None:
    m = PeerEvaluationMatrix.empty(["a", "b"])
    m.record("a", "b", 0.8)
    m.record("b", "a", 0.3)
    reports = m.to_fitness_reports(score_aggregator="column_mean")
    assert set(reports.keys()) == {"a", "b"}
    assert reports["a"].score == pytest.approx(0.3, abs=1e-6)
    assert reports["b"].score == pytest.approx(0.8, abs=1e-6)
    assert "peer_score" in reports["a"].breakdown


def test_to_fitness_reports_unknown_aggregator() -> None:
    m = PeerEvaluationMatrix.empty(["a"])
    with pytest.raises(ValueError, match="score_aggregator"):
        m.to_fitness_reports(score_aggregator="bogus")


# ---------------------------------------------------------------------------
# 3. Collusion detection
# ---------------------------------------------------------------------------


def test_collusion_score_normal() -> None:
    m = PeerEvaluationMatrix.empty(["a", "b", "c"])
    m.record("a", "b", 0.8)
    m.record("a", "c", 0.3)
    m.record("b", "a", 0.5)
    m.record("b", "c", 0.7)
    m.record("c", "a", 0.4)
    m.record("c", "b", 0.6)
    score = m.collusion_score()
    assert "score_variance" in score
    assert "symmetry" in score
    assert "concentration" in score
    # 通常分布なら variance > 0
    assert score["score_variance"] > 1e-3


def test_collusion_suspected_when_all_high_uniform() -> None:
    """全員が ほぼ同じ高得点を付けると共謀疑い."""
    m = PeerEvaluationMatrix.empty(["a", "b", "c"])
    for i in ("a", "b", "c"):
        for j in ("a", "b", "c"):
            if i != j:
                m.record(i, j, 0.95)  # 全員 0.95
    assert m.is_suspected_collusion(variance_threshold=1e-3)


# ---------------------------------------------------------------------------
# 4. Serialization
# ---------------------------------------------------------------------------


def test_to_dict_from_dict_roundtrip() -> None:
    m = PeerEvaluationMatrix.empty(["x", "y"], signed_by="judge1", generation=3)
    m.record("x", "y", 0.7)
    d = m.to_dict()
    m2 = PeerEvaluationMatrix.from_dict(d)
    assert m2.agent_ids == ("x", "y")
    assert m2.signed_by == "judge1"
    assert m2.generation == 3
    assert m2.matrix[0, 1] == pytest.approx(0.7)


def test_write_jsonl_append(tmp_path: Path) -> None:
    path = tmp_path / "peer.jsonl"
    m1 = PeerEvaluationMatrix.empty(["a", "b"], generation=0)
    m1.record("a", "b", 0.5)
    m1.write_jsonl(path)
    m2 = PeerEvaluationMatrix.empty(["a", "b"], generation=1)
    m2.record("a", "b", 0.7)
    m2.write_jsonl(path)
    lines = path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    d2 = json.loads(lines[1])
    assert d2["generation"] == 1


# ---------------------------------------------------------------------------
# 5. Mermaid render
# ---------------------------------------------------------------------------


def test_render_mermaid_contains_edges() -> None:
    m = PeerEvaluationMatrix.empty(["a", "b"])
    m.record("a", "b", 0.75)
    m.record("b", "a", 0.25)
    out = m.render_mermaid()
    assert "graph LR" in out
    assert "a --" in out
    assert "0.75" in out
    assert "b --" in out


def test_render_mermaid_top_k_edges() -> None:
    m = PeerEvaluationMatrix.empty(["a", "b", "c"])
    for i in ("a", "b", "c"):
        for j in ("a", "b", "c"):
            if i != j:
                m.record(i, j, 0.5 if i == "a" else 0.1)
    out = m.render_mermaid(top_k_edges=2)
    # top 2 edges should be a's outgoing (0.5)
    assert out.count("0.50") == 2 or out.count("0.5") >= 2


# ---------------------------------------------------------------------------
# 6. PeerFitnessAdapter — EvolutionLoop integration
# ---------------------------------------------------------------------------


def test_peer_fitness_adapter_end_to_end(tmp_path: Path) -> None:
    """4 個体集団を peer-based fitness で 3 世代回す."""
    bounds = GenomeBounds(lower=(0.0, 0.0), upper=(1.0, 1.0))
    rng = np.random.default_rng(0)
    inds = []
    for _ in range(4):
        vals = bounds.sample_uniform(rng)
        inds.append(
            Individual.from_genome(Genome.from_values(vals, bounds=bounds))
        )
    pop = Population(individuals=inds, bounds=bounds, seed=0)

    def pair_score(evaluator: Individual, target: Individual) -> float:
        # target の genome[0] が高いほど高得点 (evaluator の好み)
        return float(target.genome.values[0])

    jsonl_path = tmp_path / "peer_matrix.jsonl"
    adapter = PeerFitnessAdapter(
        pair_score_fn=pair_score,
        matrix_jsonl_path=jsonl_path,
        signed_by="testjudge",
    )

    def placeholder_fitness(genome: Genome) -> FitnessReport:
        return FitnessReport(score=0.0)

    loop = EvolutionLoop(
        fitness_fn=placeholder_fitness,
        selection=TournamentSelection(k=2),
        crossover=UniformCrossover(p=0.5),
        mutation=GaussianMutation(sigma=0.05, p=0.1),
        elitism=ElitismSelection(top_n=1),
        scheduler=adapter,
    )
    result = loop.run(pop, EvolutionConfig(max_generations=3, patience=99, log_progress=False))
    # 各世代で matrix を JSONL append したはず
    lines = jsonl_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) >= 3  # 評価回数 = 世代数 + 終端
    # 最終 best は genome[0] が高い (peer fitness 設定通り)
    final_best = result.final_population.best()
    assert final_best.genome.values[0] > 0.3


def test_peer_fitness_adapter_includes_self_optional() -> None:
    inds = []
    bounds = GenomeBounds(lower=(0.0,), upper=(1.0,))
    inds.append(Individual.from_genome(Genome.from_values((0.5,), bounds=bounds)))
    inds.append(Individual.from_genome(Genome.from_values((0.5,), bounds=bounds)))

    call_count = {"n": 0}

    def pair_score(evaluator, target):
        call_count["n"] += 1
        return 0.5

    # include_self=True → n*n = 4 calls
    adapter = PeerFitnessAdapter(pair_score_fn=pair_score, include_self=True)
    adapter(lambda g: FitnessReport(score=0.0), inds)
    assert call_count["n"] == 4

    # include_self=False (default) → n*(n-1) = 2 calls
    call_count["n"] = 0
    adapter2 = PeerFitnessAdapter(pair_score_fn=pair_score, include_self=False)
    adapter2(lambda g: FitnessReport(score=0.0), inds)
    assert call_count["n"] == 2
