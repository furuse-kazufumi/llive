#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""PoC: does standardized-novelty selection SUSTAIN diversity where scalar selection COLLAPSES?

Smallest falsifiable test of the core open-ended-evolution requirement
(OPEN_ENDED_EVOLUTION_REQUIREMENTS.md: STD-1 / SEL-1 / SEL-2 / OE-3):

* **scalar** selection (old-proxy-like "all factors high & balanced") → premature
  convergence: behavioral diversity collapses (the gen23 extinction we observed).
* **novelty** selection (k-NN distance over a per-dim z-scored descriptor, incl. a
  large neutral reservoir) → diversity is sustained (no central-convergence).

Pure stdlib + numpy, deterministic (seed). No LLM (proxy). Isolated — does NOT touch
the production EvolutionLoop. Habit: always PoC (feedback_poc_feasibility_first).

    py -3.11 scripts/poc_openended_diversity.py
    py -3.11 scripts/poc_openended_diversity.py --gens 500 --pop 128 --latent 256
"""
from __future__ import annotations

import argparse
import sys

import numpy as np


def _utf8_stdout() -> None:
    """cp932 console safety: emit UTF-8 (feedback_cli_utf8_stdout_pattern)."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _diversity(G: np.ndarray) -> float:
    """behavioral diversity = mean per-dim std across the population (genome space)."""
    return float(np.mean(np.std(G, axis=0)))


def run(
    mode: str,
    *,
    gens: int = 300,
    pop: int = 64,
    n_factors: int = 10,
    latent: int = 64,
    k: int = 10,
    seed: int = 0,
    sparse: float = 0.05,
    step: float = 0.1,
) -> np.ndarray:
    """Return the per-generation diversity trajectory for `mode` in {scalar, novelty}."""
    rng = np.random.default_rng(seed)
    gdim = n_factors + latent
    G = rng.uniform(0.0, 1.0, (pop, gdim))
    archive: list[np.ndarray] = []
    hist = np.empty(gens)

    for gen in range(gens):
        hist[gen] = _diversity(G)
        # per-dim z-score descriptor over the population (STD-1): magnitude removed
        mu, sd = G.mean(0), G.std(0) + 1e-9
        D = (G - mu) / sd

        if mode == "scalar":
            # old-proxy-like: reward "all factors high and balanced" -> single peak
            fit = G.mean(1) * (1.0 - G.std(1))
        elif mode == "novelty":
            # novelty = mean k-NN distance over the z-scored descriptor (+ recent archive)
            ref = D if not archive else np.vstack([D, *archive[-5:]])
            dists = np.linalg.norm(D[:, None, :] - ref[None, :, :], axis=2)
            dists.sort(axis=1)
            fit = dists[:, 1 : k + 1].mean(axis=1)  # skip self (distance 0)
            archive.append(D.copy())
        else:
            raise ValueError(f"unknown mode: {mode}")

        # binary tournament selection
        a = rng.integers(0, pop, pop)
        b = rng.integers(0, pop, pop)
        winners = np.where(fit[a] >= fit[b], a, b)
        parents = G[winners]

        # sparse Gaussian mutation (SPARSE-1: only a fraction of loci per child)
        child = parents.copy()
        m = rng.random(child.shape) < sparse
        child[m] += rng.normal(0.0, step, int(m.sum()))
        G = np.clip(child, 0.0, 1.0)

    return hist


def main() -> int:
    ap = argparse.ArgumentParser(description="open-ended diversity PoC (scalar vs novelty)")
    ap.add_argument("--gens", type=int, default=300)
    ap.add_argument("--pop", type=int, default=64)
    ap.add_argument("--latent", type=int, default=64, help="neutral reservoir size")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--sparse", type=float, default=0.05)
    args = ap.parse_args()
    _utf8_stdout()

    kw = dict(gens=args.gens, pop=args.pop, latent=args.latent, seed=args.seed, sparse=args.sparse)
    sc = run("scalar", **kw)
    nv = run("novelty", **kw)

    def tail(h: np.ndarray) -> float:
        return float(h[-max(1, len(h) // 5):].mean())  # mean over last 20% of gens

    print(f"PoC open-ended diversity  (gens={args.gens} pop={args.pop} "
          f"latent={args.latent} seed={args.seed})  — PROXY, deterministic")
    print(f"  metric = mean per-dim genome std (higher = more behavioral diversity)")
    print(f"  {'mode':8s} {'gen0':>8s} {'final':>8s} {'tail20%':>8s} {'retained%':>10s}")
    for name, h in (("scalar", sc), ("novelty", nv)):
        retained = 100.0 * tail(h) / h[0] if h[0] else 0.0
        print(f"  {name:8s} {h[0]:8.4f} {h[-1]:8.4f} {tail(h):8.4f} {retained:9.1f}%")
    verdict = "SUSTAINED" if tail(nv) > 1.5 * tail(sc) else "INCONCLUSIVE"
    print(f"  => novelty/scalar tail ratio = {tail(nv)/ (tail(sc)+1e-9):.2f}x  [{verdict}]")
    print("  honest: proxy mechanism test only; not 'new AI'. real claim needs Stage6 LLM.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
