#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""PoC: can DATA-DRIVEN (AURORA-style) behavior descriptors keep QD coverage without
hand-designing the descriptor axes?

Smallest falsifiable test of the "unsupervised behavior characterization" element of
Quality-Diversity ([[feedback_staged_poc_individual_structure]] / [[feedback_benchmark_honest_disclosure]]).

Background: in MAP-Elites / QD you must pick the *behavior descriptor* — the low-dim
axes the archive is binned along. Hand-picking them is brittle: if you guess the wrong
axes, the archive bins along directions that barely vary and the population collapses
into a few cells (low coverage) even though behavior is actually diverse. AURORA
(Cully 2019, "Autonomous skill discovery with QD and unsupervised descriptors") instead
*learns* the descriptor from collected behavior signals (an autoencoder) and periodically
re-fits it as the archive grows (container refresh).

Proposition (falsifiable):

  「行動信号からデータ駆動で低次元記述子を学習 (PCA / numpy SVD) し periodic に refresh
    して QD archive を張ると、(a) ハンドコード記述子が *取りこぼす* 行動分散軸を捉え、
    (b) アーカイブ coverage / 行動多様性がハンドコード記述子と同等以上になる。
    = 記述子を手で設計せずに QD の被覆を保てる。」

Design (stdlib + numpy, deterministic seed, ZERO llive imports = isolated toy):
* 個体 -> 行動信号 b in R^D (D=8-16). 重要な行動分散は HANDCODED が選ばない軸に乗せる
  (= ハンドコードの盲点を意図的に作る): high-variance latent factors を回転行列で
  全 D 次元に拡散させ、handcoded が固定で取る 2 次元には低分散ノイズしか乗らないようにする。
* HANDCODED 記述子 = b の固定 2 次元 (dims 0,1) を取る。盲点軸 (high-variance 回転後の軸)
  には殆ど整列しないので archive がごく少数セルに潰れる。
* AURORA 記述子 = 収集済 behavior 群に PCA (numpy SVD) をかけ上位 2 主成分へ射影。
  archive 拡大に応じ periodic に再 fit (= AURORA の container refresh) を最小実装。
* QD archive = 各記述子で 2D グリッド MAP-Elites (同一解像度・同一個体集合 = fair)。
  個体は決定論的 RNG で生成 + 軽い変異 (toy)。両 archive に同じ個体を submit する。
* metric = archive coverage (占有セル数 / 全セル数) と captured variance (記述子が説明する
  b の分散割合)、および handcoded が取りこぼす盲点軸の分散を AURORA が捉えるか。
* verdict (決定論): AURORA coverage >= HANDCODED coverage かつ AURORA captured variance >
  HANDCODED captured variance (= 盲点軸を捉える). -> aurora_matches_or_beats_handcoded.

同等以上にならなければ honest にそう報告する (feedback_benchmark_honest_disclosure)。

    py -3.11 scripts/poc_aurora_descriptors.py
    py -3.11 scripts/poc_aurora_descriptors.py --gens 600 --seed 1
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
# behavior generator: build a blind spot for the handcoded descriptor
# ---------------------------------------------------------------------------
def _random_orthonormal(d: int, rng: np.random.Generator) -> np.ndarray:
    """A deterministic random orthonormal (rotation) matrix via QR of a Gaussian.

    Used to SPREAD the high-variance latent behavior factors across ALL D observed
    dimensions, so that no single observed axis (and in particular NOT the fixed dims the
    handcoded descriptor reads) is aligned with a dominant factor. This is what creates
    the handcoded descriptor's "blind spot".
    """
    a = rng.normal(0.0, 1.0, (d, d))
    q, r = np.linalg.qr(a)
    # fix sign so the rotation is deterministic (QR sign is otherwise ambiguous).
    q = q * np.sign(np.diag(r))[None, :]
    return q


def generate_behaviors(
    *, n: int, d: int, n_factors: int, seed: int, hi_var: float, lo_var: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Generate n behavior vectors b in R^d with the diversity hidden off the handcoded axes.

    Construction (a deliberate, honestly-documented blind spot for the handcoded descriptor):
      * the FIRST 2 observed dims (0,1) — exactly the ones the handcoded descriptor reads —
        carry ONLY low-variance noise (`lo_var`). This models a human who picked the wrong
        (low-variance) behavior axes.
      * the REMAINING d-2 dims carry the real behavior diversity: `n_factors` high-variance
        latent factors (`hi_var`) spread across the d-2 subspace by a fixed deterministic
        rotation, plus low-variance noise on the rest of that subspace. The rotation makes
        the variance NOT axis-aligned, so PCA must actually *discover* the directions (it
        can't just read off a coordinate) — this is AURORA's real job.

    The blind spot is therefore explicit and falsifiable: handcoded sees only noise; AURORA
    must recover the rotated high-variance structure in the complementary subspace.

    Returns (behaviors b (n,d), rotation R ((d-2),(d-2)), latent (n,d)).
    """
    rng = np.random.default_rng(seed)
    rest = d - 2
    nf = min(n_factors, rest)
    # latent behavior factors: nf high-variance factors carry the REAL diversity, the rest
    # are low-variance noise. These live in the (d-2) complementary subspace.
    latent_rest = np.empty((n, rest))
    latent_rest[:, :nf] = rng.normal(0.0, hi_var, (n, nf))           # high-variance factors
    latent_rest[:, nf:] = rng.normal(0.0, lo_var, (n, rest - nf))    # low-variance noise

    behaviors = np.empty((n, d))
    # dims 0,1 = the handcoded descriptor's axes = the BLIND SPOT. They are a near-DEGENERATE
    # (collinear) low-variance readout: both are the SAME high-variance factor scaled down by
    # `lo_var`, plus a touch of independent noise. Result: dims 0,1 are highly correlated and
    # low-variance, so binning on them collapses individuals onto a near-1D diagonal -> few
    # occupied cells. This models a human who picked two axes that (a) barely vary and (b) are
    # redundant with each other — a realistic bad descriptor choice (NOT pure i.i.d. noise,
    # which would spuriously spread across the grid and inflate coverage).
    shared = latent_rest[:, 0]                                       # one real factor
    behaviors[:, 0] = lo_var * shared + rng.normal(0.0, lo_var * 0.1, n)
    behaviors[:, 1] = lo_var * shared + rng.normal(0.0, lo_var * 0.1, n)
    # remaining d-2 dims = where the real behavior diversity lives, ROTATED so the variance is
    # NOT axis-aligned -> PCA (AURORA) must discover the directions, it can't read a coord off.
    R = _random_orthonormal(rest, rng)
    behaviors[:, 2:] = latent_rest @ R.T
    latent = np.hstack([behaviors[:, :2], latent_rest])
    return behaviors, R, latent


# ---------------------------------------------------------------------------
# descriptors: handcoded (fixed dims) vs AURORA (learned PCA projection)
# ---------------------------------------------------------------------------
def handcoded_descriptor(behaviors: np.ndarray, dims: tuple[int, int] = (0, 1)) -> np.ndarray:
    """Hand-picked descriptor = take two FIXED observed dims of b. (n,2)."""
    return behaviors[:, list(dims)].copy()


def fit_pca(behaviors: np.ndarray, k: int = 2) -> tuple[np.ndarray, np.ndarray]:
    """Fit PCA on collected behaviors via numpy SVD. Return (mean (d,), components (k,d)).

    Components are the top-k right singular vectors of the centered data — the directions
    of maximum variance. This is the linear AURORA descriptor learner. Deterministic for a
    fixed input (SVD sign is pinned below for reproducibility).
    """
    mean = behaviors.mean(axis=0)
    centered = behaviors - mean
    # economy SVD: U(n,r) S(r) Vt(r,d); rows of Vt are principal directions.
    _u, _s, vt = np.linalg.svd(centered, full_matrices=False)
    comps = vt[:k].copy()
    # pin sign deterministically: make the largest-magnitude entry of each component
    # positive (SVD sign is otherwise arbitrary -> non-deterministic projections).
    for i in range(comps.shape[0]):
        j = int(np.argmax(np.abs(comps[i])))
        if comps[i, j] < 0:
            comps[i] = -comps[i]
    return mean, comps


def pca_project(behaviors: np.ndarray, mean: np.ndarray, comps: np.ndarray) -> np.ndarray:
    """Project behaviors onto the learned PCA components. (n,k)."""
    return (behaviors - mean) @ comps.T


# ---------------------------------------------------------------------------
# QD archive: 2D grid MAP-Elites coverage over a descriptor space
# ---------------------------------------------------------------------------
def grid_coverage(descriptors: np.ndarray, *, bins: int) -> tuple[float, int, int]:
    """Occupied-cell fraction of a `bins`x`bins` MAP-Elites grid over the descriptor space.

    The grid spans the OBSERVED range of the supplied descriptors (min..max per axis), so
    each descriptor is given its own fair, fully-utilised extent — coverage is not
    penalised for a descriptor whose raw scale happens to be small. What it measures is
    how well the descriptor SPREADS the individuals across distinct cells. A descriptor
    aligned with low-variance (blind-spot) directions collapses individuals into few cells
    even after range-normalisation, because the points are nearly degenerate along those
    axes relative to the noise floor.

    Returns (coverage_fraction, occupied_cells, total_cells).
    """
    total = bins * bins
    if descriptors.shape[0] == 0:
        return 0.0, 0, total
    lo = descriptors.min(axis=0)
    hi = descriptors.max(axis=0)
    span = hi - lo
    # guard against a degenerate (zero-span) axis -> all points map to bin 0 on that axis.
    span = np.where(span <= 1e-12, 1.0, span)
    norm = (descriptors - lo) / span  # in [0,1]
    idx = np.clip((norm * bins).astype(int), 0, bins - 1)  # (n,2) cell indices
    cells = idx[:, 0] * bins + idx[:, 1]
    occupied = int(np.unique(cells).size)
    return occupied / total, occupied, total


def captured_variance(behaviors: np.ndarray, descriptors: np.ndarray) -> float:
    """Fraction of total behavior variance that the 2D descriptor linearly captures.

    = sum of variances of the descriptor coords / total variance of b. For PCA this is
    the explained-variance ratio of the top-2 PCs; for the handcoded descriptor it is the
    variance of the two fixed dims relative to the whole behavior vector. This is the
    direct measure of whether the descriptor sits on the high-variance behavior axes
    (AURORA's claim) or on a blind spot (handcoded failure mode).
    """
    total = float(np.sum(np.var(behaviors, axis=0)))
    if total <= 0.0:
        return 0.0
    cap = float(np.sum(np.var(descriptors, axis=0)))
    return cap / total


# ---------------------------------------------------------------------------
# AURORA container refresh: periodic re-fit of the descriptor as the archive grows
# ---------------------------------------------------------------------------
def run_aurora_with_refresh(
    *,
    behaviors: np.ndarray,
    bins: int,
    refresh_every: int,
    batch: int,
) -> dict:
    """Stream behaviors in batches, periodically re-fitting PCA (AURORA container refresh).

    This is the minimal version of AURORA's container refresh: as new behaviors arrive the
    descriptor is re-learned on everything seen so far, then the WHOLE archive is re-binned
    under the new descriptor (AURORA re-projects every elite on refresh). We record the
    refresh history (coverage after each refresh) and the final coverage / captured
    variance under the last-fitted descriptor.
    """
    n = behaviors.shape[0]
    history: list[dict] = []
    mean = comps = None
    seen = 0
    next_refresh = 0
    for start in range(0, n, batch):
        seen = min(start + batch, n)
        if seen >= next_refresh:
            # re-fit the descriptor on everything collected so far (container refresh).
            mean, comps = fit_pca(behaviors[:seen], k=2)
            next_refresh = seen + refresh_every
            proj = pca_project(behaviors[:seen], mean, comps)
            cov, occ, tot = grid_coverage(proj, bins=bins)
            history.append(
                {"after_n": seen, "coverage": round(cov, 4), "occupied": occ, "total": tot}
            )
    # final descriptor = last fit; project the FULL collected set.
    assert mean is not None and comps is not None
    proj_full = pca_project(behaviors, mean, comps)
    cov, occ, tot = grid_coverage(proj_full, bins=bins)
    var = captured_variance(behaviors, proj_full)
    return {
        "coverage": cov,
        "occupied": occ,
        "total": tot,
        "captured_variance": var,
        "n_refreshes": len(history),
        "refresh_history": history,
        "mean": mean,
        "comps": comps,
    }


# ---------------------------------------------------------------------------
# verdict
# ---------------------------------------------------------------------------
def build_verdict(handcoded: dict, aurora: dict) -> dict:
    """Deterministic verdict: AURORA matches-or-beats handcoded on BOTH coverage and the
    captured-variance (blind-spot) test.

    (a) blind-spot capture: AURORA captured variance STRICTLY exceeds handcoded — AURORA's
        learned axes sit on the high-variance behavior directions the fixed handcoded dims
        miss.
    (b) coverage: AURORA coverage >= handcoded coverage — learning the descriptor does not
        cost archive coverage (and here, recovers the coverage handcoded loses to its blind
        spot).
    """
    cov_ok = aurora["coverage"] >= handcoded["coverage"]
    var_ok = aurora["captured_variance"] > handcoded["captured_variance"]
    aurora_matches_or_beats = bool(cov_ok and var_ok)
    return {
        "handcoded_coverage": round(handcoded["coverage"], 4),
        "aurora_coverage": round(aurora["coverage"], 4),
        "handcoded_occupied_cells": handcoded["occupied"],
        "aurora_occupied_cells": aurora["occupied"],
        "total_cells": handcoded["total"],
        "handcoded_captured_variance": round(handcoded["captured_variance"], 4),
        "aurora_captured_variance": round(aurora["captured_variance"], 4),
        "coverage_ratio_aurora_over_handcoded": round(
            aurora["coverage"] / (handcoded["coverage"] + 1e-9), 4
        ),
        "variance_ratio_aurora_over_handcoded": round(
            aurora["captured_variance"] / (handcoded["captured_variance"] + 1e-9), 4
        ),
        "coverage_non_inferior": bool(cov_ok),
        "captures_blind_spot": bool(var_ok),
        "aurora_matches_or_beats_handcoded": aurora_matches_or_beats,
    }


def run(
    *,
    n: int = 800,
    d: int = 12,
    n_factors: int = 4,
    bins: int = 16,
    seed: int = 0,
    hi_var: float = 1.0,
    lo_var: float = 0.02,
    refresh_every: int = 200,
    batch: int = 100,
) -> dict:
    """Build behaviors with a handcoded blind spot, bin both descriptors, return result."""
    behaviors, R, _latent = generate_behaviors(
        n=n, d=d, n_factors=n_factors, seed=seed, hi_var=hi_var, lo_var=lo_var
    )

    # --- HANDCODED arm: fixed dims (0,1) -> archive ---
    hc_desc = handcoded_descriptor(behaviors, dims=(0, 1))
    hc_cov, hc_occ, hc_tot = grid_coverage(hc_desc, bins=bins)
    hc_var = captured_variance(behaviors, hc_desc)
    handcoded = {
        "coverage": hc_cov,
        "occupied": hc_occ,
        "total": hc_tot,
        "captured_variance": hc_var,
    }

    # --- AURORA arm: learned PCA descriptor with periodic container refresh ---
    aurora = run_aurora_with_refresh(
        behaviors=behaviors, bins=bins, refresh_every=refresh_every, batch=batch
    )

    verdict = build_verdict(handcoded, aurora)

    return {
        "schema": "poc_aurora_descriptors/v1",
        "proposition": (
            "行動信号からデータ駆動で低次元記述子を学習 (PCA/SVD) し periodic に refresh して "
            "QD archive を張ると、(a) ハンドコード記述子が取りこぼす行動分散軸を捉え、(b) "
            "archive coverage / 行動多様性がハンドコード記述子と同等以上になる "
            "(= 記述子を手で設計せずに QD の被覆を保てる)。"
        ),
        "config": {
            "n": n, "d": d, "n_factors": n_factors, "bins": bins, "seed": seed,
            "hi_var": hi_var, "lo_var": lo_var,
            "refresh_every": refresh_every, "batch": batch,
        },
        "handcoded": {
            "descriptor": "fixed dims (0,1) of behavior vector",
            "coverage": round(handcoded["coverage"], 4),
            "occupied_cells": handcoded["occupied"],
            "total_cells": handcoded["total"],
            "captured_variance": round(handcoded["captured_variance"], 4),
        },
        "aurora": {
            "descriptor": "learned top-2 PCA components (numpy SVD), periodic refresh",
            "coverage": round(aurora["coverage"], 4),
            "occupied_cells": aurora["occupied"],
            "total_cells": aurora["total"],
            "captured_variance": round(aurora["captured_variance"], 4),
            "n_refreshes": aurora["n_refreshes"],
            "refresh_history": aurora["refresh_history"],
        },
        "verdict": verdict,
        "honest_notes": [
            "proxy toy・実 llive 非接触 (import ゼロ)。データ駆動記述子が手設計の盲点を捉え "
            "QD coverage を保てる『機構の feasibility』を示すもので、実 llive 行動での "
            "主張ではない。",
            "PCA は線形。本家 AURORA は autoencoder (非線形) で記述子を学習する。よって本 "
            "PoC は『データから記述子を学ぶと手設計の盲点を捉えうる』線形版の feasibility の "
            "みを示し、非線形 manifold での挙動は別途要検証 (line: PCA は線形部分空間しか "
            "捉えられない)。",
            "盲点は意図的に構成: high-variance latent factors を直交回転で全 D 次元へ拡散させ、"
            "handcoded が固定で読む 2 次元には high-variance 成分が薄くしか乗らないようにした。"
            "実 llive 行動信号で handcoded がこれほど不利かは未検証 (= toy の設計上の優位)。",
            "coverage は各記述子の OBSERVED range を 16x16 グリッドに張る (range-normalised) "
            "ので、生スケールの大小では不利にならない fair な比較。測っているのは『個体を異なる "
            "セルにどれだけ広く散らすか』。",
            "captured_variance = 記述子 2 座標の分散和 / b 全分散。PCA では top-2 PC の "
            "explained-variance ratio、handcoded では固定 2 次元の分散割合 = 記述子が "
            "high-variance 行動軸に乗っているかの直接指標。",
            "container refresh は最小実装: 新 batch 到着ごとに全既収集 behavior で PCA を "
            "再 fit し全 archive を再 binning (AURORA は refresh で全 elite を再射影する)。",
            "SVD の符号は決定論的に固定 (各 component の最大絶対値要素を正に) — そうしないと "
            "射影の符号が実行毎に揺れて非決定論になる。",
            "次段 = 実 llive 個体の行動信号 (出力埋め込み / lineage / 思考因子軌跡) を behavior "
            "ベクトルに配線し、descriptor-router 資産へ接続する。",
            "verdict が False なら命題は inconclusive/falsified — honest にそう報告する "
            "(aurora_matches_or_beats_handcoded=False で表現)。",
        ],
    }


def _print(out: dict) -> None:
    v = out["verdict"]
    c = out["config"]
    print("\n===== AURORA-style data-driven descriptor PoC — PROXY, deterministic =====")
    print(f"n={c['n']} d={c['d']} n_factors={c['n_factors']} bins={c['bins']}x{c['bins']} "
          f"seed={c['seed']} refresh_every={c['refresh_every']} batch={c['batch']}")
    print("\n[QD archive coverage — occupied cells / total grid cells (range-normalised)]")
    print(f"  {'descriptor':12s} {'coverage':>9s} {'occupied':>9s} {'total':>7s} "
          f"{'capt.var':>9s}")
    print(f"  {'handcoded':12s} {v['handcoded_coverage']:9.4f} "
          f"{v['handcoded_occupied_cells']:9d} {v['total_cells']:7d} "
          f"{v['handcoded_captured_variance']:9.4f}")
    print(f"  {'AURORA':12s} {v['aurora_coverage']:9.4f} "
          f"{v['aurora_occupied_cells']:9d} {v['total_cells']:7d} "
          f"{v['aurora_captured_variance']:9.4f}")
    print(f"\n  coverage ratio AURORA/handcoded   = "
          f"{v['coverage_ratio_aurora_over_handcoded']:.2f}x")
    print(f"  capt.var ratio AURORA/handcoded   = "
          f"{v['variance_ratio_aurora_over_handcoded']:.2f}x")
    print(f"  coverage_non_inferior (>=)        = {v['coverage_non_inferior']}")
    print(f"  captures_blind_spot (var >)       = {v['captures_blind_spot']}")
    print(f"  AURORA refreshes                  = {out['aurora']['n_refreshes']}")
    print(f"\n  VERDICT aurora_matches_or_beats_handcoded = "
          f"{v['aurora_matches_or_beats_handcoded']}")
    if v["aurora_matches_or_beats_handcoded"]:
        print("  → データ駆動 (PCA) 記述子は手設計が取りこぼす high-variance 行動軸を捉え、"
              "archive coverage も同等以上 = 記述子を手で設計せずに QD 被覆を保てる "
              "(機構 feasibility あり)。")
    else:
        print("  → この設定では AURORA が handcoded を coverage+captured variance で同等以上に "
              "できなかった。honest に記録 (命題は falsified or inconclusive)。")
    print("  honest: proxy mechanism test only; PCA は線形 (本家 AURORA は非線形 AE)。"
          "実 llive 非接触。")


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    ap = argparse.ArgumentParser(
        description="AURORA-style data-driven QD descriptor PoC (PCA vs handcoded)"
    )
    ap.add_argument("--n", type=int, default=800)
    ap.add_argument("--d", type=int, default=12)
    ap.add_argument("--n-factors", type=int, default=4)
    ap.add_argument("--bins", type=int, default=16)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--hi-var", type=float, default=1.0)
    ap.add_argument("--lo-var", type=float, default=0.02)
    ap.add_argument("--refresh-every", type=int, default=200)
    ap.add_argument("--batch", type=int, default=100)
    ap.add_argument("--out", type=Path,
                    default=Path(r"D:/projects/llive/out/poc_aurora_descriptors"))
    args = ap.parse_args(argv)

    out = run(
        n=args.n, d=args.d, n_factors=args.n_factors, bins=args.bins, seed=args.seed,
        hi_var=args.hi_var, lo_var=args.lo_var,
        refresh_every=args.refresh_every, batch=args.batch,
    )

    args.out.mkdir(parents=True, exist_ok=True)
    out_json = args.out / "aurora.json"
    out_json.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    _print(out)
    print(f"\n[poc_aurora] wrote {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
