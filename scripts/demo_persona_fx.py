# SPDX-License-Identifier: Apache-2.0
"""PERSONA-FX PoC — 文化的ペルソナ獲得の機構検証 (隔離・合成・falsifiable).

設計: fullsense `docs/vision/PERSONA_FX.md`。
核: ペルソナは遺伝しない。プールから、平均を外れた個性的な個体が相関で persona を獲得する
(各 persona が独立に「相関最大の個性的個体」を argmax で選ぶ = per-persona argmax)。

検証する falsifiable 主張:
  U  persona 側 uniqueness — 各 persona の bearer は最大 1 体 (被らない)
  M  個体多重の創発 — 個体は 0/1/≥2 persona を持ちうる (多才 hub / generic)
  D  隔世 — 相関個体が居なければ休眠、後世で出現すれば再付与
  H  退化診断 — 集団が収束すると 1 個体が多数 persona を総取り (偏りが跳ねる)

HONEST DISCLOSURE: 合成 factor ベクトル / proxy。実 LLM・実 genome ループに非接触
(EvolutionLoop/genome を一切 import しない)。本 PoC は *機構の feasibility と創発特性*
を検証するもので production 値ではない。stdlib + numpy のみ、決定論的 (seed)。

    py -3.11 scripts/demo_persona_fx.py
"""
from __future__ import annotations

import sys

import numpy as np

FACTOR_DIM = 10


# --- 機構 (per-persona argmax) ---------------------------------------------


def deviation(pop: np.ndarray) -> np.ndarray:
    """各個体の centroid からの距離 (= 平均からの逸脱 = novelty 代用)."""
    if len(pop) == 0:
        return np.zeros(0)
    return np.linalg.norm(pop - pop.mean(axis=0), axis=1)


def eligible_idx(pop: np.ndarray, top_p: float = 0.5) -> np.ndarray:
    """逸脱が大きい (個性的な) top_p 割合の個体 index."""
    d = deviation(pop)
    if len(d) == 0:
        return np.zeros(0, dtype=int)
    thr = np.quantile(d, 1.0 - top_p)
    return np.where(d >= thr)[0]


def _cosine(vec: np.ndarray, mat: np.ndarray) -> np.ndarray:
    """vec:(D,) と mat:(K,D) の cosine 類似 (K,)."""
    v = vec / (np.linalg.norm(vec) + 1e-12)
    m = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-12)
    return m @ v


def assign(
    pop: np.ndarray,
    personas: np.ndarray,
    *,
    top_p: float = 0.5,
    corr_threshold: float = 0.5,
) -> dict[int, int | None]:
    """各 persona が独立に eligible 個体の相関最大を argmax (しきい値超) で選ぶ.

    返り: persona_idx -> individual_idx (None = 休眠: 相関する個性的個体が居ない).
    persona ごとに 1 エントリなので persona の重複は構造的に起きない (U)。
    個体は複数 persona から選ばれうる (M) / 一度も選ばれないこともある (generic)。
    """
    elig = eligible_idx(pop, top_p)
    out: dict[int, int | None] = {}
    for p, proto in enumerate(personas):
        if len(elig) == 0:
            out[p] = None
            continue
        corr = _cosine(proto, pop[elig])
        best = int(np.argmax(corr))
        out[p] = int(elig[best]) if corr[best] >= corr_threshold else None
    return out


def multiplicity(assignment: dict[int, int | None], n: int) -> np.ndarray:
    """per-individual の persona 数 (0..N)."""
    counts = np.zeros(n, dtype=int)
    for ind in assignment.values():
        if ind is not None:
            counts[ind] += 1
    return counts


# --- 検証デモ ----------------------------------------------------------------


def _unit(i: int) -> np.ndarray:
    v = np.zeros(FACTOR_DIM)
    v[i] = 1.0
    return v


def main() -> int:
    rng = np.random.default_rng(0)
    print("# PERSONA-FX PoC (synthetic, proxy — NOT production)\n")

    # personas: 3 つの直交プロトタイプ (factor 0 / 1 / 2 方向)
    personas = np.stack([_unit(0), _unit(1), _unit(2)])

    # ---- U + M: specialist(p0) + polymath(p1&p2 を兼任) + generic 群 ----
    specialist0 = _unit(0) * 1.0                       # p0 の専門家 (cos≈1)
    polymath = (_unit(1) + _unit(2)) / np.sqrt(2)      # p1,p2 に中程度相関 (cos≈0.71)
    generics = rng.normal(0, 0.03, size=(8, FACTOR_DIM)) + 0.5  # 平均近傍 (低逸脱)
    pop = np.vstack([specialist0, polymath, generics])  # idx0=specialist, idx1=polymath
    a = assign(pop, personas, top_p=0.5, corr_threshold=0.5)
    counts = multiplicity(a, len(pop))
    print(f"[U/M] assignment={a}")
    print(f"[U/M] per-individual persona counts={counts.tolist()}")

    # U: 各 persona の bearer は最大 1 (構造的に dict 1 entry/persona)
    assert all(v is None or isinstance(v, int) for v in a.values())
    # M: 多重が創発 — polymath(idx1) が 2 persona、generic は 0、混在
    assert counts.max() >= 2, "polymath が複数 persona を帯びるはず"
    assert counts.min() == 0, "generic 個体は 0 persona のはず"
    assert a[0] == 0, "p0 は specialist(idx0) に付くはず"
    assert a[1] == 1 and a[2] == 1, "p1,p2 は polymath(idx1) を兼任するはず"
    print("  -> U(被らない) + M(多才 hub と generic の創発) OK\n")

    # ---- D: 隔世 (休眠 → 後世で再付与) ----
    persona_x = _unit(5)[None, :]                      # factor5 方向の persona
    # phase1: factor5 に相関する個体が居ない (全員 factor0-2 中心)
    pop1 = np.vstack([specialist0, polymath, generics])
    d1 = assign(pop1, persona_x, top_p=0.5, corr_threshold=0.5)
    # phase2: factor5 に強く相関する個体が後世で出現
    newcomer = _unit(5) * 1.0
    pop2 = np.vstack([pop1, newcomer])
    d2 = assign(pop2, persona_x, top_p=0.5, corr_threshold=0.5)
    print(f"[D] phase1(休眠)={d1}  phase2(再付与)={d2}")
    assert d1[0] is None, "相関個体不在では休眠 (None) のはず"
    assert d2[0] == len(pop2) - 1, "後世で出現した個体に再付与されるはず"
    print("  -> D(隔世: 休眠→再覚醒) OK\n")

    # ---- H: 退化診断 (集団収束 → 1 個体が総取り) ----
    base = _unit(0)                                    # 全員ほぼ同一方向に収束
    collapsed = base + rng.normal(0, 0.001, size=(10, FACTOR_DIM))
    # personas も似通った方向にして「判別不能」を作る
    sim_personas = np.stack([_unit(0), _unit(0) + 0.01, _unit(0) - 0.01])
    ah = assign(collapsed, sim_personas, top_p=0.5, corr_threshold=0.3)
    ch = multiplicity(ah, len(collapsed))
    print(f"[H] collapsed assignment={ah}  counts={ch.tolist()}  max={ch.max()}")
    assert ch.max() >= 2, "収束集団では 1 個体が多数 persona を総取り (退化が可視化) するはず"
    print("  -> H(退化診断: 偏りが跳ねる) OK\n")

    print("ALL PoC CHECKS PASSED (U / M / D / H).")
    print("honest: 合成・proxy。実装時は 逸脱→NoveltyScorer / 相関→factor_affinity / "
          "報酬→lleval に差し替え。多様性エンジン(E)は次段 (toy 選択ループ)。")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows cp932 対策
    raise SystemExit(main())
