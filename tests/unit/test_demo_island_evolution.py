# SPDX-License-Identifier: Apache-2.0
"""Smoke tests for scripts/demo_island_evolution.py.

Coarse-grained Parallel GA orchestrator が IslandModel + Population step を
組み合わせて期待通りに JSONL を吐くことを確認する.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import demo_island_evolution as die  # noqa: E402


def test_island_evolution_serial_smoke(tmp_path: Path) -> None:
    cfg = die.IslandConfig(
        n_islands=2,
        island_size=4,
        migration_interval=2,
        migration_size=1,
        topology="ring",
        migration_policy="best",
        max_generations=3,
        max_workers=1,
        out_dir=tmp_path,
        seed=42,
    )
    summary = die.run_island_evolution(cfg, problem="sphere")

    assert summary["n_islands"] == 2
    assert summary["max_generations"] == 3
    assert summary["global_best_score"] is not None
    assert summary["effective_pop"] >= 1

    for i in range(2):
        path = tmp_path / f"island_{i:02d}" / "generations.jsonl"
        assert path.exists(), f"missing {path}"
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(rows) == 3
        for r in rows:
            assert "best_score" in r
            assert "diversity_l2" in r
            assert "island_id" in r
            assert r["island_id"] == i

    assert (tmp_path / "summary.json").exists()
    mig_path = tmp_path / "migrations.jsonl"
    if mig_path.exists():
        mig_rows = [
            json.loads(line)
            for line in mig_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        for m in mig_rows:
            assert m["total_migrants"] >= 1
            assert "island_sizes" in m


def test_island_evolution_parallel_smoke(tmp_path: Path) -> None:
    cfg = die.IslandConfig(
        n_islands=3,
        island_size=4,
        migration_interval=10,
        migration_size=1,
        topology="ring",
        migration_policy="best",
        max_generations=2,
        max_workers=2,
        out_dir=tmp_path,
        seed=7,
    )
    summary = die.run_island_evolution(cfg, problem="sphere")
    assert summary["n_islands"] == 3
    assert summary["max_workers"] == 2
    for i in range(3):
        path = tmp_path / f"island_{i:02d}" / "generations.jsonl"
        assert path.exists()


def test_island_evolution_rosenbrock(tmp_path: Path) -> None:
    cfg = die.IslandConfig(
        n_islands=2,
        island_size=4,
        migration_interval=1,
        migration_size=1,
        topology="fully",
        migration_policy="best",
        max_generations=2,
        max_workers=1,
        out_dir=tmp_path,
        seed=123,
    )
    summary = die.run_island_evolution(cfg, problem="rosenbrock")
    assert summary["problem"] == "rosenbrock"
    assert summary["topology"] == "fully"
    mig_path = tmp_path / "migrations.jsonl"
    assert mig_path.exists()
