#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""PoC sweep: 「固定スカラー目的は飽和・全滅し、開放端(novelty/QD/MC)はそれを回避する」を実証.

Background (honest disclosure, 2026-05-26)
------------------------------------------
直近の 12h 実 LLM 進化ラン (out/lldarwin_12h_realpressure_2026_05_26) の実データで、
固定の人手 quiz fitness が **gen5 で best=1.0 に飽和し、以降 66 世代が無進歩 = 進化として
成立していない** ことが判明した。原因:
  (a) 評価軸の大半が飽和ノイズで実効勾配が少数 dim しかない (argmax が即 max に張り付く)、
  (b) fitness に効くのは少数 chromosome のみ、残り (c_factors 40dim 等) は中立浮動。
ユーザー結論 = 「人手の恣意的な固定ものさしを捨て、自由な開放端進化 (QD/novelty) へ」。

What this sweep does
--------------------
要件正本 `fullsense/docs/vision/OPEN_ENDED_EVOLUTION_REQUIREMENTS.md` §0/§2/§3 に従い、
**§3 の直交軸**を proxy・決定論・実 LLM 無し (SR-1 sandbox) で sweep する:

* 選択 (selection):
    - ``scalar``    : 固定スカラー目的の argmax tournament (= baseline の飽和・全滅を再現)
    - ``novelty``   : per-dim z-score 標準化記述子上の k-NN novelty tournament (SEL-1/2)
    - ``lexicase``  : ε-lexicase — 多軸 archetype ケースを集約せず個別評価 (SEL-3)
    - 各選択に ``+minimal-criterion`` (--mc) を直交付加 (SEL-4): 下位を繁殖不可に
* 標準化 (--standardize): per-dim z-score on/off (STD-1)
* 中立貯蔵庫 (--reservoir): off / size∈{256,1024} (NEUT-1/2: descriptor が読むが scalar fitness は読まない)
* アーカイブ (--archive): none / map-elites (QD-1/2, JL 2D map で軽量化 DESC-1)

ゲノム構成 (要件 §1.2):
    genome = factors (scalar fitness が読む、archetype peak を作る意味ある少数 dim)
           + saturation-noise dims (fitness 飽和の源、argmax が無視する)
           + neutral reservoir (--latent, fitness 中立。標準化記述子 / QD map が読む)
archetype peak を持つ ``factors`` で scalar argmax は数世代で max=1.0 に飽和し、
飽和ノイズと中立 latent では勾配ゼロ → 進化が止まる (= lldarwin の再現)。

受入メトリクス (§2, 末尾世代で判定):
    archive_growth(末尾20%世代でも新 cell ≥1) / monoculture(全世代 <0.8) /
    behavioral diversity(非ゼロ高止まり) / mean_novelty 時系列(枯渇しない) /
    全滅検査(有効個体数 = pop 維持 ∧ 生存 lineage ≥2)

Isolated / deterministic / NO LLM (PROXY). 既存 production EvolutionLoop に触れない。
HONEST: proxy mechanism feasibility only. 'new AI' (intelligence) の主張は Stage6 実 LLM 必須。

    py -3.11 scripts/poc_openended_sweep.py --gens 10000 --pop 256 --out out/poc_openended_sweep_2026_05_26
    py -3.11 scripts/poc_openended_sweep.py --quick      # 短時間 smoke (gens=2000)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


def _utf8() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Run configuration (one orthogonal-axis combination)
# ---------------------------------------------------------------------------
@dataclass
class RunConfig:
    """1 sweep 構成 (§3 直交軸の 1 点)."""

    label: str
    selection: str  # "scalar" | "novelty" | "lexicase"
    standardize: bool = True
    minimal_criterion: bool = False
    reservoir: int = 0  # 0 = off, else size
    archive: str = "none"  # "none" | "map-elites"

    # scale knobs (CLI から注入)
    pop: int = 256
    gens: int = 10000
    factors: int = 10  # archetype peak を作る意味ある dim (scalar fitness が読む)
    sat_noise: int = 12  # 飽和ノイズ dim (argmax が無視する)
    latent: int = 256  # 中立貯蔵庫 dim (fitness 中立, descriptor が読む)
    n_archetypes: int = 8  # scalar fitness の peak 数 (= lldarwin founder 数)
    k: int = 15
    cells: int = 32  # QD map 解像度 (per axis)
    mc_cull: float = 0.2  # minimal-criterion: 下位 fraction を繁殖不可に
    sparse: float = 0.05  # per-locus 変異率 (SPARSE-1)
    step: float = 0.1
    seed: int = 0
    eps_lexicase: float = 0.05

    def gdim(self) -> int:
        return self.factors + self.sat_noise + self.latent


# ---------------------------------------------------------------------------
# The open-ended evolution engine (numpy-only, fast proxy)
# ---------------------------------------------------------------------------
class OpenEndedRun:
    """1 構成を回し、世代ごとに §2 受入メトリクスを記録する.

    scalar baseline と開放端 (novelty/lexicase/QD/MC) を同一 engine の
    selection mode 切替で比較できるよう、共通の繁殖・記述子・archive パスを使う。
    """

    def __init__(self, cfg: RunConfig):
        self.cfg = cfg
        self.gdim = cfg.gdim()
        self.proj_dim = 2  # JL random-projection map for the QD archive (DESC-1)

    # ---- init --------------------------------------------------------------
    def _init(self) -> None:
        c = self.cfg
        self.rng = np.random.default_rng(c.seed)
        # 固定 archetype peaks。**factors 部分にのみ** peak を置く
        # (= scalar fitness が読む少数の意味ある dim)。残り (sat_noise/latent) は
        # archetype に含めない → 勾配が無く飽和ノイズ/中立浮動になる。
        ap_rng = np.random.default_rng(c.seed + 101)
        self.archetypes = ap_rng.uniform(0, 1, (c.n_archetypes, c.factors))

        # 固定 JL 射影行列 (決定論)。記述子 → 2D map。
        self.P = np.random.default_rng(c.seed + 7).normal(0, 1, (self.gdim, self.proj_dim))

        # gen0: 各 archetype 近傍に種を撒く + ランダム padding。
        # 各 gen0 個体は自分自身の lineage (monoculture が takeover を測れるように)。
        G = self.rng.uniform(0, 1, (c.pop, self.gdim))
        for i in range(c.pop):
            a = i % c.n_archetypes
            # factors 部分を archetype 近傍に寄せる (founder seeding と同義)
            G[i, : c.factors] = np.clip(
                self.archetypes[a] + self.rng.normal(0, 0.05, c.factors), 0, 1
            )
        self.G = G
        self.origin = np.arange(c.pop)  # lineage label (selectively neutral)

        # QD archive: cell -> best scalar fitness in that cell (QD-1/2)
        self.archive: dict[tuple[int, int], float] = {}
        # 中立貯蔵庫: cell -> (best descriptor-novelty, genome). 絶滅 niche の re-inject 用。
        self.reservoir: dict[int, tuple[float, np.ndarray]] = {}
        self.gen = 0

    # ---- proxy fitness (固定スカラー目的 — lldarwin 飽和の再現) ------------
    def _scalar_fitness(self) -> np.ndarray:
        """max over archetypes の類似度 (lldarwin rich-proxy と同型).

        factors 部分のみを読む → archetype peak に乗った個体は即 1.0 (飽和)。
        飽和ノイズ dim / 中立 latent は読まない (勾配ゼロ)。
        """
        F = self.G[:, : self.cfg.factors]  # (pop, factors)
        # similarity = 1 - normalized L2 to nearest archetype
        # (pop, n_arch, factors)
        diff = F[:, None, :] - self.archetypes[None, :, :]
        dist = np.linalg.norm(diff, axis=2) / np.sqrt(self.cfg.factors)
        sim = 1.0 - dist
        return sim.max(axis=1)  # max over archetypes → multi-modal だが各 peak は 1.0 飽和

    def _archetype_cases(self) -> np.ndarray:
        """lexicase 用の多軸ケース行列 (pop, n_archetypes). 集約しない (SEL-3)."""
        F = self.G[:, : self.cfg.factors]
        diff = F[:, None, :] - self.archetypes[None, :, :]
        dist = np.linalg.norm(diff, axis=2) / np.sqrt(self.cfg.factors)
        return 1.0 - dist  # 各 archetype への類似度 = 個別ケース

    # ---- descriptor / novelty ---------------------------------------------
    def _descriptor(self) -> np.ndarray:
        """行動記述子。標準化 on なら per-dim z-score (STD-1)。

        記述子は全 gdim (factors + sat_noise + latent) を読む → 中立貯蔵庫が
        novelty/QD に寄与する (NEUT-2)。scalar fitness は factors しか読まない。
        """
        if self.cfg.standardize:
            mu, sd = self.G.mean(0), self.G.std(0) + 1e-9
            return (self.G - mu) / sd
        return self.G.copy()

    def _novelty(self, D: np.ndarray) -> np.ndarray:
        # 中立貯蔵庫を参照集合に含める (絶滅 niche の記憶 → novelty 枯渇防止)
        ref = D
        if self.reservoir:
            # 全 reservoir genome を一括で記述子空間へ写す (per-entry 呼び出しを避け高速化)
            res_G = np.array([g for _, g in self.reservoir.values()])
            if self.cfg.standardize:
                mu, sd = self.G.mean(0), self.G.std(0) + 1e-9
                res_D = (res_G - mu) / sd
            else:
                res_D = res_G
            ref = np.vstack([D, res_D])
        kk = max(1, min(self.cfg.k, len(ref) - 1))
        # vectorized k-NN: ||a-b||^2 = |a|^2 + |b|^2 - 2 a·b。自己距離 (対角) を除外し
        # 各行で最近接 kk 個 (自己の次から) の平均を取る。pop≤数千で十分高速 (chunk で OOM 防止)。
        ref_sq = np.einsum("ij,ij->i", ref, ref)
        nov = np.empty(len(D))
        chunk = 512
        for start in range(0, len(D), chunk):
            end = min(start + chunk, len(D))
            d_chunk = D[start:end]
            d_sq = np.einsum("ij,ij->i", d_chunk, d_chunk)[:, None]
            # squared dist (chunk, n_ref); 数値誤差で僅かに負になりうるので clip(0)
            dsq = d_sq + ref_sq[None, :] - 2.0 * (d_chunk @ ref.T)
            np.maximum(dsq, 0.0, out=dsq)
            dist = np.sqrt(dsq)
            # 自己 (= start..end 行に対応する ref 列) を inf にして除外
            for r in range(end - start):
                dist[r, start + r] = np.inf
            part = np.partition(dist, kk, axis=1)[:, :kk]
            nov[start:end] = part.mean(axis=1)
        return nov

    def _project_descriptor(self, genome: np.ndarray) -> np.ndarray:
        """reservoir 内の生 genome を現世代の記述子空間へ写す (標準化 params 共有)."""
        if self.cfg.standardize:
            mu, sd = self.G.mean(0), self.G.std(0) + 1e-9
            return (genome - mu) / sd
        return genome.copy()

    # ---- QD archive + reservoir -------------------------------------------
    def _map_coords(self, D: np.ndarray) -> np.ndarray:
        # D が z-score 済みなら (D@P)/sqrt(gdim) ~ N(0,1) → 固定 bin [-4,4]
        coords = (D @ self.P) / np.sqrt(self.gdim)
        return np.clip(((coords + 4.0) / 8.0 * self.cfg.cells).astype(int), 0, self.cfg.cells - 1)

    def _update_archive(self, D: np.ndarray, scalar: np.ndarray) -> None:
        if self.cfg.archive != "map-elites":
            return
        ix = self._map_coords(D)
        for i in range(len(D)):
            cell = (int(ix[i, 0]), int(ix[i, 1]))
            # QD-2: cell elite は scalar fitness で比較 (新 cell は必ず採用、単調成長)
            if scalar[i] > self.archive.get(cell, -np.inf):
                self.archive[cell] = float(scalar[i])

    def _update_reservoir(self, D: np.ndarray, nov: np.ndarray) -> None:
        if self.cfg.reservoir <= 0:
            return
        ix = self._map_coords(D)
        flat = ix[:, 0] * self.cfg.cells + ix[:, 1]
        for i in range(len(D)):
            cell = int(flat[i])
            if cell not in self.reservoir or nov[i] > self.reservoir[cell][0]:
                self.reservoir[cell] = (float(nov[i]), self.G[i].copy())
        # 容量上限: 古い/低 novelty を切る
        if len(self.reservoir) > self.cfg.reservoir:
            keep = sorted(self.reservoir.items(), key=lambda kv: -kv[1][0])[: self.cfg.reservoir]
            self.reservoir = dict(keep)

    # ---- selection --------------------------------------------------------
    def _select_parents(self, scalar: np.ndarray, nov: np.ndarray, cases: np.ndarray) -> np.ndarray:
        """pop 個の親 index を返す。selection mode で分岐。"""
        c = self.cfg
        n = self.G.shape[0]

        # minimal-criterion: 下位 mc_cull を繁殖不可に (SEL-4)
        # 何を criterion にするかは選択軸に合わせる (scalar は scalar、それ以外は novelty)
        crit = scalar if c.selection == "scalar" else nov
        if c.minimal_criterion:
            floor = np.quantile(crit, c.mc_cull)
            eligible = np.where(crit >= floor)[0]
            if len(eligible) < 2:
                eligible = np.arange(n)
        else:
            eligible = np.arange(n)

        if c.selection == "scalar":
            # 固定スカラー目的の argmax tournament (= baseline)。飽和すると勾配ゼロ。
            ea, eb = self.rng.choice(eligible, n), self.rng.choice(eligible, n)
            return np.where(scalar[ea] >= scalar[eb], ea, eb)

        if c.selection == "novelty":
            ea, eb = self.rng.choice(eligible, n), self.rng.choice(eligible, n)
            return np.where(nov[ea] >= nov[eb], ea, eb)

        if c.selection == "lexicase":
            # ε-lexicase: 各親選択ごとに archetype ケースをランダム順に当て、
            # ε 内の prime を残して絞る (集約しない、専門家が生存)。
            parents = np.empty(n, dtype=int)
            n_cases = cases.shape[1]
            for p in range(n):
                pool = eligible.copy()
                order = self.rng.permutation(n_cases)
                for ci in order:
                    if len(pool) <= 1:
                        break
                    vals = cases[pool, ci]
                    best = vals.max()
                    pool = pool[vals >= best - c.eps_lexicase]
                parents[p] = pool[self.rng.integers(len(pool))]
            return parents

        raise ValueError(f"unknown selection: {c.selection!r}")

    # ---- one generation ----------------------------------------------------
    def step(self) -> dict:
        c = self.cfg
        scalar = self._scalar_fitness()
        cases = self._archetype_cases() if c.selection == "lexicase" else np.zeros((c.pop, 1))
        D = self._descriptor()
        nov = self._novelty(D)

        self._update_archive(D, scalar)
        self._update_reservoir(D, nov)

        # --- metrics (§2) ---
        diversity = float(np.mean(np.std(self.G, axis=0)))  # behavioral diversity (genome std)
        ix = self._map_coords(D)
        flat = ix[:, 0] * c.cells + ix[:, 1]
        # monoculture = 行動集中 (最大占有 map cell の割合)。OE-3。
        monoculture = float(np.bincount(flat).max() / c.pop)
        # occupied_cells = この世代で集団が占有する distinct な behavioral niche 数。
        # これが「全滅検査」の正しい操作的量 (§0: open-endedness の signal は behavioral)。
        occupied_cells = int(len(np.unique(flat)))
        # n_distinct_genomes = この世代の distinct な個体数 (behavioral 全滅 = ほぼ全部同一)。
        n_distinct = int(np.unique(self.G.round(6), axis=0).shape[0])
        # lineage_fixation は INFORMATIONAL のみ。founder-origin label は selectively
        # NEUTRAL なので機構に関係なく中立浮動 (Kimura) で固定する → 全滅判定には使わない。
        # 系統 label を <1 に保つには QD niching on lineage / PERSONA-FX が要る
        # (poc_evolution_env.py 著者コメントと整合)。ここでは behavioral 量で全滅を測る。
        uniq_lineages = int(len(np.unique(self.origin)))
        lineage_fix = float(np.unique(self.origin, return_counts=True)[1].max() / c.pop)
        rec = {
            "generation": self.gen,
            "scalar_best": float(scalar.max()),
            "scalar_mean": float(scalar.mean()),
            "diversity": diversity,
            "monoculture": monoculture,
            "occupied_cells": occupied_cells,
            "mean_novelty": float(nov.mean()),
            "archive_cells": len(self.archive),
            "uniq_lineages": uniq_lineages,
            "lineage_fixation": lineage_fix,
            "n_distinct_genomes": n_distinct,
        }

        # --- breed ---
        parents = self._select_parents(scalar, nov, cases)
        child = self.G[parents].copy()
        porigin = self.origin[parents]
        # sparse per-locus Gaussian mutation (SPARSE-1)
        m = self.rng.random(child.shape) < c.sparse
        child[m] += self.rng.normal(0, c.step, int(m.sum()))
        self.G = np.clip(child, 0, 1)
        self.origin = porigin

        # 中立貯蔵庫からの re-inject: 絶滅した map cell の elite を「親が低 novelty だった子」
        # に差し戻す (lineage-niched QD の核, 開放端を支える)。
        # NOTE: 差し替え対象は **親 novelty (nov[parents])** の昇順で選ぶ。子の novelty を
        # 再計算 (高コスト) せずに「最も平凡な系統」を置換でき、再計算 1 回ぶん高速化する。
        # map coords (present 判定) は安価なので post-breed の D2 で行う。
        if c.reservoir > 0 and self.reservoir:
            D2 = self._descriptor()
            ix2 = self._map_coords(D2)
            present = set(int(r[0] * c.cells + r[1]) for r in ix2)
            extinct = [cell for cell in self.reservoir if cell not in present]
            if extinct:
                order = np.argsort(nov[parents])  # 親が低 novelty の子から差し替え
                n_reinj = min(len(extinct), max(1, c.pop // 20))  # 最大 5% re-inject
                for j in range(n_reinj):
                    cell = extinct[j % len(extinct)]
                    self.G[order[j]] = self.reservoir[cell][1].copy()
                    self.origin[order[j]] = -(cell + 1)  # 復活 lineage に負ラベル

        self.gen += 1
        return rec

    # ---- run loop ----------------------------------------------------------
    def run(self, out_dir: Path, log_every: int = 25) -> dict:
        c = self.cfg
        self._init()
        rows: list[dict] = []
        t0 = time.time()
        while self.gen < c.gens:
            rec = self.step()
            if self.gen % log_every == 0 or self.gen == 1:
                rows.append(rec)
        elapsed = time.time() - t0

        metrics_path = out_dir / f"metrics_{c.label}.jsonl"
        metrics_path.write_text(
            "\n".join(json.dumps(r) for r in rows), encoding="utf-8"
        )
        summary = self._summarize(rows, elapsed)
        summary["config"] = {
            "label": c.label, "selection": c.selection, "standardize": c.standardize,
            "minimal_criterion": c.minimal_criterion, "reservoir": c.reservoir,
            "archive": c.archive, "pop": c.pop, "gens": c.gens, "gdim": self.gdim,
            "factors": c.factors, "sat_noise": c.sat_noise, "latent": c.latent,
            "n_archetypes": c.n_archetypes, "seed": c.seed,
        }
        return summary

    def _summarize(self, rows: list[dict], elapsed: float) -> dict:
        """§2 受入メトリクスを末尾世代で判定する."""
        if not rows:
            return {"error": "no rows"}
        n = len(rows)
        tail = rows[-max(1, n // 5):]  # 末尾 20%
        head = rows[: max(1, n // 5)]

        # archive growth (末尾20%世代でも新 cell ≥1)
        cells_at_tail_start = tail[0]["archive_cells"]
        cells_final = rows[-1]["archive_cells"]
        archive_growth_tail = cells_final - cells_at_tail_start

        # behavioral diversity: 末尾平均 / 初期との比
        div0 = rows[0]["diversity"]
        div_tail = float(np.mean([r["diversity"] for r in tail]))

        # monoculture: 全世代 max
        mono_max = float(max(r["monoculture"] for r in rows))
        mono_tail = float(np.mean([r["monoculture"] for r in tail]))

        # novelty 枯渇判定: 末尾平均 / 初期平均
        nov_head = float(np.mean([r["mean_novelty"] for r in head]))
        nov_tail = float(np.mean([r["mean_novelty"] for r in tail]))

        # scalar 飽和判定: best が頭打ちになった世代 (= 最初に max に到達した世代)
        scalar_best_final = rows[-1]["scalar_best"]
        sat_gen = None
        for r in rows:
            if r["scalar_best"] >= scalar_best_final - 1e-9:
                sat_gen = r["generation"]
                break

        # 全滅検査 (BEHAVIORAL, §0): 末尾世代で集団が占有する distinct niche 数 と
        # distinct genome 数。lineage label は中立浮動するので全滅判定に使わない。
        distinct_tail = float(np.mean([r["n_distinct_genomes"] for r in tail]))
        occupied_tail = float(np.mean([r["occupied_cells"] for r in tail]))
        uniq_lineages_tail = float(np.mean([r["uniq_lineages"] for r in tail]))  # informational
        pop = self.cfg.pop

        # 判定 (§2 合格条件)
        ok_archive = archive_growth_tail >= 1 if self.cfg.archive == "map-elites" else None
        ok_monoculture = mono_max < 0.8
        ok_diversity = div_tail > 0.5 * div0
        ok_novelty = nov_tail > 0.5 * nov_head if nov_head > 0 else None
        # behavioral 全滅でない = 末尾でも複数 niche を占有 ∧ 個体が collapse していない。
        # 「pop の半分以上が distinct な個体」かつ「2 niche 以上」を生存条件とする。
        ok_alive = occupied_tail >= 2 and distinct_tail >= 0.5 * pop

        # 総合: open-ended 成立 = 飽和して停止せず多様性持続 + behavioral に全滅しない
        # baseline (scalar) は飽和し monoculture / behavioral 全滅しやすい。
        open_ended = bool(ok_monoculture and ok_diversity and ok_alive
                          and (ok_archive in (True, None)))

        return {
            "elapsed_s": round(elapsed, 2),
            "gens_run": rows[-1]["generation"],
            "scalar_best_final": round(scalar_best_final, 4),
            "scalar_saturation_gen": sat_gen,
            "archive_cells_final": cells_final,
            "archive_growth_tail20pct": archive_growth_tail,
            "diversity_init": round(div0, 4),
            "diversity_tail": round(div_tail, 4),
            "monoculture_max": round(mono_max, 4),
            "monoculture_tail": round(mono_tail, 4),
            "novelty_head": round(nov_head, 4),
            "novelty_tail": round(nov_tail, 4),
            "distinct_genomes_tail": round(distinct_tail, 1),
            "occupied_cells_tail": round(occupied_tail, 1),
            "uniq_lineages_tail": round(uniq_lineages_tail, 1),  # informational (neutral drift)
            "checks": {
                "archive_growth>=1": ok_archive,
                "monoculture<0.8": ok_monoculture,
                "diversity_held": ok_diversity,
                "novelty_not_depleted": ok_novelty,
                "alive_behavioral": ok_alive,
            },
            "open_ended": open_ended,
        }


# ---------------------------------------------------------------------------
# Sweep driver
# ---------------------------------------------------------------------------
def build_sweep(base: RunConfig) -> list[RunConfig]:
    """§3 直交軸の代表構成を組む (フル直交 = 組合せ爆発なので意味ある点を選別)."""
    import copy

    def mk(label: str, **kw) -> RunConfig:
        c = copy.replace(base, label=label) if hasattr(copy, "replace") else None
        if c is None:
            from dataclasses import replace as dc_replace
            c = dc_replace(base, label=label)
        for k, v in kw.items():
            setattr(c, k, v)
        return c

    return [
        # --- baseline: 固定スカラー目的 argmax (飽和・全滅を再現) ---
        mk("baseline_scalar", selection="scalar", standardize=False, archive="none"),
        mk("baseline_scalar_mc", selection="scalar", standardize=False,
           minimal_criterion=True, archive="none"),
        # --- 開放端: novelty (標準化 on/off) ---
        mk("novelty_std", selection="novelty", standardize=True, archive="none"),
        mk("novelty_nostd", selection="novelty", standardize=False, archive="none"),
        # --- 開放端: novelty + minimal-criterion ---
        mk("novelty_std_mc", selection="novelty", standardize=True,
           minimal_criterion=True, archive="none"),
        # --- 開放端: ε-lexicase ---
        mk("lexicase_std", selection="lexicase", standardize=True, archive="none"),
        mk("lexicase_std_mc", selection="lexicase", standardize=True,
           minimal_criterion=True, archive="none"),
        # --- QD アーカイブ (MAP-Elites) を novelty に付与 ---
        mk("novelty_std_qd", selection="novelty", standardize=True, archive="map-elites"),
        # --- 中立貯蔵庫 (reservoir) sweep ---
        mk("novelty_std_res256", selection="novelty", standardize=True,
           reservoir=256, archive="map-elites"),
        mk("novelty_std_res1024", selection="novelty", standardize=True,
           reservoir=1024, archive="map-elites"),
        # --- フル開放端: novelty + std + MC + QD + reservoir ---
        mk("full_oe", selection="novelty", standardize=True, minimal_criterion=True,
           reservoir=1024, archive="map-elites"),
        # --- scalar に QD を付けても飽和回避できるか (対照) ---
        mk("scalar_qd", selection="scalar", standardize=False, archive="map-elites"),
    ]


def main() -> int:
    _utf8()
    ap = argparse.ArgumentParser(description="open-ended evolution PoC sweep (proxy, deterministic)")
    ap.add_argument("--gens", type=int, default=10000)
    ap.add_argument("--pop", type=int, default=256)
    ap.add_argument("--factors", type=int, default=10)
    ap.add_argument("--sat-noise", type=int, default=12)
    ap.add_argument("--latent", type=int, default=256)
    ap.add_argument("--n-archetypes", type=int, default=8)
    ap.add_argument("--cells", type=int, default=32)
    ap.add_argument("--k", type=int, default=15)
    ap.add_argument("--sparse", type=float, default=0.05)
    ap.add_argument("--step", type=float, default=0.1)
    ap.add_argument("--mc-cull", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=str, default="out/poc_openended_sweep")
    ap.add_argument("--only", type=str, default="", help="comma-separated labels to run (subset)")
    ap.add_argument("--quick", action="store_true", help="smoke: gens=2000, pop=64")
    args = ap.parse_args()

    if args.quick:
        args.gens = min(args.gens, 2000)
        args.pop = min(args.pop, 64)
        args.latent = min(args.latent, 64)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    base = RunConfig(
        label="base", selection="scalar", pop=args.pop, gens=args.gens,
        factors=args.factors, sat_noise=args.sat_noise, latent=args.latent,
        n_archetypes=args.n_archetypes, cells=args.cells, k=args.k,
        sparse=args.sparse, step=args.step, mc_cull=args.mc_cull, seed=args.seed,
    )
    configs = build_sweep(base)
    if args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        configs = [c for c in configs if c.label in wanted]

    print(f"[sweep] {len(configs)} configs, gens={args.gens} pop={args.pop} "
          f"gdim={base.gdim()} out={out}")
    summaries: list[dict] = []
    for i, cfg in enumerate(configs, 1):
        t = time.time()
        summ = OpenEndedRun(cfg).run(out)
        summaries.append(summ)
        (out / f"summary_{cfg.label}.json").write_text(
            json.dumps(summ, indent=2), encoding="utf-8"
        )
        verdict = "OPEN-ENDED" if summ.get("open_ended") else "BOUNDED/COLLAPSED"
        print(f"  [{i}/{len(configs)}] {cfg.label:22s} {time.time()-t:6.1f}s "
              f"best={summ['scalar_best_final']:.3f}@g{summ['scalar_saturation_gen']} "
              f"div {summ['diversity_init']:.3f}->{summ['diversity_tail']:.3f} "
              f"mono_max={summ['monoculture_max']:.2f} "
              f"cells={summ['archive_cells_final']} "
              f"niches={summ['occupied_cells_tail']:.0f} => {verdict}")

    (out / "all_summaries.json").write_text(
        json.dumps(summaries, indent=2), encoding="utf-8"
    )
    _write_summary_md(out, summaries, args)
    print(f"[sweep] done. summary -> {out / 'SUMMARY.md'}")
    return 0


def _write_summary_md(out: Path, summaries: list[dict], args: argparse.Namespace) -> None:
    lines: list[str] = []
    lines.append("# Open-Ended Evolution PoC Sweep — SUMMARY")
    lines.append("")
    lines.append(f"- 生成: proxy / deterministic / NO LLM (SR-1 sandbox). seed={args.seed}")
    lines.append(f"- scale: gens={args.gens}, pop={args.pop}, "
                 f"gdim={args.factors + args.sat_noise + args.latent} "
                 f"(factors={args.factors} + sat_noise={args.sat_noise} + latent={args.latent}), "
                 f"n_archetypes={args.n_archetypes}")
    lines.append("")
    lines.append("**仮説**: 固定スカラー目的 (baseline) は飽和・単峰化・(系統)全滅するが、"
                 "開放端 (novelty/lexicase + 標準化 + QD + 中立貯蔵庫) はそれを回避し多様性を持続する。")
    lines.append("")
    lines.append("## 比較表 (§2 受入メトリクス, 末尾世代判定)")
    lines.append("")
    lines.append("| 構成 | 選択 | std | MC | res | QD | best@飽和gen | div(init→tail) | mono_max | cells | nov(head→tail) | niches(tail) | 判定 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for s in summaries:
        c = s["config"]
        verdict = "OPEN-ENDED" if s.get("open_ended") else "BOUNDED/COLLAPSED"
        lines.append(
            f"| {c['label']} | {c['selection']} | {'Y' if c['standardize'] else '-'} "
            f"| {'Y' if c['minimal_criterion'] else '-'} | {c['reservoir'] or '-'} "
            f"| {'Y' if c['archive']=='map-elites' else '-'} "
            f"| {s['scalar_best_final']:.3f}@g{s['scalar_saturation_gen']} "
            f"| {s['diversity_init']:.3f}→{s['diversity_tail']:.3f} "
            f"| {s['monoculture_max']:.2f} | {s['archive_cells_final']} "
            f"| {s['novelty_head']:.2f}→{s['novelty_tail']:.2f} "
            f"| {s['occupied_cells_tail']:.0f} | {verdict} |"
        )
    lines.append("")
    lines.append("## §2 チェック内訳")
    lines.append("")
    lines.append("| 構成 | archive_growth≥1 | monoculture<0.8 | diversity_held | novelty_not_depleted | alive(behavioral) | archive_growth(tail20%) |")
    lines.append("|---|---|---|---|---|---|---|")
    for s in summaries:
        ch = s["checks"]
        def m(v):
            return "—" if v is None else ("PASS" if v else "FAIL")
        lines.append(
            f"| {s['config']['label']} | {m(ch['archive_growth>=1'])} | {m(ch['monoculture<0.8'])} "
            f"| {m(ch['diversity_held'])} | {m(ch['novelty_not_depleted'])} | {m(ch['alive_behavioral'])} "
            f"| {s['archive_growth_tail20pct']:+d} |"
        )
    lines.append("")
    lines.append("> 注: `lineage_fixation` は全構成で中立浮動 (Kimura) により ~1.0 に固定するため "
                 "**全滅判定には使わない** (informational のみ)。open-endedness の operative signal は "
                 "behavioral 量 (occupied niches / monoculture / diversity / archive growth) — §0 と整合。")
    lines.append("")
    # 自動判定: baseline vs open-ended
    base_runs = [s for s in summaries if s["config"]["selection"] == "scalar"]
    oe_runs = [s for s in summaries if s["config"]["selection"] != "scalar"]
    base_oe = [s["open_ended"] for s in base_runs]
    oe_oe = [s["open_ended"] for s in oe_runs]
    lines.append("## 結論 (honest disclosure)")
    lines.append("")
    if base_runs and oe_runs:
        base_saturated = all(
            s["scalar_saturation_gen"] is not None
            and s["scalar_saturation_gen"] < args.gens * 0.1
            for s in base_runs
        )
        lines.append(f"- **baseline(scalar) 構成**: open-ended 成立 = "
                     f"{sum(base_oe)}/{len(base_oe)}。"
                     f"飽和 (best が gens の 10% 未満で頭打ち) = "
                     f"{'YES' if base_saturated else 'NO'}。")
        lines.append(f"- **開放端構成 (novelty/lexicase)**: open-ended 成立 = "
                     f"{sum(oe_oe)}/{len(oe_oe)}。")
        if sum(oe_oe) > sum(base_oe):
            lines.append("- **判定: 「開放端は成立し baseline は成立しない」を支持する方向。**")
        elif sum(oe_oe) == 0:
            lines.append("- **判定: 開放端も成立せず (要パラメータ調整 — 次巡へ)。**")
        else:
            lines.append("- **判定: 部分的。崩壊した開放端構成あり (下表 FAIL 参照、次巡で調整)。**")
    lines.append("")
    lines.append("> HONEST: これは proxy mechanism feasibility のみ。"
                 "'new AI' (intelligence) の主張は Stage6 実 LLM 評価が必須 (要件 §0-4)。"
                 "崩壊/飽和した構成も隠さず上表に残す。")
    (out / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
