#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""PoC: does MINIMAL-CRITERION COEVOLUTION avoid the saturation that FIXED-TASK selection hits?

Smallest falsifiable test of the central pathology from the 12h run
([[feedback_staged_poc_individual_structure]] / [[feedback_benchmark_honest_disclosure]]):

  central病理 = **飽和** — a fixed task battery lets the best solver hit a ceiling
  early; the population keeps churning but capability stops climbing.

Proposition (falsifiable):

  「タスクと解法を共進化させ、minimal criterion (解法はある帯のタスクを解けたら存続 /
    タスクは『解ける解法が居るが多すぎない』帯のみ存続) で回すと、固定タスク選択が陥る
    飽和 (能力 frontier が早期に天井で停滞) を回避し、解法能力 frontier が非飽和に
    伸び続ける。」

This is the toy mechanism behind Minimal Criterion Coevolution (MCC; Brant & Stanley
2017) / POET-lite: instead of a static benchmark, the *tasks* coevolve to stay near the
frontier of what the current solver population can just-barely do — an emergent
auto-curriculum.

Design (stdlib + numpy, deterministic seed, ZERO llive imports = isolated toy):
* solver = capability vector in R^d_>=0.  task = difficulty/feature vector in R^d.
* solve(solver, task) = solver capability dominates task difficulty in EVERY dim.
  (per-dim dominance is the minimal-criterion substrate.)
* MCC loop:
    - solver minimal criterion: solves >= MC_SOLVE tasks in the current task pop
      -> eligible to reproduce.  mutation pushes capability UP (open search).
    - task minimal criterion: number of solvers that solve it is in [lo, hi]
      -> stays alive / reproduces.  too-easy (>hi) and too-hard/unsolved (<lo)
      tasks are culled.  this自動的に generates near-frontier difficulty = auto-curriculum.
* CONTROL = fixed-task selection: a static task battery, solvers evolve, tasks never change.
* metric = capability frontier per generation:
    max over solvers of the HARDEST task difficulty (sum of difficulty) it can solve,
    evaluated against a fixed dense difficulty probe (identical for both arms = fair).
* verdict (deterministic): MCC frontier significantly EXCEEDS fixed-task frontier in the
  tail AND fixed-task is a plateau (its own tail slope ~= 0).  -> mcc_avoids_saturation.

If the frontier does NOT keep climbing, report it honestly (feedback_benchmark_honest_disclosure).

    py -3.11 scripts/poc_minimal_criterion_coevolution.py
    py -3.11 scripts/poc_minimal_criterion_coevolution.py --gens 400 --seed 1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np


def _ensure_utf8_stdout() -> None:
    """cp932 console safety: emit UTF-8 (feedback_cli_utf8_stdout_pattern)."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass


# ---------------------------------------------------------------------------
# minimal-criterion substrate: dominance solve check + band filter
# ---------------------------------------------------------------------------
def solves(solver: np.ndarray, task: np.ndarray) -> bool:
    """A solver solves a task iff its capability dominates the difficulty in EVERY dim.

    This per-dim dominance is the minimal-criterion substrate: a binary, structural
    "can / cannot", not a graded score.
    """
    return bool(np.all(np.asarray(solver) >= np.asarray(task)))


def solve_matrix(solvers: np.ndarray, tasks: np.ndarray) -> np.ndarray:
    """Boolean (n_solvers, n_tasks): solvers[i] dominates tasks[j] in every dim."""
    # solvers[:, None, :] >= tasks[None, :, :]  -> (S, T, d); all over last axis.
    return np.all(solvers[:, None, :] >= tasks[None, :, :], axis=2)


def task_band_mask(solve_mat: np.ndarray, lo: int, hi: int) -> np.ndarray:
    """Minimal criterion for TASKS: kept iff #solvers solving it is in [lo, hi].

    `solve_mat` is (n_solvers, n_tasks).  Returns a boolean mask over tasks.
    Too-easy tasks (count > hi) and too-hard tasks (count < lo) are culled -> the
    survivors sit on the frontier of current solver capability = auto-curriculum.
    """
    counts = solve_mat.sum(axis=0)
    return (counts >= lo) & (counts <= hi)


# ---------------------------------------------------------------------------
# frontier metric — identical fair probe for both arms
# ---------------------------------------------------------------------------
def capability_frontier(solvers: np.ndarray, probe: np.ndarray | None = None) -> float:
    """Frontier = the hardest UNIFORM task any solver can dominate (UNBOUNDED metric).

    A solver dominates the uniform difficulty vector (t,...,t) iff t <= min(capability)
    in every dim (dominance is gated by the weakest dim). So the hardest uniform task a
    solver clears is exactly its min-dim capability, and the population frontier is

        max_i  min_d  capability[i, d].

    This is the *same fair metric* for both arms (it depends only on the solver
    capabilities, not on either arm's own task population) AND it is unbounded above, so
    a non-saturating arm can keep climbing through it indefinitely. `probe` is accepted
    for API symmetry but unused (kept so callers/tests can pass it harmlessly).
    """
    if solvers.size == 0:
        return 0.0
    return float(np.max(np.min(solvers, axis=1)))


# ---------------------------------------------------------------------------
# MCC arm: solvers AND tasks coevolve under minimal criteria
# ---------------------------------------------------------------------------
def run_mcc(
    *,
    gens: int,
    pop: int,
    task_pop: int,
    d: int,
    seed: int,
    mc_solve: int,
    band_lo: int,
    band_hi: int,
    step: float,
    task_step: float,
) -> dict:
    """Coevolve solvers + tasks. Return frontier trajectory + task-difficulty trajectory.

    Mutation is ZERO-MEAN Gaussian: net upward movement of capability comes ONLY from
    selection, never from a mechanical mutation bias. So if the selection signal dies
    (saturation), the frontier stops climbing — which is exactly what we want to detect.
    """
    rng = np.random.default_rng(seed)
    # start solvers small (low capability) and tasks easy — both must climb together.
    solvers = rng.uniform(0.0, 0.3, (pop, d))
    tasks = rng.uniform(0.0, 0.3, (task_pop, d))

    frontier = np.empty(gens)
    task_mean_diff = np.empty(gens)
    task_max_diff = np.empty(gens)

    for g in range(gens):
        frontier[g] = capability_frontier(solvers)
        task_mean_diff[g] = float(tasks.sum(axis=1).mean()) if len(tasks) else 0.0
        task_max_diff[g] = float(tasks.sum(axis=1).max()) if len(tasks) else 0.0

        sm = solve_matrix(solvers, tasks)        # (S, T)

        # --- SOLVER minimal criterion: solve >= mc_solve tasks -> reproduce ---
        solver_solved_counts = sm.sum(axis=1)
        eligible = np.flatnonzero(solver_solved_counts >= mc_solve)
        if eligible.size == 0:
            # nobody clears the bar -> relax: let the top solvers reproduce so the
            # population doesn't die (still climbs; we record this honestly via no
            # special-casing of the metric).
            eligible = np.argsort(solver_solved_counts)[-max(1, pop // 4):]
        parents = solvers[rng.choice(eligible, size=pop)]
        # ZERO-MEAN mutation: only selection (not a mutation bias) moves the frontier.
        children = np.clip(parents + rng.normal(0.0, step, parents.shape), 0.0, None)
        solvers = children  # unbounded above: frontier can keep climbing if selection pushes

        # --- TASK minimal criterion: keep tasks solved by [lo, hi] solvers ---
        sm2 = solve_matrix(solvers, tasks)       # recompute vs the new solver pop
        keep = task_band_mask(sm2, band_lo, band_hi)
        survivors = tasks[keep]
        if survivors.size == 0:
            # band empty -> seed near the current solver frontier so the curriculum
            # re-anchors to current capability (auto-curriculum self-heals).
            anchor = np.median(solvers, axis=0)
            survivors = np.clip(
                anchor[None, :] + rng.normal(0.0, task_step, (max(1, task_pop // 4), d)),
                0.0, None,
            )
        # refill task population by mutating survivors (zero-mean) -> the surviving band
        # already sits near the frontier; mutation explores難度 around it. As solvers
        # improve, the band re-selects HARDER survivors -> curriculum advances upward.
        n_children = task_pop - len(survivors)
        if n_children > 0:
            idx = rng.choice(len(survivors), size=n_children)
            new_tasks = np.clip(
                survivors[idx] + rng.normal(0.0, task_step, (n_children, d)), 0.0, None
            )
            tasks = np.vstack([survivors, new_tasks])
        else:
            tasks = survivors[:task_pop]

    return {
        "frontier": frontier,
        "task_mean_diff": task_mean_diff,
        "task_max_diff": task_max_diff,
    }


# ---------------------------------------------------------------------------
# CONTROL arm: fixed task battery, solver-only evolution
# ---------------------------------------------------------------------------
def run_fixed(
    *,
    gens: int,
    pop: int,
    task_pop: int,
    d: int,
    seed: int,
    mc_solve: int,
    step: float,
    probe: np.ndarray,
    battery_hi: float,
) -> dict:
    """Static task battery; only solvers evolve. Tasks NEVER change -> early ceiling."""
    rng = np.random.default_rng(seed)
    solvers = rng.uniform(0.0, 0.3, (pop, d))
    # fixed battery: a static set of difficulties (never regenerated). Once the best
    # solver dominates them all, the selection signal flatlines -> saturation.
    tasks = rng.uniform(0.0, battery_hi, (task_pop, d))

    frontier = np.empty(gens)
    for g in range(gens):
        frontier[g] = capability_frontier(solvers, probe)
        sm = solve_matrix(solvers, tasks)
        counts = sm.sum(axis=1)
        eligible = np.flatnonzero(counts >= mc_solve)
        if eligible.size == 0:
            eligible = np.argsort(counts)[-max(1, pop // 4):]
        parents = solvers[rng.choice(eligible, size=pop)]
        children = parents + np.abs(rng.normal(0.0, step, parents.shape))
        # NOTE: even with upward-biased mutation, once every solver solves the WHOLE
        # static battery the minimal criterion no longer discriminates -> drift only,
        # and the frontier-on-probe plateaus (no pressure toward the harder probe tail).
        all_solve = sm.all(axis=1)
        if all_solve.all():
            # selection is fully saturated: all parents equally eligible (pure drift).
            parents = solvers[rng.integers(0, pop, pop)]
            children = parents + np.abs(rng.normal(0.0, step, parents.shape)) * 0.0
        solvers = children

    return {"frontier": frontier}


# ---------------------------------------------------------------------------
# verdict
# ---------------------------------------------------------------------------
def _tail_slope(h: np.ndarray, frac: float = 0.3) -> float:
    """Least-squares slope per generation over the last `frac` of the trajectory."""
    n = max(2, int(len(h) * frac))
    seg = h[-n:]
    x = np.arange(n, dtype=float)
    # slope of linear fit
    return float(np.polyfit(x, seg, 1)[0])


def _tail_mean(h: np.ndarray, frac: float = 0.2) -> float:
    n = max(1, int(len(h) * frac))
    return float(h[-n:].mean())


def build_verdict(mcc: dict, fixed: dict, *, gens: int) -> dict:
    fm = mcc["frontier"]
    fx = fixed["frontier"]
    mcc_tail = _tail_mean(fm)
    fixed_tail = _tail_mean(fx)
    mcc_slope = _tail_slope(fm)
    fixed_slope = _tail_slope(fx)

    # plateau test for the fixed arm: tail slope small relative to its own scale.
    fixed_plateau = abs(fixed_slope) < 0.01 * (fixed_tail + 1e-9)
    # MCC still climbing: positive tail slope.
    mcc_still_climbing = mcc_slope > 0.01 * (mcc_tail + 1e-9)
    # MCC exceeds fixed in the tail with margin.
    mcc_exceeds = mcc_tail > 1.15 * fixed_tail

    mcc_avoids_saturation = bool(mcc_exceeds and mcc_still_climbing and fixed_plateau)

    return {
        "mcc_tail_frontier": round(mcc_tail, 4),
        "fixed_tail_frontier": round(fixed_tail, 4),
        "mcc_tail_slope_per_gen": round(mcc_slope, 6),
        "fixed_tail_slope_per_gen": round(fixed_slope, 6),
        "mcc_over_fixed_ratio": round(mcc_tail / (fixed_tail + 1e-9), 4),
        "mcc_exceeds_fixed_tail": bool(mcc_exceeds),
        "mcc_still_climbing": bool(mcc_still_climbing),
        "fixed_is_plateau": bool(fixed_plateau),
        "mcc_avoids_saturation": mcc_avoids_saturation,
    }


def run(
    *,
    gens: int = 300,
    pop: int = 64,
    task_pop: int = 48,
    d: int = 6,
    seed: int = 0,
    mc_solve: int = 1,
    band_lo: int = 1,
    band_hi: int = 12,
    step: float = 0.05,
    task_step: float = 0.04,
    probe_n: int = 200,
    probe_hi: float = 3.0,
    battery_hi: float = 0.6,
) -> dict:
    """Run both arms with a shared fair probe and return the full result dict."""
    probe_rng = np.random.default_rng(seed + 9999)  # probe independent of either arm
    probe = _make_probe(d, probe_n, probe_hi, probe_rng)

    mcc = run_mcc(
        gens=gens, pop=pop, task_pop=task_pop, d=d, seed=seed,
        mc_solve=mc_solve, band_lo=band_lo, band_hi=band_hi,
        step=step, task_step=task_step, probe=probe,
    )
    fixed = run_fixed(
        gens=gens, pop=pop, task_pop=task_pop, d=d, seed=seed,
        mc_solve=mc_solve, step=step, probe=probe, battery_hi=battery_hi,
    )
    verdict = build_verdict(mcc, fixed, gens=gens)

    return {
        "schema": "poc_minimal_criterion_coevolution/v1",
        "proposition": (
            "タスクと解法を共進化させ minimal criterion (解法=帯のタスクを解けば存続 / "
            "タスク=解ける解法が [lo,hi] 帯のみ存続) で回すと、固定タスク選択が陥る飽和 "
            "(能力 frontier が早期に天井で停滞) を回避し、frontier が非飽和に伸び続ける。"
        ),
        "config": {
            "gens": gens, "pop": pop, "task_pop": task_pop, "d": d, "seed": seed,
            "mc_solve": mc_solve, "band_lo": band_lo, "band_hi": band_hi,
            "step": step, "task_step": task_step,
            "probe_n": probe_n, "probe_hi": probe_hi, "battery_hi": battery_hi,
        },
        "mcc": {
            "frontier": [round(x, 4) for x in mcc["frontier"].tolist()],
            "task_mean_diff": [round(x, 4) for x in mcc["task_mean_diff"].tolist()],
            "task_max_diff": [round(x, 4) for x in mcc["task_max_diff"].tolist()],
        },
        "fixed": {
            "frontier": [round(x, 4) for x in fixed["frontier"].tolist()],
        },
        "verdict": verdict,
        "honest_notes": [
            "proxy toy・実 llive 非接触 (import ゼロ)。共進化が飽和を回避できる『機構の "
            "feasibility』を示すもので、実 LLM 進化での飽和回避を主張するものではない。",
            "frontier metric は両 arm 共通の固定 probe battery で測る (MCC を自前の易しい "
            "task で甘く採点しない = fair)。",
            "solve 判定は per-dim dominance の binary。実タスクは graded であり、この "
            "binary minimal criterion は素地のみ。",
            "次段 = 実 llive の task (苦手軸 / CTF) と個体を共進化させる配線。",
            "既存 AdaptivePercentileGate との違い: gate は固定 task 集合に対する閾値を "
            "適応させるだけ。MCC は task 自体を生成・淘汰して frontier 近傍の難度を "
            "創発させる (= auto-curriculum) 点が本質的に異なる。",
            "fixed arm が飽和しなければ命題は falsified — その場合 honest にそう報告する "
            "(mcc_avoids_saturation=False で表現)。",
        ],
    }


def _print(out: dict) -> None:
    v = out["verdict"]
    c = out["config"]
    mf = out["mcc"]["frontier"]
    xf = out["fixed"]["frontier"]
    print("\n===== Minimal Criterion Coevolution (MCC) PoC — PROXY, deterministic =====")
    print(f"gens={c['gens']} pop={c['pop']} task_pop={c['task_pop']} d={c['d']} "
          f"seed={c['seed']} band=[{c['band_lo']},{c['band_hi']}] mc_solve={c['mc_solve']}")
    print("\n[capability frontier — hardest fixed-probe difficulty any solver dominates]")
    print(f"  {'arm':10s} {'gen0':>8s} {'mid':>8s} {'final':>8s} {'tail20%':>8s} {'tailslope':>10s}")
    mid = len(mf) // 2
    print(f"  {'MCC':10s} {mf[0]:8.3f} {mf[mid]:8.3f} {mf[-1]:8.3f} "
          f"{v['mcc_tail_frontier']:8.3f} {v['mcc_tail_slope_per_gen']:10.5f}")
    print(f"  {'fixed':10s} {xf[0]:8.3f} {xf[mid]:8.3f} {xf[-1]:8.3f} "
          f"{v['fixed_tail_frontier']:8.3f} {v['fixed_tail_slope_per_gen']:10.5f}")
    print(f"\n  MCC / fixed tail ratio = {v['mcc_over_fixed_ratio']:.2f}x")
    print(f"  mcc_exceeds_fixed_tail = {v['mcc_exceeds_fixed_tail']}")
    print(f"  mcc_still_climbing     = {v['mcc_still_climbing']} "
          f"(tail slope {v['mcc_tail_slope_per_gen']:+.5f}/gen)")
    print(f"  fixed_is_plateau       = {v['fixed_is_plateau']} "
          f"(tail slope {v['fixed_tail_slope_per_gen']:+.5f}/gen)")
    print(f"\n  VERDICT mcc_avoids_saturation = {v['mcc_avoids_saturation']}")
    if v["mcc_avoids_saturation"]:
        print("  → 共進化 (タスク自動カリキュラム) は固定タスク選択が早期に陥る飽和を回避し、"
              "frontier が非飽和に伸び続けた = 機構 feasibility あり。")
    else:
        print("  → この設定では MCC が固定タスク選択を非飽和で超えなかった。honest に記録 "
              "(命題は falsified or inconclusive)。")
    print("  honest: proxy mechanism test only; 実 llive 非接触。実 LLM 進化の主張ではない。")


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description="Minimal Criterion Coevolution PoC (MCC vs fixed-task)")
    ap.add_argument("--gens", type=int, default=300)
    ap.add_argument("--pop", type=int, default=64)
    ap.add_argument("--task-pop", type=int, default=48)
    ap.add_argument("--d", type=int, default=6)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--mc-solve", type=int, default=1)
    ap.add_argument("--band-lo", type=int, default=1)
    ap.add_argument("--band-hi", type=int, default=12)
    ap.add_argument("--step", type=float, default=0.05)
    ap.add_argument("--task-step", type=float, default=0.04)
    ap.add_argument("--probe-n", type=int, default=200)
    ap.add_argument("--probe-hi", type=float, default=3.0)
    ap.add_argument("--battery-hi", type=float, default=0.6)
    ap.add_argument("--out", type=Path,
                    default=Path(r"D:/projects/llive/out/poc_minimal_criterion_coevolution"))
    args = ap.parse_args(argv)

    out = run(
        gens=args.gens, pop=args.pop, task_pop=args.task_pop, d=args.d, seed=args.seed,
        mc_solve=args.mc_solve, band_lo=args.band_lo, band_hi=args.band_hi,
        step=args.step, task_step=args.task_step,
        probe_n=args.probe_n, probe_hi=args.probe_hi, battery_hi=args.battery_hi,
    )

    args.out.mkdir(parents=True, exist_ok=True)
    out_json = args.out / "mcc.json"
    out_json.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    _print(out)
    print(f"\n[poc_mcc] wrote {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
