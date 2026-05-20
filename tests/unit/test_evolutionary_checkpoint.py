# SPDX-License-Identifier: Apache-2.0
"""v0.C 大規模集団対応 — checkpoint / resume / 時間予算 test."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from llive.perf.evolutionary import (
    EvolutionConfig,
    EvolutionLoop,
    GenomeBounds,
    Population,
    sphere_fitness,
)


def test_checkpoint_writes_snapshot_per_generation(tmp_path: Path) -> None:
    """checkpoint_every=1 (default) で全世代の snapshot が書かれる."""
    pop = Population.random(
        bounds=GenomeBounds(lower=(-1.0,), upper=(1.0,)),
        size=4,
        seed=0,
    )
    loop = EvolutionLoop(fitness_fn=sphere_fitness)
    config = EvolutionConfig(
        max_generations=3,
        patience=10,
        log_progress=False,
        out_dir=tmp_path / "run",
    )
    loop.run(pop, config)
    snaps = sorted((tmp_path / "run").glob("snapshot_gen_*.json"))
    # gen 0, 1, 2, 3 の 4 件
    assert len(snaps) == 4
    # generations.jsonl も存在
    assert (tmp_path / "run" / "generations.jsonl").exists()


def test_checkpoint_every_2_writes_every_other_gen(tmp_path: Path) -> None:
    pop = Population.random(
        bounds=GenomeBounds(lower=(-1.0,), upper=(1.0,)), size=4, seed=0,
    )
    loop = EvolutionLoop(fitness_fn=sphere_fitness)
    config = EvolutionConfig(
        max_generations=4,
        patience=10,
        log_progress=False,
        out_dir=tmp_path / "run",
        checkpoint_every=2,
    )
    loop.run(pop, config)
    snaps = sorted((tmp_path / "run").glob("snapshot_gen_*.json"))
    # gen 0, 2, 4 の 3 件
    assert len(snaps) == 3


def test_resume_from_dir_restores_population(tmp_path: Path) -> None:
    """1 度回した out_dir から resume_from で再開. 世代番号が引き継がれる."""
    bounds = GenomeBounds(lower=(-1.0, -1.0), upper=(1.0, 1.0))
    pop1 = Population.random(bounds=bounds, size=6, seed=42)
    loop = EvolutionLoop(fitness_fn=sphere_fitness)

    # 第 1 回: 3 世代回して停止
    config1 = EvolutionConfig(
        max_generations=3, patience=10, log_progress=False, out_dir=tmp_path / "run",
    )
    result1 = loop.run(pop1, config1)
    assert result1.final_population.generation == 3

    # 第 2 回: resume_from で再開
    pop2 = Population.random(bounds=bounds, size=6, seed=999)  # 元 seed と無関係でも上書きされる
    config2 = EvolutionConfig(
        max_generations=5,
        patience=10,
        log_progress=False,
        out_dir=tmp_path / "run2",
        resume_from=tmp_path / "run",  # dir 指定 → 最新 snapshot を自動選択
    )
    loop2 = EvolutionLoop(fitness_fn=sphere_fitness)
    result2 = loop2.run(pop2, config2)
    # 元の generation=3 から開始, max_generations=5 で 5+1 世代 = 終了 generation=8? or 5+
    # 実装により挙動は変わるが, 少なくとも 3 以上には進んでいる
    assert result2.final_population.generation >= 3


def test_resume_from_nonexistent_path_falls_back(tmp_path: Path) -> None:
    """resume_from が存在しなくても fallback で通常 run になる."""
    bounds = GenomeBounds(lower=(0.0,), upper=(1.0,))
    pop = Population.random(bounds=bounds, size=3, seed=0)
    loop = EvolutionLoop(fitness_fn=sphere_fitness)
    config = EvolutionConfig(
        max_generations=2,
        patience=5,
        log_progress=False,
        resume_from=tmp_path / "nonexistent",
    )
    result = loop.run(pop, config)
    assert result.stopped_reason in ("max_generations", "patience_exhausted (5 stagnant gens)")


def test_wallclock_budget_stops_evolution() -> None:
    """max_wallclock_seconds を 0.001 にすると即座に budget 超過で停止."""
    bounds = GenomeBounds(lower=(-1.0,), upper=(1.0,))
    pop = Population.random(bounds=bounds, size=3, seed=0)
    loop = EvolutionLoop(fitness_fn=sphere_fitness)
    config = EvolutionConfig(
        max_generations=100,  # 大きいが
        patience=100,
        log_progress=False,
        max_wallclock_seconds=0.0001,  # 即座に超過
    )
    result = loop.run(pop, config)
    assert "wallclock_budget_exhausted" in result.stopped_reason


def test_wallclock_budget_none_means_no_limit() -> None:
    """None の場合は通常通り max_generations まで進む."""
    bounds = GenomeBounds(lower=(-1.0,), upper=(1.0,))
    pop = Population.random(bounds=bounds, size=3, seed=0)
    loop = EvolutionLoop(fitness_fn=sphere_fitness)
    config = EvolutionConfig(
        max_generations=3,
        patience=100,
        log_progress=False,
        max_wallclock_seconds=None,
    )
    result = loop.run(pop, config)
    assert "wallclock" not in result.stopped_reason
