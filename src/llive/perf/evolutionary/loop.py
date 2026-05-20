# SPDX-License-Identifier: Apache-2.0
"""EvolutionLoop — 1 世代 = evaluate → select → breed → mutate → 次世代 (llive v0.B EV-06).

Phase 2 (本セッション): SerialScheduler のみ.
Phase 3 で MultiprocessingScheduler / AsyncioScheduler を ``scheduler`` module
で提供.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

import numpy as np

from llive.perf.evolutionary.crossover import UniformCrossover
from llive.perf.evolutionary.fitness import Fitness
from llive.perf.evolutionary.individual import FitnessReport, Individual
from llive.perf.evolutionary.mutation import ChainedMutation, GaussianMutation
from llive.perf.evolutionary.population import Population, PopulationStats
from llive.perf.evolutionary.seeds import call_fitness_with_seed, fitness_accepts_seed
from llive.perf.evolutionary.selection import (
    ElitismSelection,
    TournamentSelection,
)

# 型 alias
SelectionFn = Callable[[Population, np.random.Generator], Individual]
CrossoverFn = Callable[[object, object, np.random.Generator], object]
MutationFn = Callable[[object, np.random.Generator], object]
SchedulerFn = Callable[[Fitness, Iterable[Individual]], list[FitnessReport]]


def _serial_scheduler(
    fitness_fn: Fitness, individuals: Iterable[Individual]
) -> list[FitnessReport]:
    """Phase 2 default. シリアルに fitness を評価.

    Phase 3.5: fitness_fn が 2 引数 shape (genome, seed) を受け入れるなら
    individual ごとに deterministic な sub_seed を派生して渡す.
    """
    inds = list(individuals)
    if fitness_accepts_seed(fitness_fn):
        # parent_seed は呼び出し元 (EvolutionLoop) が個別世代の seed を
        # population から取得して渡す方が綺麗だが, scheduler 単独利用でも
        # 動くように個体ごとに parent_seed=0 baseline を使う.
        # 真の再現性は EvolutionLoop が seed_aware_scheduler を作る経路で.
        return [call_fitness_with_seed(fitness_fn, ind, parent_seed=0) for ind in inds]
    return [fitness_fn(ind.genome) for ind in inds]


@dataclass
class EvolutionConfig:
    """1 run の設定."""

    max_generations: int = 50
    patience: int = 10  # best fitness 停滞検出 (生成数)
    diversity_floor: float = 1e-6  # これ以下なら多様性枯渇で停止
    out_dir: Path | None = None  # JSONL 出力先 (None なら無出力)
    log_progress: bool = True


@dataclass
class EvolutionResult:
    """run 全体の結果."""

    best_individual: Individual
    best_score: float
    final_population: Population
    stats_history: list[PopulationStats]
    stopped_reason: str
    elapsed_seconds: float

    def to_dict(self) -> dict:
        return {
            "best_score": float(self.best_score),
            "best_individual": self.best_individual.to_dict(),
            "stats_history": [s.to_dict() for s in self.stats_history],
            "stopped_reason": self.stopped_reason,
            "elapsed_seconds": float(self.elapsed_seconds),
            "final_generation": self.final_population.generation,
            "final_population_size": self.final_population.size,
        }


@dataclass
class EvolutionLoop:
    """1 世代を回す Loop. ``run()`` で max_generations まで進化.

    callable をすべて injection できるので, UCB selector 連携 / 実 LLM fitness /
    並列 scheduler のいずれも plug-in 可能.
    """

    fitness_fn: Fitness
    selection: SelectionFn = field(default_factory=lambda: TournamentSelection(k=3))
    crossover: CrossoverFn = field(default_factory=lambda: UniformCrossover(p=0.5))
    mutation: MutationFn = field(
        default_factory=lambda: ChainedMutation(mutations=(GaussianMutation(sigma=0.1, p=0.05),))
    )
    elitism: ElitismSelection = field(default_factory=lambda: ElitismSelection(top_n=2))
    scheduler: SchedulerFn = _serial_scheduler

    # -- main loop ---------------------------------------------------------

    def run(self, population: Population, config: EvolutionConfig) -> EvolutionResult:
        start = time.perf_counter()
        stats_history: list[PopulationStats] = []
        stopped_reason = "max_generations"
        best_so_far = float("-inf")
        stagnation = 0
        rng = np.random.default_rng(population.seed)

        for gen in range(config.max_generations + 1):
            # 1. 評価
            reports = self.scheduler(self.fitness_fn, population.individuals)
            for ind, rep in zip(population.individuals, reports, strict=True):
                ind.record_fitness(rep)

            # 2. 統計
            stats = population.compute_stats()
            stats_history.append(stats)
            if config.log_progress:
                _log_generation(stats)
            if config.out_dir is not None:
                _write_generation(config.out_dir, stats, population)

            # 3. 停滞検出
            if stats.best_score > best_so_far + 1e-12:
                best_so_far = stats.best_score
                stagnation = 0
            else:
                stagnation += 1
            if stagnation >= config.patience:
                stopped_reason = f"patience_exhausted ({stagnation} stagnant gens)"
                break

            # 4. 多様性枯渇検出
            if stats.diversity_l2 < config.diversity_floor:
                stopped_reason = f"diversity_collapsed ({stats.diversity_l2:.2e})"
                break

            # 5. 終了世代なら break (評価のみして次世代生成は不要)
            if gen >= config.max_generations:
                stopped_reason = "max_generations"
                break

            # 6. 次世代生成
            next_individuals = self._breed_next_generation(population, rng)
            next_seed = int(rng.integers(0, 2**31 - 1))
            population.replace(next_individuals, new_seed=next_seed)

        elapsed = time.perf_counter() - start
        return EvolutionResult(
            best_individual=population.best(),
            best_score=best_so_far,
            final_population=population,
            stats_history=stats_history,
            stopped_reason=stopped_reason,
            elapsed_seconds=elapsed,
        )

    # -- breed -------------------------------------------------------------

    def _breed_next_generation(
        self, population: Population, rng: np.random.Generator
    ) -> list[Individual]:
        next_gen_num = population.generation + 1
        next_individuals: list[Individual] = []

        # elitism: 上位 top_n をそのままコピー
        elites = self.elitism.select(population)
        for e in elites:
            next_individuals.append(
                Individual.from_genome(
                    e.genome,
                    parent_ids=(e.individual_id,),
                    birth_generation=next_gen_num,
                )
            )

        # 残り個体を crossover + mutation で生成
        while len(next_individuals) < population.size:
            parent_a = self.selection(population, rng)
            parent_b = self.selection(population, rng)
            child_genome = self.crossover(parent_a.genome, parent_b.genome, rng)
            child_genome = self.mutation(child_genome, rng)
            next_individuals.append(
                Individual.from_genome(
                    child_genome,
                    parent_ids=(parent_a.individual_id, parent_b.individual_id),
                    birth_generation=next_gen_num,
                )
            )

        return next_individuals


# ---------------------------------------------------------------------------
# log / persist helpers
# ---------------------------------------------------------------------------


def _log_generation(stats: PopulationStats) -> None:
    print(
        f"[gen {stats.generation:03d}] "
        f"best={stats.best_score:.4f} "
        f"mean={stats.mean_score:.4f} "
        f"std={stats.std_score:.4f} "
        f"diversity={stats.diversity_l2:.4f} "
        f"seed={stats.seed}"
    )


def _write_generation(out_dir: Path, stats: PopulationStats, population: Population) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    line = json.dumps(stats.to_dict(), ensure_ascii=False)
    with (out_dir / "generations.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    # snapshot は generation ごとに 1 ファイル (重い場合は config で off に)
    snap_path = out_dir / f"snapshot_gen_{stats.generation:04d}.json"
    snap_path.write_text(json.dumps(population.to_dict(), ensure_ascii=False), encoding="utf-8")


__all__ = ["EvolutionConfig", "EvolutionLoop", "EvolutionResult"]
