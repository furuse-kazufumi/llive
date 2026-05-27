# SPDX-License-Identifier: Apache-2.0
"""Unit tests for scripts/poc_minimal_criterion_coevolution.py.

Minimal Criterion Coevolution (MCC; Brant & Stanley 2017 / POET-lite) toy の決定論的
verdict を固定。proxy・CPU・LLM/Docker ゼロ・llive import ゼロ (隔離 toy)。

命題: タスクと解法を共進化させ minimal criterion で回すと、固定タスク選択が陥る飽和
(能力 frontier が早期に天井で停滞) を回避し、frontier が非飽和に伸び続ける。
([[feedback_staged_poc_individual_structure]] / [[feedback_benchmark_honest_disclosure]])
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import poc_minimal_criterion_coevolution as mcc  # noqa: E402


# ---------------------------------------------------------------------------
# solve judgement: per-dim dominance
# ---------------------------------------------------------------------------
def test_solves_dominance_true_when_capability_dominates_every_dim():
    solver = np.array([0.5, 0.6, 0.7])
    task = np.array([0.4, 0.6, 0.1])  # 2nd dim is a tie (>= counts as solved)
    assert mcc.solves(solver, task) is True


def test_solves_dominance_false_when_any_dim_short():
    solver = np.array([0.5, 0.6, 0.7])
    task = np.array([0.4, 0.65, 0.1])  # 2nd dim: 0.6 < 0.65 -> not solved
    assert mcc.solves(solver, task) is False


def test_solve_matrix_matches_scalar_solves():
    rng = np.random.default_rng(0)
    solvers = rng.uniform(0, 1, (5, 4))
    tasks = rng.uniform(0, 1, (7, 4))
    sm = mcc.solve_matrix(solvers, tasks)
    assert sm.shape == (5, 7)
    for i in range(5):
        for j in range(7):
            assert bool(sm[i, j]) == mcc.solves(solvers[i], tasks[j])


# ---------------------------------------------------------------------------
# minimal-criterion band filter for tasks
# ---------------------------------------------------------------------------
def test_task_band_mask_keeps_only_in_band_counts():
    # solve_mat columns -> solver counts: [0, 1, 2, 3, 5]
    solve_mat = np.array(
        [
            [False, True, True, True, True],
            [False, False, True, True, True],
            [False, False, False, True, True],
            [False, False, False, False, True],
            [False, False, False, False, True],
        ]
    )
    counts = solve_mat.sum(axis=0)
    np.testing.assert_array_equal(counts, [0, 1, 2, 3, 5])
    mask = mcc.task_band_mask(solve_mat, lo=1, hi=3)
    # in-band counts (1,2,3) kept; too-hard (0) and too-easy (5) culled.
    np.testing.assert_array_equal(mask, [False, True, True, True, False])


def test_task_band_mask_edges_inclusive():
    solve_mat = np.array([[True], [True], [False]])  # count = 2
    assert mcc.task_band_mask(solve_mat, lo=2, hi=2).tolist() == [True]
    assert mcc.task_band_mask(solve_mat, lo=3, hi=4).tolist() == [False]


# ---------------------------------------------------------------------------
# frontier metric: unbounded, fair, monotone in capability
# ---------------------------------------------------------------------------
def test_capability_frontier_is_top_k_mean_of_min_dim():
    # 3 solvers, min-dim caps = [0.2, 0.5, 0.9]; top_k=2 -> mean(0.5,0.9)=0.7
    solvers = np.array([[0.2, 0.8, 0.3], [0.5, 0.6, 0.9], [0.9, 0.95, 0.99]])
    assert abs(mcc.capability_frontier(solvers, top_k=2) - 0.7) < 1e-9
    # top_k larger than pop clamps to pop size.
    assert abs(mcc.capability_frontier(solvers, top_k=10)
               - np.mean([0.2, 0.5, 0.9])) < 1e-9


def test_capability_frontier_unbounded_and_monotone():
    base = np.full((8, 4), 0.5)
    hi = np.full((8, 4), 5.0)  # capabilities far above any [0,1] battery -> frontier > 1
    assert mcc.capability_frontier(hi) > mcc.capability_frontier(base)
    assert mcc.capability_frontier(hi) > 1.0  # not capped at any probe ceiling


# ---------------------------------------------------------------------------
# task coevolution raises difficulty in step with the climbing frontier
# (auto-curriculum) — falsifiable mechanism check
# ---------------------------------------------------------------------------
def test_mcc_task_difficulty_tracks_climbing_frontier():
    out = mcc.run(gens=300, seed=0)
    fr = np.asarray(out["mcc"]["frontier"], dtype=float)
    tmd = np.asarray(out["mcc"]["task_mean_diff"], dtype=float)
    # frontier climbs over the run.
    assert fr[-1] > fr[0]
    # task mean difficulty climbs too (curriculum follows the frontier upward).
    assert tmd[-1] > tmd[0]
    # and rises substantially (not a marginal wobble): final >> initial.
    assert tmd[-1] > 3.0 * tmd[0]


def test_mcc_frontier_climbs_far_above_fixed_battery():
    out = mcc.run(gens=300, seed=0)
    v = out["verdict"]
    # MCC frontier broke well past the static battery scale.
    assert v["mcc_tail_frontier"] > 3.0 * v["battery_ceiling"]
    # fixed frontier stayed bounded near the battery scale (informational confinement).
    assert v["fixed_confined_to_battery"] is True


# ---------------------------------------------------------------------------
# deterministic verdict: MCC diverges from (saturated) fixed-task selection
# ---------------------------------------------------------------------------
def test_verdict_mcc_avoids_saturation_seed0():
    out = mcc.run(gens=300, seed=0)
    v = out["verdict"]
    # MCC tail frontier exceeds the fixed-task tail frontier by the divergence margin.
    assert v["mcc_tail_frontier"] > v["fixed_tail_frontier"]
    assert v["mcc_over_fixed_ratio"] >= 2.0
    assert v["mcc_diverges"] is True
    assert v["mcc_broke_ceiling"] is True
    # the headline deterministic verdict.
    assert v["mcc_avoids_saturation"] is True


def test_verdict_is_deterministic_for_fixed_seed():
    a = mcc.run(gens=200, seed=1)["verdict"]
    b = mcc.run(gens=200, seed=1)["verdict"]
    assert a == b  # same seed -> identical verdict dict


def test_output_schema_and_honest_notes_present():
    out = mcc.run(gens=120, seed=0)
    assert out["schema"] == "poc_minimal_criterion_coevolution/v1"
    assert "proposition" in out and out["proposition"]
    # honest disclosure: notes must mention the proxy/llive-isolation caveat.
    notes = " ".join(out["honest_notes"])
    assert "proxy" in notes.lower()
    assert "llive" in notes.lower()
    # the verdict carries the falsifiable boolean.
    assert "mcc_avoids_saturation" in out["verdict"]


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
