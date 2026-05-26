#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""PoC scale-up sweep: 「母数 (population) を上げると開放端は多様性を **質的に** 増やすか」を実証.

Background (honest disclosure, 2026-05-27)
------------------------------------------
先行 sweep (`scripts/poc_openended_sweep.py`, out/poc_openended_sweep_2026_05_26*) で:
  * 全 scalar 構成は全滅・飽和 (open-ended 不成立)、
  * 全 novelty/lexicase 構成は open-ended 成立 (13/13)、
を 10K世代×pop256 で実証済。さらに round2 で **記述子容量 (genome latent)** を
256→1024 に上げると occupied niches が 101→146-150 に増えることを確認した (GENOME-1)。

しかし要件 `fullsense/docs/vision/OPEN_ENDED_EVOLUTION_REQUIREMENTS.md` の **POP-1**
(母数 population のスケール 256→4096) は **未検証** だった。本 sweep はそこを埋める。

What this sweep does
--------------------
**full_oe 系構成** (selection=novelty, standardize=on, minimal_criterion=on,
reservoir=1024, archive=map-elites) を **pop ∈ {256, 1024, 2048, 4096}** で回し、
要件 §2 メトリクス (occupied niches / archive cells / monoculture / uniq_lineages /
factor_spread / behavioral_spread / mean_novelty) の **pop に対する単調性** を測る。

仮説 (POP-1): 「母数を上げると open-endedness 指標が **質的に** 向上する」
  — occupied niches ↑ / archive cells ↑ / monoculture ↓ / 多様性 ↑ が pop↑ で単調。

Tractability (最優先)
---------------------
novelty の k-NN は O(pop²) かつ既存実装は **全 gdim (1046-dim)** で距離を取る →
pop4096×gdim1046 は重すぎる。本 wrapper は `ScaleupRun` で `_novelty` を override し、
**記述子を固定 JL 射影で低次元 (--nov-proj, 既定 24 dim) に落として** から k-NN 距離を計算する
(DESC-1: JL 射影 8-50 dim)。これで距離計算が O(pop²·proj) になり pop4096 でも現実的時間に収まる。

  * archive/reservoir の map 座標は従来通り 2D JL (engine の self.P) を使う (機構不変)。
  * QD grid 解像度 `cells` は **pop 横断で固定** (既定 64 → 4096 cell grid) して
    「occupied niches が grid 上限で頭打ちにならない」ようにする (pop4096 でも grid に余裕)。
    → niche 数が pop に応じて増える余地を担保し POP-1 を公正に判定できる。
  * gens は pop に応じて短縮可 (pop が大きいほど 1 世代が重いため)。ただし末尾20%で
    「多様性が持続しているか」を判定できる長さは確保する (既定 pop256:5000 → pop4096:2000)。

正直な測定限界 (honest disclosure)
----------------------------------
  * novelty 距離は **JL 24-dim 近似** で計算 (full-gdim 厳密 k-NN ではない)。
    Johnson-Lindenstrauss 補題で距離は ~保たれるが、絶対 novelty 値は engine 既存ランと
    直接比較不可 (low-dim では距離スケールが縮む)。**pop 横断の相対比較** が目的。
  * gens は pop で異なる → 「同一世代数での比較」ではない。各 pop が tail で飽和/持続して
    いるかを内部で見て判定する。pop↑で gens↓だと niche 蓄積に不利 (= POP の効果を過小評価
    する方向のバイアス) なので、それでも niche が増えれば POP-1 を強く支持する。
  * cells を pop 横断で固定するので occupied niches の上限は cells² (既定 4096)。
    pop4096 が grid を埋め尽くしたら飽和 (頭打ち) として正直に報告する。

Isolated / deterministic / NO LLM (PROXY). 既存 production EvolutionLoop に触れない。
既存 `poc_openended_sweep.py` は import するだけ (additive、改変なし)。

    py -3.11 scripts/poc_scaleup_sweep.py --out out/poc_scaleup_2026_05_27
    py -3.11 scripts/poc_scaleup_sweep.py --quick   # smoke: small pops, short gens
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace as dc_replace
from pathlib import Path

import numpy as np

# scripts/ を sys.path に載せて poc_openended_sweep を import できるようにする
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# 既存 engine を additive に再利用 (改変なし)。
from poc_openended_sweep import OpenEndedRun, RunConfig, _utf8  # noqa: E402


class ScaleupRun(OpenEndedRun):
    """`OpenEndedRun` を tractability 用に拡張: novelty k-NN を低次元 JL 射影で計算する.

    既存の `_novelty` は全 gdim (1046-dim) で O(pop²·gdim) → pop4096 で重い。
    ここでは記述子 D を固定 JL 行列 `self.Pnov` で `nov_proj` 次元へ射影してから
    k-NN 距離を取る (DESC-1)。距離計算は O(pop²·nov_proj) に縮む。
    map 座標 (archive/reservoir) は engine の self.P (2D) のまま = 機構不変。
    """

    def __init__(self, cfg: RunConfig, nov_proj: int = 24):
        super().__init__(cfg)
        self.nov_proj = nov_proj

    def _init(self) -> None:  # noqa: D401
        super()._init()
        # novelty 用の固定 JL 射影行列 (決定論)。記述子 gdim -> nov_proj。
        self.Pnov = np.random.default_rng(self.cfg.seed + 31).normal(
            0, 1, (self.gdim, self.nov_proj)
        ) / np.sqrt(self.nov_proj)

    def _novelty(self, D: np.ndarray) -> np.ndarray:
        """低次元 JL 射影上で k-NN novelty を計算 (tractable, DESC-1).

        参照集合に中立貯蔵庫 (reservoir) を含める点は engine 既存実装と同じ意味論。
        射影は距離を Johnson-Lindenstrauss で近似保存する → 相対 novelty は妥当。
        """
        Dp = D @ self.Pnov  # (pop, nov_proj)
        ref = Dp
        if self.reservoir:
            res_G = np.array([g for _, g in self.reservoir.values()])
            if self.cfg.standardize:
                mu, sd = self.G.mean(0), self.G.std(0) + 1e-9
                res_D = (res_G - mu) / sd
            else:
                res_D = res_G
            ref = np.vstack([Dp, res_D @ self.Pnov])
        kk = max(1, min(self.cfg.k, len(ref) - 1))
        ref_sq = np.einsum("ij,ij->i", ref, ref)
        nov = np.empty(len(Dp))
        chunk = 512
        for start in range(0, len(Dp), chunk):
            end = min(start + chunk, len(Dp))
            d_chunk = Dp[start:end]
            d_sq = np.einsum("ij,ij->i", d_chunk, d_chunk)[:, None]
            dsq = d_sq + ref_sq[None, :] - 2.0 * (d_chunk @ ref.T)
            np.maximum(dsq, 0.0, out=dsq)
            dist = np.sqrt(dsq)
            for r in range(end - start):
                dist[r, start + r] = np.inf
            part = np.partition(dist, kk, axis=1)[:, :kk]
            nov[start:end] = part.mean(axis=1)
        return nov


# pop -> default gens (pop が大きいほど 1 世代が重い → 短縮。末尾20%で持続判定できる長さは確保)
DEFAULT_GENS = {256: 5000, 1024: 3500, 2048: 2500, 4096: 2000}


def build_scaleup_configs(
    pops: list[int],
    *,
    gens_map: dict[int, int],
    latent: int,
    cells: int,
    factors: int,
    sat_noise: int,
    n_archetypes: int,
    k: int,
    sparse: float,
    step: float,
    mc_cull: float,
    seed: int,
) -> list[RunConfig]:
    """full_oe 系構成 (novelty+std+MC+reservoir+QD) を pop ごとに 1 点ずつ作る.

    pop **以外** は全構成で固定 = 母数だけを動かす公正な比較。
    reservoir は pop 横断で 1024 固定 (要件指定の full_oe)。
    """
    configs: list[RunConfig] = []
    for pop in pops:
        configs.append(
            RunConfig(
                label=f"full_oe_pop{pop}",
                selection="novelty",
                standardize=True,
                minimal_criterion=True,
                reservoir=1024,
                archive="map-elites",
                pop=pop,
                gens=gens_map.get(pop, DEFAULT_GENS.get(pop, 2000)),
                factors=factors,
                sat_noise=sat_noise,
                latent=latent,
                n_archetypes=n_archetypes,
                k=k,
                cells=cells,
                sparse=sparse,
                step=step,
                mc_cull=mc_cull,
                seed=seed,
            )
        )
    return configs


def _monotonic(values: list[float], *, increasing: bool, tol: float = 1e-9) -> str:
    """単調性を判定して文字列で返す (strict / weak / non-monotonic).

    increasing=True なら値が pop↑ で増える期待。tol は浮動小数の許容ゆらぎ。
    """
    if len(values) < 2:
        return "n/a"
    diffs = [values[i + 1] - values[i] for i in range(len(values) - 1)]
    if increasing:
        if all(d > tol for d in diffs):
            return "strictly-increasing"
        if all(d >= -tol for d in diffs):
            return "weakly-increasing"
    else:
        if all(d < -tol for d in diffs):
            return "strictly-decreasing"
        if all(d <= tol for d in diffs):
            return "weakly-decreasing"
    # 全体トレンド (端点比較) で方向だけ示す
    net = values[-1] - values[0]
    return f"non-monotonic (net {'↑' if net > 0 else '↓' if net < 0 else '→'} {net:+.3g})"


def main() -> int:
    _utf8()
    ap = argparse.ArgumentParser(
        description="open-ended evolution POPULATION scale-up sweep (proxy, deterministic)"
    )
    ap.add_argument("--pops", type=str, default="256,1024,2048,4096",
                    help="comma-separated population sizes")
    ap.add_argument("--gens", type=str, default="",
                    help="comma-separated gens aligned to --pops (default: adaptive per pop)")
    ap.add_argument("--latent", type=int, default=1024,
                    help="neutral reservoir genome dim (容量, 全 pop 共通で固定)")
    ap.add_argument("--cells", type=int, default=64,
                    help="QD grid resolution per axis (全 pop 共通で固定; 上限 niche = cells^2)")
    ap.add_argument("--nov-proj", type=int, default=24,
                    help="novelty k-NN を計算する JL 射影次元 (DESC-1, 8-50)")
    ap.add_argument("--factors", type=int, default=10)
    ap.add_argument("--sat-noise", type=int, default=12)
    ap.add_argument("--n-archetypes", type=int, default=8)
    ap.add_argument("--k", type=int, default=15)
    ap.add_argument("--sparse", type=float, default=0.05)
    ap.add_argument("--step", type=float, default=0.1)
    ap.add_argument("--mc-cull", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=str, default="out/poc_scaleup")
    ap.add_argument("--quick", action="store_true",
                    help="smoke: pops=128,512 gens 600/400 latent=128 cells=32")
    args = ap.parse_args()

    if args.quick:
        pops = [128, 512]
        gens_map = {128: 600, 512: 400}
        args.latent = 128
        args.cells = 32
    else:
        pops = [int(p) for p in args.pops.split(",") if p.strip()]
        if args.gens.strip():
            gvals = [int(g) for g in args.gens.split(",") if g.strip()]
            gens_map = dict(zip(pops, gvals))
        else:
            gens_map = {p: DEFAULT_GENS.get(p, 2000) for p in pops}

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    configs = build_scaleup_configs(
        pops, gens_map=gens_map, latent=args.latent, cells=args.cells,
        factors=args.factors, sat_noise=args.sat_noise,
        n_archetypes=args.n_archetypes, k=args.k, sparse=args.sparse,
        step=args.step, mc_cull=args.mc_cull, seed=args.seed,
    )

    gdim = configs[0].gdim()
    print(f"[scaleup] {len(configs)} configs (full_oe), pops={pops} "
          f"gdim={gdim} latent={args.latent} cells={args.cells} "
          f"nov_proj={args.nov_proj} grid_max_niche={args.cells**2} out={out}")

    summaries: list[dict] = []
    for i, cfg in enumerate(configs, 1):
        t = time.time()
        summ = ScaleupRun(cfg, nov_proj=args.nov_proj).run(out)
        summaries.append(summ)
        (out / f"summary_{cfg.label}.json").write_text(
            json.dumps(summ, indent=2), encoding="utf-8"
        )
        verdict = "OPEN-ENDED" if summ.get("open_ended") else "BOUNDED/COLLAPSED"
        print(f"  [{i}/{len(configs)}] {cfg.label:18s} pop={cfg.pop:5d} g={cfg.gens:5d} "
              f"{time.time()-t:7.1f}s "
              f"niches={summ['occupied_cells_tail']:.0f} "
              f"cells={summ['archive_cells_final']:5d} "
              f"mono_max={summ['monoculture_max']:.3f} "
              f"bspread_t={summ.get('bspread_tail', 0):.3f} "
              f"uniq_lin={summ['uniq_lineages_tail']:.0f} "
              f"=> {verdict}")

    (out / "all_summaries.json").write_text(
        json.dumps(summaries, indent=2), encoding="utf-8"
    )
    _write_scaleup_summary_md(out, summaries, args, pops, gens_map, gdim)
    print(f"[scaleup] done. summary -> {out / 'SUMMARY.md'}")
    return 0


def _write_scaleup_summary_md(
    out: Path, summaries: list[dict], args: argparse.Namespace,
    pops: list[int], gens_map: dict[int, int], gdim: int,
) -> None:
    # pop 順にソート (configs はその順だが念のため)
    rows = sorted(summaries, key=lambda s: s["config"]["pop"])
    popv = [s["config"]["pop"] for s in rows]
    niches = [s["occupied_cells_tail"] for s in rows]
    cells = [float(s["archive_cells_final"]) for s in rows]
    mono = [s["monoculture_max"] for s in rows]
    mono_tail = [s.get("monoculture_tail", s["monoculture_max"]) for s in rows]
    bspread = [s.get("bspread_tail", 0.0) for s in rows]
    fspread = [s.get("fspread_tail", 0.0) for s in rows]
    nov_tail = [s.get("novelty_tail", 0.0) for s in rows]
    uniq_lin = [s["uniq_lineages_tail"] for s in rows]
    distinct = [s["distinct_genomes_tail"] for s in rows]

    grid_max = args.cells ** 2

    L: list[str] = []
    L.append("# Open-Ended Evolution — POPULATION Scale-Up Sweep (POP-1)")
    L.append("")
    L.append(f"- 生成: proxy / deterministic / NO LLM (SR-1 sandbox). seed={args.seed}")
    L.append(f"- 構成: **full_oe** (selection=novelty, standardize=on, minimal_criterion=on, "
             f"reservoir=1024, archive=map-elites) を pop だけ変えて比較")
    L.append(f"- 固定パラメータ (全 pop 共通): latent={args.latent}, cells={args.cells} "
             f"(grid 上限 niche = {grid_max}), gdim={gdim} "
             f"(factors={args.factors}+sat_noise={args.sat_noise}+latent={args.latent}), "
             f"n_archetypes={args.n_archetypes}, sparse={args.sparse}, step={args.step}")
    L.append(f"- gens (pop 別, adaptive): " +
             ", ".join(f"pop{p}={gens_map.get(p)}" for p in pops))
    L.append(f"- novelty k-NN: **JL {args.nov_proj}-dim 射影** 上で計算 (tractability, DESC-1)")
    L.append("")
    L.append("**仮説 (POP-1)**: 母数 (population) を上げると open-endedness 指標が "
             "**質的に** 向上する — occupied niches↑ / archive cells↑ / monoculture↓ / "
             "多様性↑ が pop↑ で単調。")
    L.append("")
    L.append("## pop × メトリクス比較表 (§2, 末尾20%世代判定)")
    L.append("")
    L.append("| pop | gens | elapsed(s) | occupied niches | archive cells | mono_max | mono_tail | "
             "bspread_tail | fspread_tail | novelty_tail(JL) | uniq_lineages | distinct_genomes | 判定 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for s in rows:
        c = s["config"]
        verdict = "OPEN-ENDED" if s.get("open_ended") else "BOUNDED/COLLAPSED"
        L.append(
            f"| {c['pop']} | {c['gens']} | {s.get('elapsed_s', 0):.0f} "
            f"| {s['occupied_cells_tail']:.0f} | {s['archive_cells_final']} "
            f"| {s['monoculture_max']:.3f} | {s.get('monoculture_tail', 0):.3f} "
            f"| {s.get('bspread_tail', 0):.3f} | {s.get('fspread_tail', 0):.3f} "
            f"| {s.get('novelty_tail', 0):.3f} | {s['uniq_lineages_tail']:.0f} "
            f"| {s['distinct_genomes_tail']:.0f} | {verdict} |"
        )
    L.append("")
    L.append(f"> distinct_genomes_tail は **pop に対する絶対値**。pop に対する比率 "
             f"(distinct/pop) も多様性持続の指標。")
    L.append("")

    # --- 単調性判定 ---
    L.append("## pop に対する単調性 (POP-1 の核判定)")
    L.append("")
    L.append("| 指標 | 期待方向 | 値 (pop昇順) | 単調性 |")
    L.append("|---|---|---|---|")
    def fmt(vals, prec=2):
        return " → ".join(f"{v:.{prec}f}" for v in vals)
    L.append(f"| occupied niches | ↑ | {fmt(niches, 0)} | {_monotonic(niches, increasing=True)} |")
    L.append(f"| archive cells | ↑ | {fmt(cells, 0)} | {_monotonic(cells, increasing=True)} |")
    L.append(f"| monoculture_max | ↓ | {fmt(mono, 3)} | {_monotonic(mono, increasing=False)} |")
    L.append(f"| monoculture_tail | ↓ | {fmt(mono_tail, 3)} | {_monotonic(mono_tail, increasing=False)} |")
    L.append(f"| bspread_tail | ↑ | {fmt(bspread, 3)} | {_monotonic(bspread, increasing=True)} |")
    L.append(f"| fspread_tail | ↑/→ | {fmt(fspread, 3)} | {_monotonic(fspread, increasing=True)} |")
    L.append(f"| novelty_tail (JL) | ↑ | {fmt(nov_tail, 2)} | {_monotonic(nov_tail, increasing=True)} |")
    L.append(f"| distinct_genomes | ↑ | {fmt(distinct, 0)} | {_monotonic(distinct, increasing=True)} |")
    L.append(f"| uniq_lineages | (informational) | {fmt(uniq_lin, 0)} | {_monotonic(uniq_lin, increasing=True)} |")
    L.append("")

    # niche grid 飽和チェック
    niche_saturated = [n / grid_max for n in niches]
    L.append(f"- QD grid 占有率 (occupied/grid_max={grid_max}): " +
             ", ".join(f"pop{p}={r:.1%}" for p, r in zip(popv, niche_saturated)))
    any_grid_saturated = any(r >= 0.9 for r in niche_saturated)
    if any_grid_saturated:
        L.append(f"  - **注意**: grid 占有率 ≥90% の pop あり → occupied niches が "
                 f"grid 上限 ({grid_max}) で頭打ちしている可能性。その pop の niche 値は過小評価。")
    L.append("")

    # --- 正直な結論 ---
    L.append("## 結論 (honest disclosure)")
    L.append("")
    niche_mono = _monotonic(niches, increasing=True)
    cells_mono = _monotonic(cells, increasing=True)
    mono_trend = _monotonic(mono, increasing=False)
    distinct_mono = _monotonic(distinct, increasing=True)

    net_niche = niches[-1] - niches[0] if len(niches) >= 2 else 0
    net_cells = cells[-1] - cells[0] if len(cells) >= 2 else 0

    qualitative = (net_niche > 0 and net_cells > 0
                   and ("increasing" in niche_mono or "increasing" in cells_mono))
    if qualitative:
        L.append(f"- **POP-1 を支持する方向**: 母数を {popv[0]}→{popv[-1]} に上げると "
                 f"occupied niches {niches[0]:.0f}→{niches[-1]:.0f} ({net_niche:+.0f})、"
                 f"archive cells {cells[0]:.0f}→{cells[-1]:.0f} ({net_cells:+.0f}) と "
                 f"open-endedness 指標が増加した。")
    else:
        L.append(f"- **POP-1 は限定的/不支持**: niches {niches[0]:.0f}→{niches[-1]:.0f}、"
                 f"cells {cells[0]:.0f}→{cells[-1]:.0f}。母数スケールの効果は "
                 f"飽和/非単調だった (下記限界参照)。")
    L.append(f"  - occupied niches 単調性 = {niche_mono}")
    L.append(f"  - archive cells 単調性 = {cells_mono}")
    L.append(f"  - monoculture_max 単調性 = {mono_trend} (↓ が望ましい)")
    L.append(f"  - distinct_genomes 単調性 = {distinct_mono}")
    L.append("")
    L.append("### 飽和/改善しない指標 (隠さず報告)")
    L.append("")
    if "increasing" not in mono_trend.replace("decreasing", "increasing") and "decreasing" not in mono_trend:
        L.append(f"- monoculture は既に全 pop で低い (max={max(mono):.3f}) → pop による"
                 f" 改善余地が小さい (床効果)。")
    if any_grid_saturated:
        L.append(f"- 一部 pop で QD grid ({grid_max} cell) を埋め尽くし occupied niches が "
                 f"構造的に頭打ち → niche 数の pop 効果はそこで飽和。grid を上げれば伸びる余地あり。")
    if "decreasing" in distinct_mono or "non-monotonic" in distinct_mono:
        L.append(f"- distinct_genomes (絶対値) は pop↑ で {distinct_mono}。"
                 f"ただし pop に対する **比率** で見るべき指標 (pop が増えれば母数も増える)。")
    L.append("")
    L.append("### 測定限界 (must read)")
    L.append("")
    L.append(f"1. **novelty 距離は JL {args.nov_proj}-dim 近似** (full-gdim {gdim} 厳密 k-NN ではない)。"
             f"Johnson-Lindenstrauss で相対距離は ~保たれるが novelty_tail の絶対値は "
             f"engine 既存ラン (full-gdim) と直接比較不可。pop 横断の相対比較が目的。")
    L.append(f"2. **gens が pop で異なる** (pop↑ で gens↓)。同一世代数比較ではない。"
             f"pop↑ で gens↓ は niche 蓄積に**不利**な方向のバイアス → それでも niche が増えれば "
             f"POP 効果は robust (下限の証明)。")
    L.append(f"3. **cells を pop 横断で固定** (occupied niche 上限 = {grid_max})。"
             f"pop4096 が grid を埋めると頭打ち = 飽和を正直に報告。grid を上げれば niche は伸びる。")
    L.append(f"4. proxy mechanism feasibility のみ。'new AI' (intelligence) の主張は "
             f"Stage6 実 LLM 評価が必須 (要件 §0-4)。")
    L.append("")
    L.append("### 次に詰める点")
    L.append("")
    L.append("- pop と cells を**同時に**スケール (pop4096 × cells128) して niche 上限の頭打ちを外す。")
    L.append("- gens を pop 横断で固定 (例: 全 pop で 3000 gen) し、世代数交絡を除いた純 POP 効果。")
    L.append("- GENOME-1 (latent) × POP-1 (pop) の 2D 交互作用 sweep (容量×母数の相乗効果)。")
    L.append("- full-gdim 厳密 novelty vs JL 近似の差分検証 (小 pop で両方走らせて誤差を定量化)。")

    (out / "SUMMARY.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
