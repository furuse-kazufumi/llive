# SPDX-License-Identifier: Apache-2.0
"""大 proxy PoC: 実 Genome3D 個体 + 進化ループで persona-index ON vs OFF を ablation.

小 PoC (``scripts/poc_persona_indexed_genome.py``) で「各因子の最適が別専門家にある
モザイク target には single 構造では届かず, persona-indexed (各因子に 1 ペルソナ) なら
構造的に埋められる」と gate 済. 本 PoC はその効果を **小 PoC の合成エンコーディングでなく
実 production 個体 (``Genome3D.c_factors`` = ``ThoughtFactorPerLayerChromosome``) と
実進化ループ** (tournament + Genome3DCrossover/Mutation 系) を通して再確認し,
ablation で persona_index の寄与を測る.

検証する命題 (falsifiable)
--------------------------
    **「founder に persona_index を持たせ operator で進化させる条件 (ON) は,
      連続 c_factors の層平均 phenotype のみで進化する条件 (OFF) が構造的に
      到達できない『各因子の最適が別専門家にある』モザイク target に到達する。」**

proxy fitness
-------------
phenotype を 10 次元の per-factor envelope target (= 各因子の per-persona 最大値) へ
近づける問題。距離が小さいほど高 score。

* ``persona_index_on``  : 個体は persona_index を持ち, phenotype =
  ``c_factors.persona_indexed_affinity()`` (= 担当ペルソナの factor affinity).
  operator (mutation/crossover) は persona_index を進化させる (additive 経路)。
* ``persona_index_off`` : 個体は persona_index を持たず (None),
  phenotype = ``c_factors`` の **層平均** (= 連続 40-dim を 10-dim に集約)。
  現行 c_factors の連続進化のみ。

両条件とも同一 budget (pop / gens / seed)・同一ループロジック (公平比較)。

HONEST DISCLOSURE
-----------------
* proxy・合成 target。実 LLM / 実思考品質ではない (PERSONA_ONTOLOGY の heuristic
  affinity を per-factor envelope にしたもの)。実 LLM 予言ではない。
* OFF は連続 [0,1] phenotype なので raw 可達性自体はモザイク target にも届きうる。
  本 PoC の論点は「**persona-index という離散・来歴つきの inductive bias が,
  同一 budget でモザイク target への収束を構造的に有利にするか**」であり,
  「OFF が原理的に到達不能」ではない。差が出るのは budget が有限で envelope が
  ペルソナ行の組合せに一致する (= indexed が argmax で 1 手到達できる) ときに顕著。
* mock/proxy・LLM/Docker ゼロ・決定論 (seed)・stdlib + numpy + llive import のみ。

    py -3.11 scripts/poc_persona_indexed_evolution.py
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from llive.perf.evolutionary.genome_3d import Genome3D
from llive.perf.evolutionary.genome_3d_operators import (
    Genome3DCrossover,
    Genome3DMutation,
)
from llive.perf.evolutionary.impl_chromosome import ImplChromosome
from llive.perf.evolutionary.meta_chromosome import MetaChromosome
from llive.perf.evolutionary.persona import PERSONA_ONTOLOGY
from llive.perf.evolutionary.prompt_chromosome import PromptChromosome
from llive.perf.evolutionary.thought_factor_per_layer import (
    NUM_THOUGHT_FACTORS,
    ThoughtFactorPerLayerChromosome,
    random_persona_index,
)


def _ensure_utf8_stdout() -> None:
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# affinity matrix + mosaic target (小 PoC と同一の素材)
# ---------------------------------------------------------------------------


def _affinity_matrix() -> tuple[np.ndarray, list[str]]:
    """A[p, f] = persona p の factor f への affinity. ids = sorted (正準順)."""
    ids = sorted(PERSONA_ONTOLOGY.keys())
    A = np.array(
        [list(PERSONA_ONTOLOGY[pid].factor_affinity) for pid in ids], dtype=float
    )
    return A, ids


def _mosaic_target(A: np.ndarray) -> np.ndarray:
    """各因子の per-persona 最大 envelope (= 単一ペルソナで到達不能なモザイク target)."""
    return A.max(axis=0)


def _single_structural_floor(A: np.ndarray, target: np.ndarray) -> float:
    """どの単一ペルソナでも超えられない target への構造的最小距離 (headroom 基準)."""
    return float(np.min(np.linalg.norm(A - target[None, :], axis=1)))


# ---------------------------------------------------------------------------
# phenotype + fitness (ON / OFF)
# ---------------------------------------------------------------------------


def phenotype_on(genome: Genome3D) -> np.ndarray:
    """ON: persona_index decode (= 担当ペルソナの factor affinity, 10-dim)."""
    pheno = genome.c_factors.persona_indexed_affinity()
    if pheno is None:
        raise ValueError("persona_index_on genome must carry persona_index")
    return np.asarray(pheno, dtype=float)


def phenotype_off(genome: Genome3D) -> np.ndarray:
    """OFF: 連続 c_factors の層平均 (40-dim → 因子方向 10-dim へ集約)."""
    arr = genome.c_factors.as_array()  # (10, n_layers)
    return arr.mean(axis=1)


def _fitness(pheno: np.ndarray, target: np.ndarray) -> float:
    """target への近さ (距離負値, max 0)."""
    return -float(np.linalg.norm(pheno - target))


# ---------------------------------------------------------------------------
# founders
# ---------------------------------------------------------------------------


def _base_genome(c_factors: ThoughtFactorPerLayerChromosome) -> Genome3D:
    return Genome3D(
        c_impl=ImplChromosome.default(),
        c_prompt=PromptChromosome.default(),
        c_meta=MetaChromosome.default(),
        c_factors=c_factors,
    )


def founders_on(rng: np.random.Generator, size: int) -> list[Genome3D]:
    """ON founders: 連続 weights は random, persona_index も random で持たせる."""
    out = []
    for _ in range(size):
        cf = ThoughtFactorPerLayerChromosome.random(rng).with_persona_index(
            random_persona_index(rng)
        )
        out.append(_base_genome(cf))
    return out


def founders_off(rng: np.random.Generator, size: int) -> list[Genome3D]:
    """OFF founders: 連続 weights は random, persona_index は None (現行 c_factors のみ)."""
    return [
        _base_genome(ThoughtFactorPerLayerChromosome.random(rng)) for _ in range(size)
    ]


# ---------------------------------------------------------------------------
# 共通の tournament 進化ループ (ON/OFF で同一ロジック・同一 budget)
# ---------------------------------------------------------------------------


@dataclass
class EvoConfig:
    pop: int
    gens: int
    seed: int
    elite: int
    tournament_k: int
    mutation_step: float
    crossover_mode: str  # "intra" / "cross"


def _tournament(
    pop: list[Genome3D],
    scores: list[float],
    k: int,
    rng: np.random.Generator,
) -> Genome3D:
    idx = rng.choice(len(pop), size=min(k, len(pop)), replace=False)
    best_i = max(idx, key=lambda i: scores[int(i)])
    return pop[int(best_i)]


def _diversity_phenotype(phenos: np.ndarray) -> float:
    """phenotype 行列 (pop, 10) の pairwise L2 平均 (多様性 proxy)."""
    if len(phenos) < 2:
        return 0.0
    diff = phenos[:, None, :] - phenos[None, :, :]
    dists = np.sqrt(np.sum(diff * diff, axis=-1))
    mask = ~np.eye(len(phenos), dtype=bool)
    return float(dists[mask].mean())


def evolve(
    founders: list[Genome3D],
    phenotype_fn,
    target: np.ndarray,
    cfg: EvoConfig,
) -> dict:
    """実 Genome3D 個体 + tournament + Genome3D operator でモザイク target を追う."""
    rng = np.random.default_rng(cfg.seed)
    crossover = Genome3DCrossover(mode=cfg.crossover_mode)
    mutation = Genome3DMutation(step_size=cfg.mutation_step)

    pop = list(founders)
    best_curve: list[float] = []
    best_dist = float("inf")

    for _gen in range(cfg.gens):
        phenos = np.stack([phenotype_fn(g) for g in pop])
        scores = [_fitness(phenos[i], target) for i in range(len(pop))]
        score_arr = np.asarray(scores)
        gen_best = float(np.min(np.linalg.norm(phenos - target[None, :], axis=1)))
        best_dist = min(best_dist, gen_best)
        best_curve.append(round(gen_best, 4))

        # 次世代
        next_pop: list[Genome3D] = []
        sorted_idx = np.argsort(score_arr)[::-1]
        for i in sorted_idx[: cfg.elite]:
            next_pop.append(pop[int(i)])
        while len(next_pop) < cfg.pop:
            a = _tournament(pop, scores, cfg.tournament_k, rng)
            b = _tournament(pop, scores, cfg.tournament_k, rng)
            child = crossover(a, b, rng)
            child = mutation(child, rng)
            next_pop.append(child)
        pop = next_pop

    # 最終評価
    phenos = np.stack([phenotype_fn(g) for g in pop])
    final_dists = np.linalg.norm(phenos - target[None, :], axis=1)
    best_dist = min(best_dist, float(final_dists.min()))
    best_idx = int(final_dists.argmin())
    best_pheno = phenos[best_idx]

    return {
        "best_dist": round(best_dist, 4),
        "best_curve": best_curve,
        "final_diversity": round(_diversity_phenotype(phenos), 4),
        "best_phenotype": [round(float(x), 3) for x in best_pheno],
        "best_persona_index": (
            list(pop[best_idx].c_factors.persona_index)
            if pop[best_idx].c_factors.persona_index is not None
            else None
        ),
    }


# ---------------------------------------------------------------------------
# run + verdict
# ---------------------------------------------------------------------------


def run(
    pop: int,
    gens: int,
    seed: int,
    eps: float,
    *,
    elite: int = 2,
    tournament_k: int = 3,
    mutation_step: float = 0.1,
    crossover_mode: str = "intra",
) -> dict:
    A, ids = _affinity_matrix()
    target = _mosaic_target(A)
    floor = _single_structural_floor(A, target)

    cfg = EvoConfig(
        pop=pop,
        gens=gens,
        seed=seed,
        elite=elite,
        tournament_k=tournament_k,
        mutation_step=mutation_step,
        crossover_mode=crossover_mode,
    )

    on = evolve(founders_on(np.random.default_rng(seed), pop), phenotype_on, target, cfg)
    off = evolve(
        founders_off(np.random.default_rng(seed), pop), phenotype_off, target, cfg
    )

    # ablation verdict: ON が OFF を寄与で上回るか (モザイク target で),
    # かつ ON が single 構造 floor を埋めたか。
    on_minus_off = round(off["best_dist"] - on["best_dist"], 4)  # >0 = ON が近い
    headroom_filled_by_on = round(floor - on["best_dist"], 4)
    verdict = {
        "proposition": (
            "persona_index ON は OFF (連続 c_factors 層平均) より同一 budget で "
            "モザイク target に近づき, single 構造 floor を埋める"
        ),
        "mosaic_target": [round(float(x), 3) for x in target],
        "single_structural_floor": round(floor, 4),
        "on_best_dist": on["best_dist"],
        "off_best_dist": off["best_dist"],
        "on_minus_off(off - on, >0 = on closer)": on_minus_off,
        "on_reaches_eps": bool(on["best_dist"] <= eps),
        "off_reaches_eps": bool(off["best_dist"] <= eps),
        "headroom_filled_by_on(floor - on)": headroom_filled_by_on,
        # ablation 採否: ON が OFF より明確に近づき (>eps) かつ floor を埋めた
        "persona_index_contributes": bool(
            on_minus_off > eps and headroom_filled_by_on > eps
        ),
    }

    return {
        "schema": "poc_persona_indexed_evolution/v1",
        "n_personas": len(ids),
        "persona_ids": ids,
        "n_factors": NUM_THOUGHT_FACTORS,
        "config": {
            "pop": pop,
            "gens": gens,
            "seed": seed,
            "eps": eps,
            "elite": elite,
            "tournament_k": tournament_k,
            "mutation_step": mutation_step,
            "crossover_mode": crossover_mode,
        },
        "results": {"persona_index_on": on, "persona_index_off": off},
        "verdict": verdict,
        "honest_notes": [
            "proxy・合成 target (PERSONA_ONTOLOGY heuristic affinity の per-factor "
            "envelope)。実 LLM/実思考品質ではない。実 LLM 予言でない。",
            "実 Genome3D 個体 + tournament + Genome3DCrossover/Mutation を経由 (小 PoC の "
            "合成エンコーディングではない)。persona_index は additive 経路 (decode) で "
            "進化し, 連続 40-dim flat genome には含まれない。",
            "OFF は連続 phenotype なので raw 可達性は原理的にモザイク target にも届く。"
            "差は『有限 budget で indexed の離散・来歴つき inductive bias が収束を "
            "有利にするか』であり OFF の原理的到達不能を主張しない (honest)。",
            "single で到達可能な滑らかな target なら ON の利得は出ない (= いつ効くかを "
            "明示)。本 PoC はモザイク target でのみ効果を測る。",
        ],
    }


def _print(out: dict) -> None:
    v = out["verdict"]
    print("\n===== persona-indexed evolution PoC (real Genome3D) =====")
    print(f"personas={out['n_personas']} factors={out['n_factors']} config={out['config']}")
    print(f"\n[mosaic target: 各因子の最適が別ペルソナ = single 構造で到達不能]")
    print(f"  single structural floor = {v['single_structural_floor']:.4f}")
    print(
        f"  ON  best_dist = {v['on_best_dist']:.4f} "
        f"(reaches eps={v['on_reaches_eps']})"
    )
    print(
        f"  OFF best_dist = {v['off_best_dist']:.4f} "
        f"(reaches eps={v['off_reaches_eps']})"
    )
    print(
        f"  => off - on (>0 = ON closer) = "
        f"{v['on_minus_off(off - on, >0 = on closer)']:+.4f}"
    )
    print(
        f"  => headroom filled by ON (floor - on) = "
        f"{v['headroom_filled_by_on(floor - on)']:+.4f}"
    )
    print(f"\nVERDICT persona_index_contributes = {v['persona_index_contributes']}")
    if v["persona_index_contributes"]:
        print(
            "  → persona_index ON が OFF を寄与で上回り single 構造 floor を埋めた "
            "= モザイク target で効果あり。"
        )
    else:
        print("  → この設定では ON の OFF 超え寄与が出なかった。honest に記録。")


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description="persona-indexed evolution PoC")
    ap.add_argument("--pop", type=int, default=30)
    ap.add_argument("--gens", type=int, default=60)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--eps", type=float, default=0.05)
    ap.add_argument("--elite", type=int, default=2)
    ap.add_argument("--tournament-k", type=int, default=3)
    ap.add_argument("--mutation-step", type=float, default=0.1)
    ap.add_argument("--crossover", default="intra", choices=["intra", "cross"])
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(r"D:/projects/llive/out/poc_persona_indexed_evolution"),
    )
    args = ap.parse_args(argv)

    out = run(
        args.pop,
        args.gens,
        args.seed,
        args.eps,
        elite=args.elite,
        tournament_k=args.tournament_k,
        mutation_step=args.mutation_step,
        crossover_mode=args.crossover,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    out_json = args.out / "persona_indexed_evolution.json"
    out_json.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    _print(out)
    print(f"\n[poc_persona_indexed_evolution] wrote {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
