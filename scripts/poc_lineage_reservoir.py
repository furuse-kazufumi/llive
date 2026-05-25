# SPDX-License-Identifier: Apache-2.0
"""PoC: lineage-niched 中立貯蔵庫 (reservoir) で系統絶滅を防げるか検証.

lldarwin Stage1 の honest 発見 (fullsense docs/research/lldarwin_stage1_results_2026_05_26.md):
novelty/lexicase は **行動多様性** を保つが **系統固定 (lineage fixation)** は中立浮動で
monoculture に向かう (既存個体の保存のみ・絶滅系統を復活できないため)。系統を保つには
「QD niching on lineage」= 系統別 elite を保持し絶滅系統を re-inject する中立貯蔵庫が要る
(poc_evolution_env 著者コメント / 設計 §6 Stage1.5)。

本 PoC は EvolutionLoop の核改修前に、reservoir 機構の効果を A/B で実証する:
  - selection = lldarwin ``MultiPressureSelector`` (criteria 除外 + novelty, Stage1 実装)
  - fitness   = rich-proxy (決定論, LLM 非依存) — 実 founder archetype を使う
  - lineage   = founder id を子へ parent_a から継承
  - reservoir = 系統別の best-ever 個体。``--reservoir`` 時のみ、絶滅した系統を毎世代 re-inject

測定: lineage_fixation (= max 系統占有率) と behavioral diversity を世代ごとに記録し、
reservoir on/off で「岡潔/グロタンが生き残るか」を比較する。

HONEST: これは proxy 機構の feasibility 検証。reservoir が lineage_fixation を下げられれば
EvolutionLoop への組込 (Stage1.5) を正当化する。実 LLM/VLM 能力の選択圧は Stage2。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from llive.perf.evolutionary.fitness_rich import make_rich_proxy_fitness
from llive.perf.evolutionary.genome_3d import genome_flat_vector
from llive.perf.evolutionary.genome_3d_operators import (
    Genome3DCrossover,
    Genome3DMutation,
)
from llive.perf.evolutionary.individual import Individual
from llive.perf.evolutionary.lldarwin import MultiPressureSelector
from llive.perf.evolutionary.persona_evolution import build_founder_genome_3d
from llive.perf.evolutionary.population import Population

DEFAULT_FOUNDERS = (
    "furuse-kazufumi",
    "friston",
    "millidge",
    "isomura-takuya",
    "oka-kiyoshi",
    "grothendieck",
    "von-neumann",
    "feynman",
)


def _diversity_l2(pop: Population) -> float:
    """集団の mean pairwise L2 (= 行動多様性, generations.jsonl と同義)."""
    vecs = np.stack([genome_flat_vector(i.genome) for i in pop.individuals])
    n = len(vecs)
    if n < 2:
        return 0.0
    dsum = 0.0
    cnt = 0
    for a in range(n):
        diff = vecs[a + 1 :] - vecs[a]
        dsum += float(np.linalg.norm(diff, axis=1).sum())
        cnt += n - a - 1
    return dsum / cnt


def _lineage_shares(lineage_of: dict[str, str], pop: Population) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ind in pop.individuals:
        lin = lineage_of.get(ind.individual_id, "(unknown)")
        counts[lin] = counts.get(lin, 0) + 1
    return counts


def run(
    founders: tuple[str, ...],
    *,
    population: int,
    generations: int,
    seed: int,
    use_reservoir: bool,
    use_novelty: bool,
) -> list[dict]:
    rng = np.random.default_rng(seed)
    fitness = make_rich_proxy_fitness(founders)
    crossover = Genome3DCrossover(mode="intra")
    mutation = Genome3DMutation(step_size=0.1)
    selector = MultiPressureSelector(epsilon=0.01, use_novelty=use_novelty)

    lineage_of: dict[str, str] = {}

    # gen0: 各 founder 1 体 + 残りは founder のコピーを padding (lineage 付き)。
    individuals: list[Individual] = []
    for i in range(population):
        pid = founders[i % len(founders)]
        ind = Individual(genome=build_founder_genome_3d(pid), birth_generation=0)
        lineage_of[ind.individual_id] = pid
        individuals.append(ind)
    pop = Population(individuals=individuals, generation=0)

    reservoir: dict[str, tuple[float, object]] = {}  # lineage -> (score, genome)
    records: list[dict] = []

    for gen in range(generations + 1):
        for ind in pop.individuals:
            if ind.fitness is None:
                ind.record_fitness(fitness(ind.genome))
        # reservoir 更新: 系統別の best-ever genome。
        for ind in pop.individuals:
            lin = lineage_of.get(ind.individual_id, "(unknown)")
            sc = float(ind.fitness.score)
            if lin not in reservoir or sc > reservoir[lin][0]:
                reservoir[lin] = (sc, ind.genome)

        counts = _lineage_shares(lineage_of, pop)
        named = {k: v for k, v in counts.items() if k in founders}
        total = sum(counts.values())
        records.append(
            {
                "generation": gen,
                "lineage_fixation": max(counts.values()) / total,
                "named_survivors": len([k for k in founders if counts.get(k, 0) > 0]),
                "diversity_l2": _diversity_l2(pop),
                "shares": dict(sorted(named.items(), key=lambda x: -x[1])),
            }
        )
        if gen == generations:
            break

        # ---- breed next generation ----
        next_inds: list[Individual] = []
        while len(next_inds) < population:
            pa = selector(pop, rng)
            pb = selector(pop, rng)
            child_g = mutation(crossover(pa.genome, pb.genome, rng), rng)
            child = Individual.from_genome(
                child_g, parent_ids=(pa.individual_id, pb.individual_id),
                birth_generation=gen + 1,
            )
            lineage_of[child.individual_id] = lineage_of.get(pa.individual_id, "(unknown)")
            next_inds.append(child)

        if use_reservoir:
            # 絶滅した系統を貯蔵庫 elite で復活 (lineage-niched QD の核, 中立貯蔵庫)。
            present = {lineage_of.get(i.individual_id) for i in next_inds}
            extinct = [f for f in founders if f not in present and f in reservoir]
            # 低 score の子を貯蔵庫 elite で置換 (best は壊さない)。
            next_inds.sort(key=lambda i: float(i.fitness.score) if i.fitness else 0.0)
            for j, lin in enumerate(extinct):
                if j >= len(next_inds):
                    break
                _, g = reservoir[lin]
                revived = Individual.from_genome(g, birth_generation=gen + 1)
                lineage_of[revived.individual_id] = lin
                next_inds[j] = revived

        pop = Population(individuals=next_inds, generation=gen + 1)

    return records


def main() -> int:
    ap = argparse.ArgumentParser(description="lineage reservoir PoC")
    ap.add_argument("--generations", type=int, default=150)
    ap.add_argument("--population", type=int, default=24)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-novelty", action="store_true", help="novelty pressure を切る")
    ap.add_argument("--out", type=Path, default=Path("out/poc_lineage_reservoir"))
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    summary = {}
    for label, reservoir in (("OFF", False), ("ON", True)):
        recs = run(
            DEFAULT_FOUNDERS,
            population=args.population,
            generations=args.generations,
            seed=args.seed,
            use_reservoir=reservoir,
            use_novelty=not args.no_novelty,
        )
        (args.out / f"reservoir_{label}.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in recs), encoding="utf-8"
        )
        tail = recs[-30:]
        summary[label] = {
            "final_named_survivors": recs[-1]["named_survivors"],
            "final_lineage_fixation": round(recs[-1]["lineage_fixation"], 3),
            "tail30_mean_lineage_fixation": round(
                float(np.mean([r["lineage_fixation"] for r in tail])), 3
            ),
            "tail30_mean_diversity": round(
                float(np.mean([r["diversity_l2"] for r in tail])), 2
            ),
            "final_shares": recs[-1]["shares"],
        }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    (args.out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
