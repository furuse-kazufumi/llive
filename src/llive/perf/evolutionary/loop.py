# SPDX-License-Identifier: Apache-2.0
"""EvolutionLoop — 1 世代 = evaluate → select → breed → mutate → 次世代 (llive v0.B EV-06).

Phase 2 (本セッション): SerialScheduler のみ.
Phase 3 で MultiprocessingScheduler / AsyncioScheduler を ``scheduler`` module
で提供.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

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
    """1 run の設定.

    大規模集団 + 長時間運用 (ユーザー要望 2026-05-21) のため:
    - ``max_wallclock_seconds`` で時間予算
    - ``checkpoint_every`` で 1 世代単位の snapshot 書出し
    - ``resume_from`` で snapshot からの再開
    """

    max_generations: int = 50
    patience: int = 10  # best fitness 停滞検出 (生成数)
    diversity_floor: float = 1e-6  # これ以下なら多様性枯渇で停止
    out_dir: Path | None = None  # JSONL 出力先 (None なら無出力)
    log_progress: bool = True
    # 大規模集団対応 (v0.C 追加, 後方互換 default = 無効)
    max_wallclock_seconds: float | None = None
    """時間予算. None なら無制限. 超過で safely 停止."""
    checkpoint_every: int = 1
    """N 世代ごとに snapshot を書く (out_dir が設定されているとき)."""
    resume_from: Path | None = None
    """snapshot_gen_NNNN.json から再開. out_dir/snapshot_gen_*.json を想定."""
    max_stall_generations: int | None = None
    """**hard collapse guard**: 集団が完全収束 (distinct genome 数 == 1) した状態が
    連続でこの世代数続いたら ``population_collapsed`` で停止する。patience (best 停滞)
    や diversity_floor (float 閾値) とは **独立** の最終安全弁で、長時間 run でそれら
    を無効化していても「全個体が同一になって同じ結果を吐き続ける空回り」を確実に止める
    (ユーザー要望 2026-05-24)。``None`` で無効 (後方互換)。EvolutionLoop 自体は
    ``max_generations`` で必ず有界なので真の無限ループにはならないが、本ガードは
    無駄な長時間空回りを早期に断つ。"""


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

    Phase 0.10 追加: ``on_generation_end`` hook で世代終了時に任意の処理を
    走らせる. lineage の winners.jsonl 自動 append 等に使う.
    """

    fitness_fn: Fitness
    selection: SelectionFn = field(default_factory=lambda: TournamentSelection(k=3))
    crossover: CrossoverFn = field(default_factory=lambda: UniformCrossover(p=0.5))
    mutation: MutationFn = field(
        default_factory=lambda: ChainedMutation(mutations=(GaussianMutation(sigma=0.1, p=0.05),))
    )
    elitism: ElitismSelection = field(default_factory=lambda: ElitismSelection(top_n=2))
    scheduler: SchedulerFn = _serial_scheduler
    on_generation_end: Callable[[Population, PopulationStats], None] | None = None
    """世代終了 (評価 + 統計後) に呼ばれる任意 hook. None なら no-op.

    例: ``on_generation_end=lambda pop, stats:
    write_winners_jsonl("out/winners.jsonl", pop, top_n=3)`` で世代ごとに
    上位 3 体を JSONL に追記できる.
    """
    on_population_bred: (
        Callable[[list[Individual], Population, np.random.Generator], list[Individual]]
        | None
    ) = None
    """次世代を breed した直後 (population.replace の前) に呼ばれる任意 hook.

    bred 個体リスト・親世代 population・rng を受け取り、変換した個体リストを返す
    (None なら no-op で素通し)。lldarwin Stage1.5 の lineage-niched 中立貯蔵庫
    (絶滅系統の re-inject) はここで bred リストの一部を貯蔵庫 elite に置換する。
    返り値の個体数は population.size と一致させること (呼び出し側責務)。
    """

    # -- main loop ---------------------------------------------------------

    def run(self, population: Population, config: EvolutionConfig) -> EvolutionResult:
        start = time.perf_counter()
        stats_history: list[PopulationStats] = []
        stopped_reason = "max_generations"
        best_so_far = float("-inf")
        stagnation = 0
        collapse_streak = 0  # 連続で全個体同一だった世代数 (hard collapse guard)

        # ---- resume_from が指定されていれば snapshot から再開 ----
        if config.resume_from is not None:
            resumed = _resume_from_snapshot(config.resume_from)
            if resumed is not None:
                # bounds も同期する (B-LOGIC-3): しないと resumed 個体の genome dim と
                # population.bounds dim が食い違い、以後の operator/clip が破綻する。
                population.individuals = resumed.individuals
                population.bounds = resumed.bounds
                population.generation = resumed.generation
                population.seed = resumed.seed
                population.generation_seeds = list(resumed.generation_seeds)
                # snapshot 整合性検証 (fail-closed)。flat genome のみ: Genome3D は
                # 単一 bounds を持たず (population.bounds is None) 次元検証の対象外。
                if population.bounds is not None:
                    for ind in population.individuals:
                        n_dims = getattr(ind.genome, "n_dims", None)
                        if n_dims is not None and n_dims != population.bounds.n_dims:
                            raise ValueError(
                                f"resumed individual genome dim ({n_dims}) != "
                                f"snapshot bounds dim ({population.bounds.n_dims}); "
                                "snapshot が破損している可能性。"
                            )

        rng = np.random.default_rng(population.seed)

        for gen in range(config.max_generations + 1):
            # ---- 時間予算超過チェック (v0.C 大規模集団対応) ----
            if config.max_wallclock_seconds is not None:
                elapsed = time.perf_counter() - start
                if elapsed >= config.max_wallclock_seconds:
                    stopped_reason = (
                        f"wallclock_budget_exhausted ({elapsed:.1f}s / "
                        f"{config.max_wallclock_seconds:.1f}s)"
                    )
                    break
            # 1. 評価 — Phase 3.5: seed-aware path で per-individual sub_seed を派生.
            #    Default scheduler は population.seed を見ない (1 引数 shape) ので,
            #    seed-aware fitness の場合は loop 側で個別に評価ループを回す.
            if fitness_accepts_seed(self.fitness_fn) and self.scheduler is _serial_scheduler:
                reports = [
                    call_fitness_with_seed(self.fitness_fn, ind, parent_seed=population.seed)
                    for ind in population.individuals
                ]
            else:
                reports = self.scheduler(self.fitness_fn, population.individuals)
            for ind, rep in zip(population.individuals, reports, strict=True):
                ind.record_fitness(rep)

            # 2. 統計
            stats = population.compute_stats()
            stats_history.append(stats)
            if config.log_progress:
                _log_generation(stats)
            if config.out_dir is not None and stats.generation % max(1, config.checkpoint_every) == 0:
                _write_generation(config.out_dir, stats, population)
            # Phase 0.10: 世代終了 hook (lineage 自動書き出し等)
            if self.on_generation_end is not None:
                try:
                    self.on_generation_end(population, stats)
                except Exception as exc:
                    # hook の失敗で run 全体を止めない
                    if config.log_progress:
                        print(f"[gen {stats.generation:03d}] on_generation_end hook failed: {exc}")

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

            # 4.5. hard collapse guard (patience/diversity_floor とは独立)。
            #      全個体が literally 同一 genome (distinct==1) の状態が連続したら停止。
            #      長時間 run で patience/diversity_floor を無効化していても「同じ結果を
            #      吐き続ける空回り」を確実に断つ最終安全弁 (ユーザー要望 2026-05-24)。
            #      frozen genome は hashable なので set で distinct 数を数えられる。
            if config.max_stall_generations is not None:
                distinct = len({ind.genome for ind in population.individuals})
                collapse_streak = collapse_streak + 1 if distinct <= 1 else 0
                if collapse_streak >= config.max_stall_generations:
                    stopped_reason = (
                        f"population_collapsed ({collapse_streak} gens all-identical)"
                    )
                    break

            # 5. 終了世代なら break (評価のみして次世代生成は不要)
            if gen >= config.max_generations:
                stopped_reason = "max_generations"
                break

            # 6. 次世代生成
            next_individuals = self._breed_next_generation(population, rng)
            # Stage1.5: bred 直後の population 変換 hook (lineage 中立貯蔵庫の re-inject 等)。
            if self.on_population_bred is not None:
                try:
                    transformed = self.on_population_bred(next_individuals, population, rng)
                    if transformed:
                        next_individuals = transformed
                except Exception as exc:  # hook 失敗で run 全体を止めない
                    if config.log_progress:
                        print(f"[gen {stats.generation:03d}] on_population_bred hook failed: {exc}")
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


def _resume_from_snapshot(path: Path | str) -> Population | None:
    """snapshot JSON (Population.to_dict()) から Population を復元.

    ``path`` がファイルなら直接読む. ディレクトリなら ``snapshot_gen_*.json``
    の最新を選ぶ.

    Returns
    -------
    Population | None
        復元できなければ None.
    """
    p = Path(path)
    if not p.exists():
        return None
    if p.is_dir():
        # 最新世代の snapshot を探す
        candidates = sorted(p.glob("snapshot_gen_*.json"))
        if not candidates:
            return None
        p = candidates[-1]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return Population.from_dict(data)


__all__ = ["EvolutionConfig", "EvolutionLoop", "EvolutionResult"]
