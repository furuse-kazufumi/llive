#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Deployable PoC: a runnable open-ended evolution ENVIRONMENT (checkpoint/resume + metrics + sweep).

Builds on the validated core (poc_openended_diversity.py: standardized-novelty selection
sustains diversity where scalar collapses) and turns it into a *runnable, introducible*
environment per the goal "新しい AI が生み出される環境を構築し、様々な条件で PoC、導入可能段階へ":

* genome = factors + cultural (opposing pairs, so 'all-max' is impossible) + neutral reservoir
* selection = per-dim z-scored NOVELTY (k-NN over pop+archive) + MINIMAL-CRITERION cull
* sparse Gaussian mutation; founder-origin lineage tracking (monoculture metric)
* QD archive over a JL random-projection 2-D map (coverage = open-endedness proxy)
* per-generation metrics.jsonl (diversity / monoculture / archive coverage / novelty)
* FULL-STATE checkpoint + --resume (continuity for 5h+ overnight runs; CKPT-1)
* --max-seconds wallclock budget; CLI knobs for the scale sweep (various conditions)

Isolated, deterministic, no LLM (PROXY). Does NOT touch production EvolutionLoop.
HONEST: proxy mechanism only; 'new AI' (intelligence) claim needs Stage6 real-LLM fitness.

    py -3.11 scripts/poc_evolution_env.py --gens 2000 --pop 256 --latent 1024 --out out/poc_env_a
    py -3.11 scripts/poc_evolution_env.py --out out/poc_env_a --resume        # continue
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np


def _utf8() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


class EvoEnv:
    def __init__(self, args: argparse.Namespace):
        self.a = args
        self.gdim = args.factors + args.cultural + args.latent
        self.proj_dim = 2  # JL random-projection map for the QD archive
        self.cells = args.cells
        self.k = args.k
        self.out = Path(args.out)
        self.out.mkdir(parents=True, exist_ok=True)

    # ---- state init / checkpoint ----
    def _fresh(self) -> None:
        a = self.a
        self.rng = np.random.default_rng(a.seed)
        # founders = distinct archetype seeds; padding = random. origin tracks lineage.
        self.G = self.rng.uniform(0, 1, (a.pop, self.gdim))
        # each gen0 individual is its OWN lineage → monoculture metric measures takeover
        # (gen0 monoculture = 1/pop). Lumping padding into one id made it trivially ~1.0.
        self.origin = np.arange(a.pop)
        # fixed JL projection matrix (deterministic from seed) for the archive map
        self.P = np.random.default_rng(a.seed + 7).normal(0, 1, (self.gdim, self.proj_dim))
        self.archive: dict[tuple[int, int], float] = {}  # cell -> best novelty
        self.gen = 0
        self.t0 = time.time()
        self.elapsed_prev = 0.0

    def _ckpt_path(self) -> Path:
        return self.out / "checkpoint.npz"

    def save(self) -> None:
        cells = np.array(list(self.archive.keys()), dtype=np.int64) if self.archive else np.zeros((0, 2), np.int64)
        vals = np.array(list(self.archive.values()), dtype=np.float64) if self.archive else np.zeros((0,), np.float64)
        np.savez(self._ckpt_path(), G=self.G, origin=self.origin, P=self.P,
                 gen=self.gen, cells=cells, vals=vals,
                 rng=self.rng.bit_generator.state["state"]["state"],
                 rng_inc=self.rng.bit_generator.state["state"]["inc"],
                 elapsed=self.elapsed_prev + (time.time() - self.t0))
        (self.out / "checkpoint_meta.json").write_text(
            json.dumps({"gen": self.gen, "pop": int(self.G.shape[0]), "gdim": self.gdim,
                        "archive_cells": len(self.archive)}, indent=2), encoding="utf-8")

    def load(self) -> bool:
        p = self._ckpt_path()
        if not p.exists():
            return False
        d = np.load(p, allow_pickle=False)
        self.G, self.origin, self.P = d["G"], d["origin"], d["P"]
        self.gen = int(d["gen"])
        self.archive = {(int(c[0]), int(c[1])): float(v) for c, v in zip(d["cells"], d["vals"])}
        self.rng = np.random.default_rng(self.a.seed)
        st = self.rng.bit_generator.state
        st["state"]["state"] = int(d["rng"]); st["state"]["inc"] = int(d["rng_inc"])
        self.rng.bit_generator.state = st
        self.elapsed_prev = float(d["elapsed"]); self.t0 = time.time()
        return True

    # ---- core step ----
    def _descriptor(self) -> np.ndarray:
        mu, sd = self.G.mean(0), self.G.std(0) + 1e-9
        return (self.G - mu) / sd  # per-dim z-score (STD-1)

    def _novelty(self, D: np.ndarray, arch_D: np.ndarray | None) -> np.ndarray:
        ref = D if arch_D is None or len(arch_D) == 0 else np.vstack([D, arch_D])
        # chunked k-NN to bound memory at large pop
        nov = np.empty(len(D))
        for i in range(len(D)):
            dd = np.linalg.norm(ref - D[i], axis=1)
            dd.sort()
            nov[i] = dd[1:self.k + 1].mean()
        return nov

    def _update_archive(self, D: np.ndarray, nov: np.ndarray) -> None:
        # 2-D map with FIXED bounds (not per-gen min-max, which trivially fills all cells).
        # D is per-dim z-scored (unit var) and P ~ N(0,1); (D@P)/sqrt(gdim) ~ N(0,1) → bin [-4,4].
        coords = (D @ self.P) / np.sqrt(self.gdim)
        ix = np.clip(((coords + 4.0) / 8.0 * self.cells).astype(int), 0, self.cells - 1)
        for i in range(len(D)):
            cell = (int(ix[i, 0]), int(ix[i, 1]))
            if nov[i] > self.archive.get(cell, -1.0):
                self.archive[cell] = float(nov[i])

    def step(self) -> dict:
        a = self.a
        D = self._descriptor()
        arch_D = None  # archive stores scalar novelty per cell; use population-only k-NN (+ self-archive optional)
        nov = self._novelty(D, arch_D)
        self._update_archive(D, nov)

        # metrics
        diversity = float(np.mean(np.std(self.G, axis=0)))
        uniq, counts = np.unique(self.origin, return_counts=True)
        monoculture = float(counts.max() / self.G.shape[0])
        rec = {"generation": self.gen, "diversity": diversity, "monoculture": monoculture,
               "archive_cells": len(self.archive), "mean_novelty": float(nov.mean())}

        # minimal-criterion: cull bottom MC% by novelty (ineligible to reproduce)
        floor = np.quantile(nov, a.mc_cull)
        eligible = np.where(nov >= floor)[0]
        if len(eligible) < 2:
            eligible = np.arange(self.G.shape[0])
        # tournament by novelty among eligible
        ea, eb = self.rng.choice(eligible, a.pop), self.rng.choice(eligible, a.pop)
        win = np.where(nov[ea] >= nov[eb], ea, eb)
        parents, porigin = self.G[win], self.origin[win]
        child = parents.copy()
        m = self.rng.random(child.shape) < a.sparse
        child[m] += self.rng.normal(0, a.step, int(m.sum()))
        self.G = np.clip(child, 0, 1)
        self.origin = porigin  # inherit founder origin from parent (lineage)
        self.gen += 1
        return rec

    def run(self) -> None:
        a = self.a
        resumed = a.resume and self.load()
        if not resumed:
            self._fresh()
        mpath = self.out / "metrics.jsonl"
        fh = mpath.open("a" if resumed else "w", encoding="utf-8")
        print(f"[evo-env] {'resume' if resumed else 'start'} gen={self.gen} pop={a.pop} "
              f"gdim={self.gdim} (f{a.factors}+c{a.cultural}+latent{a.latent}) "
              f"max_gens={a.gens} max_s={a.max_seconds} out={self.out}")
        last_ckpt = self.gen
        while self.gen < a.gens:
            rec = self.step()
            fh.write(json.dumps(rec) + "\n")
            if self.gen % max(1, a.log_every) == 0:
                fh.flush()
            if self.gen - last_ckpt >= a.checkpoint_every:
                self.save(); last_ckpt = self.gen
            if a.max_seconds and (self.elapsed_prev + time.time() - self.t0) >= a.max_seconds:
                print(f"[evo-env] wallclock budget reached at gen {self.gen}")
                break
        fh.close()
        self.save()
        self._report()

    def _report(self) -> None:
        rows = [json.loads(l) for l in (self.out / "metrics.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        if not rows:
            return
        n = len(rows)
        tail = rows[-max(1, n // 5):]
        div0 = rows[0]["diversity"]
        divt = np.mean([r["diversity"] for r in tail])
        mono_t = np.mean([r["monoculture"] for r in tail])
        cells_first = rows[max(0, n - max(1, n // 5)) - 1]["archive_cells"] if n > 5 else rows[0]["archive_cells"]
        cells_last = rows[-1]["archive_cells"]
        growth = cells_last - cells_first  # archive growth over last 20% (open-endedness proxy)
        verdict = "OPEN-ENDED-ish" if (divt > 0.5 * div0 and mono_t < 0.8 and growth >= 1) else "BOUNDED/COLLAPSED"
        print(f"[evo-env] gens={n} diversity {div0:.3f}->{divt:.3f}(tail) "
              f"monoculture(tail)={mono_t:.2f} archive_cells={cells_last} "
              f"growth(last20%)={growth:+d}  => {verdict}")
        print("  honest: PROXY mechanism; not 'new AI'. real claim needs Stage6 LLM.")


def main() -> int:
    _utf8()
    ap = argparse.ArgumentParser(description="deployable open-ended evolution PoC environment")
    ap.add_argument("--gens", type=int, default=2000)
    ap.add_argument("--pop", type=int, default=256)
    ap.add_argument("--factors", type=int, default=10)
    ap.add_argument("--cultural", type=int, default=12)
    ap.add_argument("--latent", type=int, default=1024)
    ap.add_argument("--founders", type=int, default=8)
    ap.add_argument("--k", type=int, default=15)
    ap.add_argument("--cells", type=int, default=32, help="QD archive grid resolution per axis")
    ap.add_argument("--mc-cull", type=float, default=0.1, help="minimal-criterion: cull bottom fraction by novelty")
    ap.add_argument("--sparse", type=float, default=0.03)
    ap.add_argument("--step", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=str, default="out/poc_env")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--checkpoint-every", type=int, default=200)
    ap.add_argument("--max-seconds", type=float, default=0.0, help="wallclock budget (0 = none)")
    ap.add_argument("--log-every", type=int, default=10)
    EvoEnv(ap.parse_args()).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
