# SPDX-License-Identifier: Apache-2.0
"""PoC: 各思考因子に 1 ペルソナを割り当てる **persona-indexed (モザイク) ゲノム** に効果があるか.

ユーザー要件 (2026-05-28): 「各因子に 1 ペルソナを割り当てる indexed 方式を先にやって、
PoC で効果があるのか判断したい」。Phase A 収束計画の「段階1: persona-indexed genome
(各層/因子に担当 persona, 単純な離散 index × 重い選択肢)」を **falsifiable に gate** する。

検証する命題 (falsifiable)
--------------------------
    **「因子ごとに別ペルソナを割り当てられる indexed (モザイク) ゲノムは、個体全体を
      1 ペルソナに固定する single 方式が *構造的に到達できない* 因子プロファイル
      (= 各因子の最適が別ペルソナにある『専門家委員会』型) に到達できる。」**

= 「どの 1 人の専門家も全 10 因子で最強ではない」現実の persona affinity 構造
([[project_persona_genome_integration]] の PERSONA_ONTOLOGY) を使い、モザイクが
single の頭打ちを超える *headroom* を定量化する。超えなければ honest にそう報告する
([[feedback_benchmark_honest_disclosure]])。

比較する 3 エンコーディング
---------------------------
* ``single``    : genome = 1 個の persona index → phenotype = その persona の factor_affinity
                  (= 現状の founder seeding 方式)。探索空間 = P (ペルソナ数)。
* ``continuous``: genome = 10 次元の自由ベクトル [0,1] → phenotype = そのまま
                  (= 制約なし。到達可能性は最大だが来歴/解釈性なし)。
* ``indexed``   : genome = 10 個の離散 index (因子ごとに担当 persona) →
                  phenotype[f] = A[idx_f][f] (モザイク)。本 PoC が評価する方式。

2 ターゲット (いつ効くかを切り分ける)
-------------------------------------
* ``single``  : ある 1 ペルソナの affinity そのもの。single 方式で厳密到達可能。
* ``mosaic``  : 各因子の per-persona 最大値の envelope (= 各因子で別の専門家が最強)。
                **どの単一ペルソナでも到達不能** / indexed (argmax/因子) と continuous は到達可能。

HONEST DISCLOSURE
-----------------
proxy・合成ターゲット。実 LLM/実 genome ループ非接触 (PERSONA_ONTOLOGY の affinity のみ import,
EvolutionLoop/Genome は import しない)。**表現可達性 (どの因子プロファイルに届くか) の効果**を
測るもので production の思考品質ではない。affinity 自体も persona.py の heuristic 値。stdlib +
numpy のみ、決定論的 (seed)。

    py -3.11 scripts/poc_persona_indexed_genome.py
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# --- scripts/ を path に (姉妹 PoC 規約) + llive src ---
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# 軽量 import のみ (PERSONA_ONTOLOGY = dataclass + dict。EvolutionLoop/Genome 非接触)。
from llive.perf.evolutionary.persona import (  # noqa: E402
    PERSONA_ONTOLOGY,
    THOUGHT_FACTORS,
)


def _ensure_utf8_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass


N_FACTORS = len(THOUGHT_FACTORS)  # 10


def affinity_matrix() -> tuple[np.ndarray, list[str]]:
    """PERSONA_ONTOLOGY を A[p, f] = persona p の factor f への affinity に整形."""
    ids = sorted(PERSONA_ONTOLOGY.keys())
    A = np.array(
        [list(PERSONA_ONTOLOGY[pid].factor_affinity) for pid in ids],
        dtype=float,
    )
    assert A.shape[1] == N_FACTORS, (A.shape, N_FACTORS)
    return A, ids


# ---------------------------------------------------------------------------
# エンコーディング (decode / init / mutate)
# ---------------------------------------------------------------------------


def _dist(pheno: np.ndarray, target: np.ndarray) -> float:
    return float(np.linalg.norm(pheno - target))


@dataclass
class Encoding:
    name: str
    init: object   # (rng) -> genome
    mutate: object  # (genome, rng) -> genome
    decode: object  # (genome) -> np.ndarray(N_FACTORS)


def make_encodings(A: np.ndarray) -> dict[str, Encoding]:
    P = A.shape[0]

    # single: genome = int persona idx
    def s_init(rng):
        return int(rng.integers(P))

    def s_mut(g, rng):
        return int(rng.integers(P))  # 全 P から選び直す (探索空間 = P と小さい)

    def s_dec(g):
        return A[int(g)]

    # continuous: genome = np.array(N_FACTORS) in [0,1]
    def c_init(rng):
        return rng.random(N_FACTORS)

    def c_mut(g, rng):
        ng = g + rng.normal(0.0, 0.1, size=N_FACTORS)
        return np.clip(ng, 0.0, 1.0)

    def c_dec(g):
        return np.asarray(g, dtype=float)

    # indexed (mosaic): genome = np.array(N_FACTORS) int persona idx per factor
    def i_init(rng):
        return rng.integers(P, size=N_FACTORS)

    def i_mut(g, rng):
        ng = np.array(g, dtype=int)
        f = int(rng.integers(N_FACTORS))      # 1 因子だけ担当ペルソナを変える
        ng[f] = int(rng.integers(P))
        return ng

    def i_dec(g):
        g = np.asarray(g, dtype=int)
        return A[g, np.arange(N_FACTORS)]

    return {
        "single": Encoding("single", s_init, s_mut, s_dec),
        "continuous": Encoding("continuous", c_init, c_mut, c_dec),
        "indexed": Encoding("indexed", i_init, i_mut, i_dec),
    }


# ---------------------------------------------------------------------------
# 共通の (mu+lambda) 進化 — 全エンコーディングで同一 budget・同一ロジック (公平比較)
# ---------------------------------------------------------------------------


def evolve(enc: Encoding, target: np.ndarray, *, pop: int, gens: int,
           seed: int, eps: float) -> dict:
    """同一 budget の (mu+lambda) で target への最小距離を探索 (公平比較)。"""
    rng = np.random.default_rng(seed)
    mu = max(2, pop // 4)
    genomes = [enc.init(rng) for _ in range(pop)]
    evals = 0

    def fit(g):
        nonlocal evals
        evals += 1
        return _dist(enc.decode(g), target)

    scored = [(fit(g), g) for g in genomes]
    best_curve: list[float] = []
    evals_to_eps: int | None = None
    for _gen in range(gens):
        scored.sort(key=lambda t: t[0])
        if evals_to_eps is None and scored[0][0] <= eps:
            evals_to_eps = evals
        parents = [g for _d, g in scored[:mu]]
        children = []
        i = 0
        while len(children) < (pop - mu):
            p = parents[i % len(parents)]
            children.append(enc.mutate(p, rng))
            i += 1
        scored = scored[:mu] + [(fit(c), c) for c in children]
        best_curve.append(round(min(d for d, _ in scored), 4))

    scored.sort(key=lambda t: t[0])
    best_d, best_g = scored[0]
    if evals_to_eps is None and best_d <= eps:
        evals_to_eps = evals
    return {
        "best_dist": round(float(best_d), 4),
        "reached": bool(best_d <= eps),
        "evals_to_eps": evals_to_eps,
        "best_curve": best_curve,
        "best_phenotype": [round(float(x), 3) for x in enc.decode(best_g)],
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def _single_floor(A: np.ndarray, target: np.ndarray) -> tuple[float, int]:
    """target に対し『どの単一ペルソナでも超えられない』構造的最小距離 (headroom 基準)。"""
    dists = np.linalg.norm(A - target[None, :], axis=1)
    idx = int(np.argmin(dists))
    return float(dists[idx]), idx


def run(pop: int, gens: int, seed: int, eps: float) -> dict:
    A, ids = affinity_matrix()
    encs = make_encodings(A)

    # target_single = ある generalist persona の affinity (single で厳密到達可)。
    vn_idx = ids.index("von-neumann") if "von-neumann" in ids else 0
    target_single = A[vn_idx].copy()
    # target_mosaic = 各因子の per-persona 最大 envelope (単一不能 / モザイク可)。
    target_mosaic = A.max(axis=0)

    targets = {"single": target_single, "mosaic": target_mosaic}
    results: dict[str, dict] = {}
    for tname, tvec in targets.items():
        floor, floor_idx = _single_floor(A, tvec)
        per_enc = {
            ename: evolve(enc, tvec, pop=pop, gens=gens, seed=seed, eps=eps)
            for ename, enc in encs.items()
        }
        results[tname] = {
            "target": [round(float(x), 3) for x in tvec],
            "single_persona_structural_floor": round(floor, 4),
            "single_persona_floor_persona": ids[floor_idx],
            "encodings": per_enc,
        }

    # --- verdict (falsifiable 判定) ---
    mos = results["mosaic"]["encodings"]
    sin = results["single"]["encodings"]
    floor_mosaic = results["mosaic"]["single_persona_structural_floor"]
    # single はどの 1 ペルソナでも floor 未満に行けない。indexed がその floor をどれだけ
    # 下回ったか = indexed が構造的に埋めた headroom。
    indexed_gap_filled = round(floor_mosaic - mos["indexed"]["best_dist"], 4)
    verdict = {
        "proposition": (
            "indexed(モザイク)は single が構造的に届かない『各因子別専門家』型 target に到達する"),
        "mosaic_target": {
            "single_best_dist": mos["single"]["best_dist"],
            "single_structural_floor": floor_mosaic,
            "indexed_best_dist": mos["indexed"]["best_dist"],
            "continuous_best_dist": mos["continuous"]["best_dist"],
            "indexed_reaches": mos["indexed"]["reached"],
            "single_reaches": mos["single"]["reached"],
            "headroom_filled_by_indexed(floor - indexed)": indexed_gap_filled,
        },
        "single_target": {
            "single_best_dist": sin["single"]["best_dist"],
            "indexed_best_dist": sin["indexed"]["best_dist"],
            "indexed_reaches": sin["indexed"]["reached"],
            "note": "single で到達可能な target では indexed は同等 (追加の利得なし=複雑性増のみ)",
        },
        "indexed_has_effect": bool(
            mos["indexed"]["reached"] and (not mos["single"]["reached"])
            and indexed_gap_filled > eps
        ),
    }

    return {
        "schema": "poc_persona_indexed_genome/v1",
        "proposition": __doc__.split("命題")[1].split("----")[1].strip()[:280] if "命題" in __doc__ else "",
        "n_personas": len(ids),
        "persona_ids": ids,
        "n_factors": N_FACTORS,
        "thought_factors": list(THOUGHT_FACTORS),
        "config": {"pop": pop, "gens": gens, "seed": seed, "eps": eps},
        "results": results,
        "verdict": verdict,
        "honest_notes": [
            "proxy・合成ターゲット。実 LLM/実 genome 非接触 (PERSONA_ONTOLOGY affinity のみ import)。"
            "表現可達性の効果を測るもので production 思考品質ではない。",
            "affinity は persona.py の heuristic 値 (corpus 自動抽出で精緻化予定の暫定値)。",
            "continuous は制約なしゆえ raw 可達性は最大 (mosaic にも届く)。indexed の価値は "
            "single 超えの構造的可達性 + 各因子→named persona の来歴/解釈性 + 『重い選択肢』の "
            "inductive bias であり、continuous 超えの raw 可達性ではない (honest)。",
            "single で到達可能な target では indexed の利得はゼロ (複雑性増のみ)。効果は "
            "『各因子の最適が別専門家にある』モザイク型 target でのみ出る = いつ効くかを明示。",
        ],
    }


def _print(out: dict) -> None:
    v = out["verdict"]
    print("\n===== persona-indexed (mosaic) genome PoC =====")
    print(f"personas={out['n_personas']} factors={out['n_factors']} config={out['config']}")
    mt = v["mosaic_target"]
    print("\n[mosaic target: 各因子の最適が別ペルソナ = 単一不能]")
    print(f"  single  best_dist = {mt['single_best_dist']:.4f} "
          f"(structural floor {mt['single_structural_floor']:.4f}, reached={mt['single_reaches']})")
    print(f"  indexed best_dist = {mt['indexed_best_dist']:.4f} (reached={mt['indexed_reaches']})")
    print(f"  continuous best   = {mt['continuous_best_dist']:.4f}")
    print(f"  => indexed が埋めた headroom (floor - indexed) = "
          f"{mt['headroom_filled_by_indexed(floor - indexed)']:+.4f}")
    st = v["single_target"]
    print("\n[single target: 単一ペルソナで到達可能]")
    print(f"  single best_dist = {st['single_best_dist']:.4f} / "
          f"indexed best_dist = {st['indexed_best_dist']:.4f} (reached={st['indexed_reaches']})")
    print(f"\nVERDICT indexed_has_effect = {v['indexed_has_effect']}")
    if v["indexed_has_effect"]:
        print("  → persona-indexed (モザイク) は single が構造的に届かない専門家委員会型 "
              "プロファイルに到達 = 効果あり。ただし single で足りる target では利得なし。")
    else:
        print("  → この設定では indexed の single 超えが出なかった。honest に記録。")


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description="persona-indexed genome PoC")
    ap.add_argument("--pop", type=int, default=24)
    ap.add_argument("--gens", type=int, default=80)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--eps", type=float, default=0.05,
                    help="到達とみなす target 距離の閾値")
    ap.add_argument("--out", type=Path,
                    default=Path(r"D:/projects/llive/out/poc_persona_indexed_genome"))
    args = ap.parse_args(argv)

    out = run(args.pop, args.gens, args.seed, args.eps)
    args.out.mkdir(parents=True, exist_ok=True)
    out_json = args.out / "persona_indexed.json"
    out_json.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    _print(out)
    print(f"\n[poc_persona_indexed] wrote {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
