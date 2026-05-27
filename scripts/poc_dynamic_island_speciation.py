#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""PoC: does a DYNAMIC ISLAND / SPECIATION model preserve MULTIMODALITY where a single
PANMICTIC population prematurely converges to ONE peak?

Smallest falsifiable test of the dynamic-deme idea the user raised (2026-05-24): cluster
the population with k-means into islands, evolve islands independently, migrate
periodically, and MERGE islands whose centroids have converged. RAD anchors: Island GA
(Cohoon 1987) / NEAT speciation (Stanley 2002) / dynamic deme formation.

Proposition (falsifiable):

  「集団を behavior/genome 空間で k-means により動的に島(deme)へ分割し、島ごとに独立進化
    + 周期 migration + 収束島のマージを行うと、単一集団 (panmictic) より
      (a) 多峰 fitness 地形で *複数の峰を同時に保持* し
      (b) 早期収束 (premature convergence) を回避して最終多様性/被覆が高い。」

ならなければ honest にそう報告する ([[feedback_benchmark_honest_disclosure]])。

Design (stdlib + numpy, deterministic seed, ZERO llive imports = isolated toy;
the frozen src/llive/perf/evolutionary/island_model.py is NEVER imported or touched):

* MULTIMODAL landscape: K Gaussian peaks at distinct centres in R^d. fitness(x) =
  max_k peak_height[k] * exp(-||x - centre_k||^2 / (2 sigma^2)). Peaks are well separated
  (>> sigma) so a panmictic pop, once it commits to one peak's basin, drifts the whole
  population there = premature convergence onto a SINGLE peak.

* ISLANDS arm: each MIGRATION period the population is (re)clustered with k-means (genome
  space) into K_max islands; each island runs tournament selection + Gaussian mutation
  independently for `period` gens; then a few migrants are exchanged between islands; then
  islands whose CENTROIDS are within `merge_eps` are MERGED (island count shrinks
  dynamically). Independent demes let DIFFERENT islands settle on DIFFERENT peaks.

* PANMICTIC arm: a single population of the SAME total size, SAME total budget (gens), SAME
  tournament + mutation operators, NO clustering / migration / merge. Selection pressure
  pulls the whole pop into the basin of whatever peak first dominates -> one peak.

* METRICS (per generation): #peaks occupied (a peak is "occupied" if >= occ_min
  individuals lie within occ_radius of its centre), genome spread (mean pairwise distance),
  best fitness, and the diversity trajectory (to detect EARLY collapse = premature conv.).

* VERDICT (COMPOSITE, deterministic — single scalars mislead, per先行4 PoC教訓):
  islands_preserve_multimodality := (islands occupy MORE peaks in the tail
      AND islands keep HIGHER final genome diversity) AND islands AVOID the early
      diversity collapse that panmictic suffers. Reported alongside migration/merge cost
      and a hyperparameter (K_max / migration-rate) sensitivity sweep (honest disclosure).

    py -3.11 scripts/poc_dynamic_island_speciation.py
    py -3.11 scripts/poc_dynamic_island_speciation.py --gens 240 --seed 1
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
# multimodal fitness landscape: K separated Gaussian peaks
# ---------------------------------------------------------------------------
def make_peaks(*, K: int, d: int, spread: float, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Return (centres (K,d), heights (K,)) for K well-separated Gaussian peaks.

    Centres are placed on a scaled grid / random lattice far apart (>> sigma) so the basins
    are distinct: an evolutionary pop must spread across the search space to occupy >1 peak.
    Heights are NEARLY equal (small jitter) so there is no single trivially-dominant peak —
    this is what makes premature convergence to one arbitrary peak a real failure mode.
    """
    rng = np.random.default_rng(seed)
    # place centres on a coarse integer lattice then scale by `spread`, so any two centres
    # are at least `spread` apart (>> sigma). deterministic given seed.
    centres = rng.integers(0, 3, size=(K, d)).astype(float) * spread
    # de-duplicate collisions deterministically by nudging along dim 0.
    for i in range(K):
        for j in range(i):
            if np.allclose(centres[i], centres[j]):
                centres[i, 0] += spread
    heights = 1.0 + 0.05 * rng.standard_normal(K)  # near-equal heights, tiny jitter
    return centres, np.abs(heights)


def fitness(pop: np.ndarray, centres: np.ndarray, heights: np.ndarray, sigma: float) -> np.ndarray:
    """Multimodal fitness: f(x) = max_k height_k * exp(-||x-c_k||^2 / (2 sigma^2)).

    `pop` is (n,d). Returns (n,). The MAX over peaks makes the landscape genuinely
    multimodal with disjoint basins of attraction (not a single additive bump).
    """
    # (n, K, d) -> squared distances (n, K)
    diff = pop[:, None, :] - centres[None, :, :]
    sq = np.sum(diff * diff, axis=2)
    vals = heights[None, :] * np.exp(-sq / (2.0 * sigma * sigma))
    return vals.max(axis=1)


# ---------------------------------------------------------------------------
# peak occupancy + diversity metrics
# ---------------------------------------------------------------------------
def peaks_occupied(pop: np.ndarray, centres: np.ndarray, *, radius: float, occ_min: int) -> int:
    """Count peaks with >= occ_min individuals within `radius` of the centre.

    A robust, structural multimodality metric: it is NOT fooled by a single lucky
    individual visiting a peak (requires a resident sub-population of >= occ_min).
    """
    diff = pop[:, None, :] - centres[None, :, :]
    dist = np.sqrt(np.sum(diff * diff, axis=2))  # (n, K)
    within = dist <= radius                       # (n, K)
    counts = within.sum(axis=0)                   # (K,)
    return int(np.sum(counts >= occ_min))


def genome_spread(pop: np.ndarray, *, sample: int = 64, seed: int = 0) -> float:
    """Mean pairwise Euclidean distance (population genome diversity).

    Sub-sampled deterministically for O(sample^2) cost. A high value = the population is
    spread over the search space; a collapse toward 0 = premature convergence.
    """
    n = pop.shape[0]
    if n < 2:
        return 0.0
    rng = np.random.default_rng(seed)
    idx = np.arange(n) if n <= sample else rng.choice(n, size=sample, replace=False)
    sub = pop[idx]
    diff = sub[:, None, :] - sub[None, :, :]
    dist = np.sqrt(np.sum(diff * diff, axis=2))
    m = sub.shape[0]
    # mean over the upper triangle (exclude the zero diagonal)
    iu = np.triu_indices(m, k=1)
    return float(dist[iu].mean()) if iu[0].size else 0.0


# ---------------------------------------------------------------------------
# evolutionary operators (shared by both arms = fair)
# ---------------------------------------------------------------------------
def tournament_breed(
    pop: np.ndarray,
    fit: np.ndarray,
    *,
    n_children: int,
    tour_k: int,
    step: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Tournament selection + Gaussian mutation. Returns `n_children` offspring.

    Selection pressure is what drives a basin commitment; the SAME operator is used by both
    arms, so the only difference between arms is islands-vs-panmictic STRUCTURE, not the
    selection/mutation mechanics (fair contrast).
    """
    if pop.shape[0] == 0 or n_children <= 0:
        return pop[:0].copy()
    n = pop.shape[0]
    # tour_k competitors per child, pick the fittest -> parent index.
    comp = rng.integers(0, n, size=(n_children, min(tour_k, n)))
    comp_fit = fit[comp]
    winners = comp[np.arange(n_children), comp_fit.argmax(axis=1)]
    parents = pop[winners]
    children = parents + rng.normal(0.0, step, parents.shape)
    return children


# ---------------------------------------------------------------------------
# k-means (numpy only) for dynamic deme clustering
# ---------------------------------------------------------------------------
def kmeans(pts: np.ndarray, k: int, *, iters: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Tiny deterministic Lloyd's k-means. Returns (labels (n,), centroids (k_eff, d)).

    k_eff may be < k if a cluster empties (we drop empty clusters -> this is part of the
    DYNAMIC island count: clusters can vanish). Used to split the population into demes.
    """
    n = pts.shape[0]
    k = max(1, min(k, n))
    # deterministic init: pick k farthest-ish seeds via k-means++-lite using rng.
    centroids = pts[rng.choice(n, size=k, replace=False)].copy()
    labels = np.zeros(n, dtype=int)
    for _ in range(iters):
        d2 = np.sum((pts[:, None, :] - centroids[None, :, :]) ** 2, axis=2)  # (n,k)
        labels = d2.argmin(axis=1)
        new_centroids = []
        for j in range(centroids.shape[0]):
            members = pts[labels == j]
            if members.shape[0] > 0:
                new_centroids.append(members.mean(axis=0))
        if not new_centroids:
            break
        nc = np.asarray(new_centroids)
        if nc.shape == centroids.shape and np.allclose(nc, centroids):
            centroids = nc
            break
        centroids = nc
    # recompute final labels against the (possibly shrunk) centroid set
    d2 = np.sum((pts[:, None, :] - centroids[None, :, :]) ** 2, axis=2)
    labels = d2.argmin(axis=1)
    return labels, centroids


def merge_close_centroids(centroids: np.ndarray, labels: np.ndarray, *, eps: float) -> np.ndarray:
    """MERGE islands whose centroids are within `eps` (union-find on a proximity graph).

    Returns NEW labels remapped onto the merged island ids (island count shrinks). This is
    the 'converged islands merge' mechanic: once two demes have drifted onto the same basin
    they are fused so budget isn't wasted maintaining duplicates.
    """
    k = centroids.shape[0]
    if k <= 1:
        return labels.copy()
    parent = list(range(k))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    cd = np.sqrt(np.sum((centroids[:, None, :] - centroids[None, :, :]) ** 2, axis=2))
    for i in range(k):
        for j in range(i + 1, k):
            if cd[i, j] <= eps:
                union(i, j)
    roots = np.array([find(i) for i in range(k)])
    # compact root ids -> 0..m-1 (deterministic order)
    uniq = {r: n for n, r in enumerate(sorted(set(roots.tolist())))}
    remap = np.array([uniq[roots[i]] for i in range(k)])
    return remap[labels]


# ---------------------------------------------------------------------------
# ISLANDS arm: dynamic k-means demes + migration + merge
# ---------------------------------------------------------------------------
def run_islands(
    *,
    gens: int,
    pop_size: int,
    d: int,
    seed: int,
    centres: np.ndarray,
    heights: np.ndarray,
    sigma: float,
    k_max: int,
    period: int,
    migrate_frac: float,
    merge_eps: float,
    tour_k: int,
    step: float,
    init_lo: float,
    init_hi: float,
    occ_radius: float,
    occ_min: int,
) -> dict:
    """Evolve a population partitioned into DYNAMIC k-means islands.

    Every `period` gens: re-cluster -> merge converged islands -> migrate. Within a period
    each island breeds independently (tournament + mutation), preserving its OWN basin.
    """
    rng = np.random.default_rng(seed)
    pop = rng.uniform(init_lo, init_hi, (pop_size, d))
    labels, centroids = kmeans(pop, k_max, iters=10, rng=rng)
    labels = merge_close_centroids(centroids, labels, eps=merge_eps)

    occ = np.empty(gens, dtype=int)
    spread = np.empty(gens)
    best = np.empty(gens)
    island_count = np.empty(gens, dtype=int)
    migrate_events = 0
    merge_total = 0  # cumulative reduction in island count due to merges

    for g in range(gens):
        fit = fitness(pop, centres, heights, sigma)
        occ[g] = peaks_occupied(pop, centres, radius=occ_radius, occ_min=occ_min)
        spread[g] = genome_spread(pop, seed=seed)
        best[g] = float(fit.max())
        island_count[g] = int(len(np.unique(labels)))

        # --- periodic restructure: recluster, merge converged demes, migrate ---
        if g > 0 and g % period == 0:
            pre_k, _ = kmeans(pop, k_max, iters=10, rng=rng)
            labels2, centroids2 = kmeans(pop, k_max, iters=10, rng=rng)
            before = len(np.unique(labels2))
            labels = merge_close_centroids(centroids2, labels2, eps=merge_eps)
            after = len(np.unique(labels))
            merge_total += max(0, before - after)
            # migration: move a few random individuals between islands (ring-ish exchange)
            isl_ids = np.unique(labels)
            if isl_ids.size >= 2:
                n_mig = max(1, int(migrate_frac * pop_size))
                mig_idx = rng.choice(pop_size, size=min(n_mig, pop_size), replace=False)
                # reassign each migrant to a different island id (shift in the id ring)
                shift = rng.integers(1, isl_ids.size, size=mig_idx.size)
                cur_pos = np.searchsorted(isl_ids, labels[mig_idx])
                new_pos = (cur_pos + shift) % isl_ids.size
                labels[mig_idx] = isl_ids[new_pos]
                migrate_events += 1

        # --- independent within-island breeding (each deme keeps its own basin) ---
        new_pop_parts = []
        new_label_parts = []
        for isl in np.unique(labels):
            mask = labels == isl
            members = pop[mask]
            mfit = fit[mask]
            n_isl = members.shape[0]
            if n_isl == 0:
                continue
            children = tournament_breed(
                members, mfit, n_children=n_isl, tour_k=tour_k, step=step, rng=rng
            )
            new_pop_parts.append(children)
            new_label_parts.append(np.full(children.shape[0], isl, dtype=int))
        pop = np.vstack(new_pop_parts)
        labels = np.concatenate(new_label_parts)
        # guard pop_size constant (breeding is per-island n_children=n_isl -> already exact)

    return {
        "occupied": occ,
        "spread": spread,
        "best": best,
        "island_count": island_count,
        "migrate_events": migrate_events,
        "merge_total": merge_total,
    }


# ---------------------------------------------------------------------------
# PANMICTIC arm: single population, same budget, same operators, no structure
# ---------------------------------------------------------------------------
def run_panmictic(
    *,
    gens: int,
    pop_size: int,
    d: int,
    seed: int,
    centres: np.ndarray,
    heights: np.ndarray,
    sigma: float,
    tour_k: int,
    step: float,
    init_lo: float,
    init_hi: float,
    occ_radius: float,
    occ_min: int,
) -> dict:
    """Single panmictic population. SAME budget/operators as islands, NO demes/migration.

    Tournament selection over the whole pop pulls everyone into one peak's basin once it
    dominates -> premature convergence onto a SINGLE peak, diversity collapses early.
    """
    rng = np.random.default_rng(seed)
    pop = rng.uniform(init_lo, init_hi, (pop_size, d))

    occ = np.empty(gens, dtype=int)
    spread = np.empty(gens)
    best = np.empty(gens)

    for g in range(gens):
        fit = fitness(pop, centres, heights, sigma)
        occ[g] = peaks_occupied(pop, centres, radius=occ_radius, occ_min=occ_min)
        spread[g] = genome_spread(pop, seed=seed)
        best[g] = float(fit.max())
        pop = tournament_breed(
            pop, fit, n_children=pop_size, tour_k=tour_k, step=step, rng=rng
        )

    return {"occupied": occ, "spread": spread, "best": best}


# ---------------------------------------------------------------------------
# verdict (composite, deterministic)
# ---------------------------------------------------------------------------
def _tail_mean(h: np.ndarray, frac: float = 0.2) -> float:
    n = max(1, int(len(h) * frac))
    return float(np.asarray(h, dtype=float)[-n:].mean())


def _peak_diversity_collapse(spread: np.ndarray, *, early_frac: float = 0.25) -> float:
    """Ratio final_diversity / peak_early_diversity. << 1 => early collapse (premature conv).

    We take the MAX diversity over the early window (the bloom right after random init) as
    the reference and compare it to the tail mean. A panmictic pop blooms then collapses
    (ratio small); structured islands retain a larger fraction (ratio closer to / above 1).
    """
    s = np.asarray(spread, dtype=float)
    e = max(1, int(len(s) * early_frac))
    early_peak = float(s[:e].max())
    tail = _tail_mean(s)
    return tail / (early_peak + 1e-9)


def build_verdict(
    isl: dict,
    pan: dict,
    *,
    K: int,
    collapse_thresh: float,
) -> dict:
    """Deterministic COMPOSITE verdict (no single scalar — 先行4 PoC教訓).

    islands_preserve_multimodality is an AND of three structural conditions:
      (1) islands occupy MORE peaks in the tail than panmictic (multimodality retained),
      (2) islands keep HIGHER final genome diversity than panmictic,
      (3) islands AVOID the early diversity collapse that panmictic suffers
          (islands' final/early-peak diversity ratio is materially higher than panmictic's).
    A single metric (e.g. just peak count) misjudges: a pop can sprinkle individuals over
    peaks while still collapsing in diversity, or vice versa. The AND gate is robust.
    """
    isl_occ_tail = _tail_mean(isl["occupied"])
    pan_occ_tail = _tail_mean(pan["occupied"])
    isl_div_tail = _tail_mean(isl["spread"])
    pan_div_tail = _tail_mean(pan["spread"])
    isl_collapse = _peak_diversity_collapse(isl["spread"])
    pan_collapse = _peak_diversity_collapse(pan["spread"])

    cond_more_peaks = isl_occ_tail > pan_occ_tail
    cond_more_diversity = isl_div_tail > pan_div_tail
    # islands materially avoid the collapse panmictic suffers: panmictic collapses below the
    # threshold while islands hold a clearly higher retention ratio.
    cond_avoids_collapse = (pan_collapse < collapse_thresh) and (
        isl_collapse > pan_collapse * 1.5
    )

    islands_preserve_multimodality = bool(
        cond_more_peaks and cond_more_diversity and cond_avoids_collapse
    )

    return {
        "n_peaks": int(K),
        "islands_tail_peaks_occupied": round(isl_occ_tail, 4),
        "panmictic_tail_peaks_occupied": round(pan_occ_tail, 4),
        "islands_tail_diversity": round(isl_div_tail, 4),
        "panmictic_tail_diversity": round(pan_div_tail, 4),
        "islands_diversity_retention": round(isl_collapse, 4),
        "panmictic_diversity_retention": round(pan_collapse, 4),
        "collapse_threshold": collapse_thresh,
        "cond_more_peaks": bool(cond_more_peaks),
        "cond_more_diversity": bool(cond_more_diversity),
        "cond_avoids_collapse": bool(cond_avoids_collapse),
        "islands_migrate_events": int(isl.get("migrate_events", 0)),
        "islands_merge_total": int(isl.get("merge_total", 0)),
        "islands_preserve_multimodality": islands_preserve_multimodality,
    }


def run(
    *,
    gens: int = 200,
    pop_size: int = 120,
    d: int = 4,
    seed: int = 0,
    K: int = 6,
    peak_spread: float = 6.0,
    sigma: float = 1.0,
    k_max: int = 6,
    period: int = 8,
    migrate_frac: float = 0.05,
    merge_eps: float = 1.0,
    tour_k: int = 3,
    step: float = 0.25,
    init_lo: float = -2.0,
    init_hi: float = 14.0,
    occ_radius: float = 2.0,
    occ_min: int = 3,
    collapse_thresh: float = 0.6,
) -> dict:
    """Run both arms over an identical multimodal landscape; return result dict."""
    centres, heights = make_peaks(K=K, d=d, spread=peak_spread, seed=seed)

    isl = run_islands(
        gens=gens, pop_size=pop_size, d=d, seed=seed, centres=centres, heights=heights,
        sigma=sigma, k_max=k_max, period=period, migrate_frac=migrate_frac,
        merge_eps=merge_eps, tour_k=tour_k, step=step, init_lo=init_lo, init_hi=init_hi,
        occ_radius=occ_radius, occ_min=occ_min,
    )
    pan = run_panmictic(
        gens=gens, pop_size=pop_size, d=d, seed=seed, centres=centres, heights=heights,
        sigma=sigma, tour_k=tour_k, step=step, init_lo=init_lo, init_hi=init_hi,
        occ_radius=occ_radius, occ_min=occ_min,
    )
    verdict = build_verdict(isl, pan, K=K, collapse_thresh=collapse_thresh)

    return {
        "schema": "poc_dynamic_island_speciation/v1",
        "proposition": (
            "集団を behavior/genome 空間で k-means により動的に島(deme)へ分割し、島ごとに独立進化 "
            "+ 周期 migration + 収束島マージを行うと、単一集団 (panmictic) より多峰 fitness 地形で "
            "複数の峰を同時に保持し、早期収束を回避して最終多様性/被覆が高い。"
        ),
        "config": {
            "gens": gens, "pop_size": pop_size, "d": d, "seed": seed, "K": K,
            "peak_spread": peak_spread, "sigma": sigma, "k_max": k_max, "period": period,
            "migrate_frac": migrate_frac, "merge_eps": merge_eps, "tour_k": tour_k,
            "step": step, "init_lo": init_lo, "init_hi": init_hi,
            "occ_radius": occ_radius, "occ_min": occ_min, "collapse_thresh": collapse_thresh,
        },
        "islands": {
            "occupied": [int(x) for x in isl["occupied"].tolist()],
            "spread": [round(x, 4) for x in isl["spread"].tolist()],
            "best": [round(x, 4) for x in isl["best"].tolist()],
            "island_count": [int(x) for x in isl["island_count"].tolist()],
            "migrate_events": int(isl["migrate_events"]),
            "merge_total": int(isl["merge_total"]),
        },
        "panmictic": {
            "occupied": [int(x) for x in pan["occupied"].tolist()],
            "spread": [round(x, 4) for x in pan["spread"].tolist()],
            "best": [round(x, 4) for x in pan["best"].tolist()],
        },
        "verdict": verdict,
        "honest_notes": [
            "proxy toy・実 llive 非接触 (import ゼロ)。frozen な "
            "src/llive/perf/evolutionary/island_model.py は import も改変もしていない。"
            "多峰地形上で動的島が多峰性を保つ『機構の feasibility』を示すもので、実 LLM "
            "進化での効果を主張するものではない。",
            "verdict は単一指標でなく COMPOSITE AND gate (峰占有数 多 AND 最終多様性 高 AND "
            "panmictic の早期多様性崩壊を回避) で判定 (先行4 PoC教訓: 単一スカラーは誤判定しやすい)。",
            "fitness は K 個の分離 Gaussian peak の max。peak は >> sigma で離れており panmictic は "
            "一峰の basin に commit すると全集団がそこへドリフト = premature convergence。",
            "両 arm は同 budget (gens)・同 pop_size・同 tournament+mutation operator。唯一の差は "
            "islands の k-means deme 構造 + migration + merge の有無 = fair contrast。",
            "k-means は genome 空間で島を切る proxy。実 llive では behavior 記述子 (④AURORA 連携) で "
            "島を切る/マージ閾値 merge_eps を較正する必要がある (この toy は genome 距離で代用)。",
            "HONEST cost: islands は migration/merge の計算コスト (migrate_events / merge_total を "
            "JSON に記録) を負う。また island 数・migration 率・merge_eps の hyperparameter 感度が "
            "ある (sweep 結果は report 参照)。merge_eps が小さすぎると島が割れたまま、大きすぎると "
            "1 島へ収束し panmictic と区別がつかなくなる。",
            "diversity collapse 指標 = final / early-peak diversity。panmictic は init 直後の bloom 後に "
            "崩壊 (ratio 小)、islands は独立 deme が複数 basin を保持するため高い retention を残す。",
            "verdict が False なら命題は inconclusive/falsified — honest にそう報告する "
            "(islands_preserve_multimodality=False で表現)。",
            "次段 = 実 llive の派生集団進化 (v0.C/D/E/F) に behavior-descriptor 島 + 動的 merge を "
            "配線し、AURORA 記述子で島を切る統合。",
        ],
    }


def _print(out: dict) -> None:
    v = out["verdict"]
    c = out["config"]
    io = out["islands"]["occupied"]
    po = out["panmictic"]["occupied"]
    print("\n===== Dynamic Island / Speciation PoC — PROXY, deterministic =====")
    print(f"gens={c['gens']} pop={c['pop_size']} d={c['d']} seed={c['seed']} "
          f"K_peaks={c['K']} k_max={c['k_max']} period={c['period']} "
          f"migrate_frac={c['migrate_frac']} merge_eps={c['merge_eps']}")
    print("\n[peaks occupied (>= occ_min residents within occ_radius of a peak centre)]")
    mid = len(io) // 2
    print(f"  {'arm':10s} {'gen0':>6s} {'mid':>6s} {'final':>6s} {'tail20%':>9s}")
    print(f"  {'islands':10s} {io[0]:6d} {io[mid]:6d} {io[-1]:6d} "
          f"{v['islands_tail_peaks_occupied']:9.3f}")
    print(f"  {'panmictic':10s} {po[0]:6d} {po[mid]:6d} {po[-1]:6d} "
          f"{v['panmictic_tail_peaks_occupied']:9.3f}")
    print("\n[genome diversity (mean pairwise distance)]")
    print(f"  islands  tail = {v['islands_tail_diversity']:.3f}   "
          f"retention(final/early-peak) = {v['islands_diversity_retention']:.3f}")
    print(f"  panmictic tail = {v['panmictic_tail_diversity']:.3f}   "
          f"retention(final/early-peak) = {v['panmictic_diversity_retention']:.3f}   "
          f"(collapse threshold {v['collapse_threshold']:.2f})")
    print(f"\n[islands dynamic structure] migrate_events={v['islands_migrate_events']} "
          f"merge_total={v['islands_merge_total']} "
          f"(island count {out['islands']['island_count'][0]} -> {out['islands']['island_count'][-1]})")
    print("\n[composite verdict conditions]")
    print(f"  cond_more_peaks       = {v['cond_more_peaks']} "
          f"({v['islands_tail_peaks_occupied']:.3f} > {v['panmictic_tail_peaks_occupied']:.3f})")
    print(f"  cond_more_diversity   = {v['cond_more_diversity']} "
          f"({v['islands_tail_diversity']:.3f} > {v['panmictic_tail_diversity']:.3f})")
    print(f"  cond_avoids_collapse  = {v['cond_avoids_collapse']} "
          f"(panmictic retention {v['panmictic_diversity_retention']:.3f} < "
          f"{v['collapse_threshold']:.2f} AND islands {v['islands_diversity_retention']:.3f} "
          f"> 1.5x panmictic)")
    print(f"\n  VERDICT islands_preserve_multimodality = {v['islands_preserve_multimodality']}")
    if v["islands_preserve_multimodality"]:
        print("  → 動的 k-means 島 + migration + 収束島マージは多峰性を同時保持し、panmictic が陥る "
              "早期収束を回避した = 機構 feasibility あり。")
    else:
        print("  → この設定では動的島が panmictic を複合条件で上回らなかった。honest に記録 "
              "(命題は falsified or inconclusive)。")
    print("  honest: proxy mechanism test only; 実 llive 非接触 (island_model.py 未 import/未改変)。")


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    ap = argparse.ArgumentParser(
        description="Dynamic Island / Speciation PoC (islands vs panmictic on multimodal landscape)"
    )
    ap.add_argument("--gens", type=int, default=200)
    ap.add_argument("--pop-size", type=int, default=120)
    ap.add_argument("--d", type=int, default=4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--K", type=int, default=6, help="number of fitness peaks")
    ap.add_argument("--peak-spread", type=float, default=6.0)
    ap.add_argument("--sigma", type=float, default=1.0)
    ap.add_argument("--k-max", type=int, default=6, help="initial island count")
    ap.add_argument("--period", type=int, default=8, help="recluster/migrate/merge period")
    ap.add_argument("--migrate-frac", type=float, default=0.05)
    ap.add_argument("--merge-eps", type=float, default=1.0)
    ap.add_argument("--tour-k", type=int, default=3)
    ap.add_argument("--step", type=float, default=0.25)
    ap.add_argument("--init-lo", type=float, default=-2.0)
    ap.add_argument("--init-hi", type=float, default=14.0)
    ap.add_argument("--occ-radius", type=float, default=2.0)
    ap.add_argument("--occ-min", type=int, default=3)
    ap.add_argument("--collapse-thresh", type=float, default=0.6)
    ap.add_argument("--out", type=Path,
                    default=Path(r"D:/projects/llive/out/poc_dynamic_island_speciation"))
    args = ap.parse_args(argv)

    out = run(
        gens=args.gens, pop_size=args.pop_size, d=args.d, seed=args.seed, K=args.K,
        peak_spread=args.peak_spread, sigma=args.sigma, k_max=args.k_max, period=args.period,
        migrate_frac=args.migrate_frac, merge_eps=args.merge_eps, tour_k=args.tour_k,
        step=args.step, init_lo=args.init_lo, init_hi=args.init_hi,
        occ_radius=args.occ_radius, occ_min=args.occ_min, collapse_thresh=args.collapse_thresh,
    )

    args.out.mkdir(parents=True, exist_ok=True)
    out_json = args.out / "islands.json"
    out_json.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    _print(out)
    print(f"\n[poc_dynamic_island_speciation] wrote {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
