# SPDX-License-Identifier: Apache-2.0
"""Smoke tests for scripts/demo_genome3d_evolution.py.

Genome3D 4 階建てが破壊なく進化ループに乗ることを smoke で確認.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from llive.perf.evolutionary import Genome3D
from llive.perf.evolutionary.impl_chromosome import ImplChromosome
from llive.perf.evolutionary.meta_chromosome import MetaChromosome
from llive.perf.evolutionary.prompt_chromosome import PromptChromosome
from llive.perf.evolutionary.thought_factor_per_layer import (
    ThoughtFactorPerLayerChromosome,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import demo_genome3d_evolution as dge  # noqa: E402


# ---------------------------------------------------------------------------
# fitness 関数 unit
# ---------------------------------------------------------------------------


def _make_at_target(target: float) -> Genome3D:
    return Genome3D(
        c_impl=ImplChromosome.default(),
        c_prompt=PromptChromosome.default(),
        c_meta=MetaChromosome.default(),
        c_factors=ThoughtFactorPerLayerChromosome.from_array(
            np.full((10, 4), target)
        ),
    )


def test_fitness_at_target_is_zero() -> None:
    g = _make_at_target(0.7)
    assert abs(dge.fitness_c_factors_target(g, 0.7)) < 1e-9


def test_fitness_far_is_strongly_negative() -> None:
    g = _make_at_target(0.0)
    score = dge.fitness_c_factors_target(g, 0.7)
    # 距離 sqrt(40 * 0.49) ≒ 4.427
    assert -4.5 < score < -4.4


def test_fitness_is_monotone_in_distance() -> None:
    near = _make_at_target(0.65)
    far = _make_at_target(0.30)
    assert dge.fitness_c_factors_target(near, 0.7) > dge.fitness_c_factors_target(
        far, 0.7
    )


# ---------------------------------------------------------------------------
# initial_population
# ---------------------------------------------------------------------------


def test_initial_population_size_and_diversity() -> None:
    rng = np.random.default_rng(42)
    pop = dge.initial_population(rng, 8)
    assert len(pop) == 8
    # 全員 Genome3D
    for g in pop:
        assert isinstance(g, Genome3D)
    # c_factors が random なので異なるはず
    arrs = [g.c_factors.as_array() for g in pop]
    diff = arrs[0] - arrs[1]
    assert np.any(diff != 0.0)


# ---------------------------------------------------------------------------
# end-to-end smoke
# ---------------------------------------------------------------------------


def test_smoke_intra_crossover_improves(tmp_path: Path) -> None:
    """intra_layer_crossover で 5 世代回すと best が初期より良くなる (elitism 込み)."""
    cfg = dge.Genome3DConfig(
        size=12,
        max_generations=6,
        target_value=0.7,
        crossover_kind="intra",
        elite_top=2,
        tournament_k=3,
        mutation_step=0.15,
        out_dir=tmp_path,
        seed=42,
    )
    summary = dge.run_genome3d_evolution(cfg)
    assert summary["n_islands"] == 1
    assert summary["effective_pop"] == 12
    assert summary["max_generations"] == 6

    jsonl = tmp_path / "island_00" / "generations.jsonl"
    assert jsonl.exists()
    rows = [
        json.loads(line)
        for line in jsonl.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 6
    # elitism で最低でも best は monotonically non-decreasing
    bests = [r["best_score"] for r in rows]
    for i in range(1, len(bests)):
        assert bests[i] >= bests[i - 1] - 1e-9, (
            f"best decreased at gen {i}: {bests[i - 1]:.4f} -> {bests[i]:.4f}"
        )

    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "manifest.json").exists()


def test_smoke_cross_layer_crossover(tmp_path: Path) -> None:
    cfg = dge.Genome3DConfig(
        size=8,
        max_generations=3,
        target_value=0.5,
        crossover_kind="cross",
        elite_top=2,
        tournament_k=3,
        mutation_step=0.1,
        out_dir=tmp_path,
        seed=7,
    )
    summary = dge.run_genome3d_evolution(cfg)
    assert summary["crossover_kind"] == "cross"
    # cross 経路でも crash しない + JSONL 出力
    assert (tmp_path / "island_00" / "generations.jsonl").exists()


def test_manifest_dashboard_compatible(tmp_path: Path) -> None:
    """manifest.json が dashboard が期待する key を持つことを確認."""
    cfg = dge.Genome3DConfig(
        size=4,
        max_generations=2,
        target_value=0.5,
        crossover_kind="intra",
        elite_top=1,
        tournament_k=2,
        mutation_step=0.1,
        out_dir=tmp_path,
        seed=1,
    )
    dge.run_genome3d_evolution(cfg)
    manifest = json.loads(
        (tmp_path / "manifest.json").read_text(encoding="utf-8")
    )
    # dashboard が読む必須 key
    for key in (
        "started_at_epoch",
        "problem",
        "n_islands",
        "island_size",
        "max_generations",
    ):
        assert key in manifest


def test_diversity_decreases_with_evolution(tmp_path: Path) -> None:
    """進化が進むと diversity_l2 が単調または傾向として減少することを確認.

    elitism + selection pressure で集団が target 付近に収束する → 多様性は減る.
    厳密な単調減少は保証されないので, 初回と最終を比較する.
    """
    cfg = dge.Genome3DConfig(
        size=16,
        max_generations=10,
        target_value=0.7,
        crossover_kind="intra",
        elite_top=2,
        tournament_k=3,
        mutation_step=0.05,  # mutation を抑えて収束を促進
        out_dir=tmp_path,
        seed=42,
    )
    dge.run_genome3d_evolution(cfg)
    rows = [
        json.loads(line)
        for line in (tmp_path / "island_00" / "generations.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    initial_diversity = rows[0]["diversity_l2"]
    final_diversity = rows[-1]["diversity_l2"]
    # 多様性は減るはず (mutation_step=0.05 で elitism あれば確実)
    assert final_diversity < initial_diversity, (
        f"diversity did not decrease: {initial_diversity:.4f} -> "
        f"{final_diversity:.4f}"
    )
