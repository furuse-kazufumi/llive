# SPDX-License-Identifier: Apache-2.0
"""Smoke tests for scripts/evolution_dashboard.py.

dashboard が demo_island_evolution の JSONL を欠落なく読めて, plain text
レンダリングが落ちないことを確認する.
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
import evolution_dashboard as ed  # noqa: E402


def _generate_run(tmp_path: Path) -> dict:
    cfg = die.IslandConfig(
        n_islands=3,
        island_size=4,
        migration_interval=2,
        migration_size=1,
        topology="ring",
        migration_policy="best",
        max_generations=4,
        max_workers=1,
        out_dir=tmp_path,
        seed=99,
    )
    return die.run_island_evolution(cfg, problem="sphere")


def test_dashboard_loads_jsonl(tmp_path: Path) -> None:
    _generate_run(tmp_path)
    islands_data = ed._load_island_jsonl(tmp_path)
    migrations = ed._load_migrations(tmp_path)
    summary = ed._load_summary(tmp_path)

    assert len(islands_data) == 3
    for idx in (0, 1, 2):
        assert idx in islands_data
        assert len(islands_data[idx]) == 4

    assert isinstance(migrations, list)
    assert summary is not None
    assert summary["n_islands"] == 3


def test_dashboard_plain_render(tmp_path: Path) -> None:
    _generate_run(tmp_path)
    text = ed._render_plain(tmp_path)
    assert "Island Portfolio" in text
    assert "island  0" in text
    assert "island  2" in text
    assert "effective_pop" in text


def test_dashboard_sparkline_handles_edge_cases() -> None:
    assert ed._sparkline([]) == ""
    spark = ed._sparkline([1.0, 2.0, 3.0, 4.0])
    assert len(spark) == 4
    flat = ed._sparkline([2.5, 2.5, 2.5])
    assert len(flat) == 3
    long = ed._sparkline(list(range(100)), width=10)
    assert len(long) == 10


def test_dashboard_handles_missing_dir(tmp_path: Path) -> None:
    missing = tmp_path / "nonexistent"
    assert ed._load_summary(missing) is None
    assert ed._load_manifest(missing) is None
    assert ed._load_migrations(missing) == []
    assert ed._load_island_jsonl(missing) == {}


def test_dashboard_progress_completed(tmp_path: Path) -> None:
    _generate_run(tmp_path)
    islands_data = ed._load_island_jsonl(tmp_path)
    summary = ed._load_summary(tmp_path)
    manifest = ed._load_manifest(tmp_path)
    progress = ed._compute_progress(islands_data, manifest, summary)
    assert progress["status"] == "completed"
    assert progress["max_gen"] == 4
    assert progress["current_gen"] == 4
    assert progress["progress_ratio"] == 1.0


def test_dashboard_progress_running(tmp_path: Path) -> None:
    """manifest だけあって summary がない (実行中) 状態の進捗率."""
    manifest = {
        "started_at_epoch": 0.0,
        "problem": "sphere",
        "n_islands": 2,
        "island_size": 4,
        "migration_interval": 2,
        "migration_size": 1,
        "topology": "ring",
        "migration_policy": "best",
        "max_generations": 10,
        "max_workers": 1,
        "seed": 1,
    }
    islands_data = {
        0: [{"wall_gen": i, "best_score": -i, "diversity_l2": 1.0, "generation": i, "n_individuals": 4} for i in range(3)],
        1: [{"wall_gen": i, "best_score": -i, "diversity_l2": 1.0, "generation": i, "n_individuals": 4} for i in range(3)],
    }
    progress = ed._compute_progress(islands_data, manifest, summary=None)
    assert progress["status"] == "running"
    assert progress["current_gen"] == 3
    assert progress["max_gen"] == 10
    assert 0.25 < progress["progress_ratio"] < 0.35


def test_dashboard_progress_idle() -> None:
    progress = ed._compute_progress({}, manifest=None, summary=None)
    assert progress["status"] == "idle"
    assert progress["current_gen"] == 0


def test_ascii_progress_bar_clamp() -> None:
    assert len(ed._ascii_progress_bar(0.0)) == ed._PROGRESS_BAR_WIDTH
    assert len(ed._ascii_progress_bar(1.0)) == ed._PROGRESS_BAR_WIDTH
    assert ed._ascii_progress_bar(0.0).count("█") == 0
    assert ed._ascii_progress_bar(1.0).count("░") == 0
    assert "█" in ed._ascii_progress_bar(0.5)
    assert "░" in ed._ascii_progress_bar(0.5)
    # clamp out-of-range
    assert len(ed._ascii_progress_bar(-1.0)) == ed._PROGRESS_BAR_WIDTH
    assert len(ed._ascii_progress_bar(2.0)) == ed._PROGRESS_BAR_WIDTH
