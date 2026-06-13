# SPDX-License-Identifier: Apache-2.0
"""Scheduler — 並列 fitness 評価 (llive v0.B EV-07).

3 種:

* :func:`serial_scheduler` — Phase 1-2 default. シリアル評価.
* :class:`MultiprocessingScheduler` — CPU-bound fitness 向け (multiprocessing).
* :class:`AsyncioScheduler` — I/O-bound (LLM API) fitness 向け.

fitness 関数は **picklable** が前提 (multiprocessing 制約). lambda や閉包は
top-level 関数に分離する.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass

from llive.perf.evolutionary.fitness import Fitness
from llive.perf.evolutionary.individual import FitnessReport, Individual


def serial_scheduler(
    fitness_fn: Fitness, individuals: Iterable[Individual]
) -> list[FitnessReport]:
    """シリアル評価 (debug / test 用)."""
    return [fitness_fn(ind.genome) for ind in individuals]


# ---------------------------------------------------------------------------
# Multiprocessing
# ---------------------------------------------------------------------------


def _eval_one(args: tuple[Fitness, Individual]) -> tuple[str, FitnessReport]:
    """ProcessPoolExecutor で実行される最小関数 (top-level + picklable)."""
    fitness_fn, individual = args
    return (individual.individual_id, fitness_fn(individual.genome))


@dataclass
class MultiprocessingScheduler:
    """ProcessPoolExecutor で fitness を並列評価.

    fitness 関数は **picklable** が必須. lambda は使えない. top-level 関数
    または ``@dataclass`` の callable instance のみ.

    Attributes
    ----------
    n_workers : int
        ワーカー数. ``0`` 以下なら ``os.cpu_count()`` を採用.
    """

    n_workers: int = 0

    def __call__(
        self, fitness_fn: Fitness, individuals: Iterable[Individual]
    ) -> list[FitnessReport]:
        inds = list(individuals)
        n = self.n_workers if self.n_workers > 0 else None  # None で auto
        results: dict[str, FitnessReport] = {}
        with ProcessPoolExecutor(max_workers=n) as pool:
            futures = [pool.submit(_eval_one, (fitness_fn, ind)) for ind in inds]
            for fut in as_completed(futures):
                ind_id, report = fut.result()
                results[ind_id] = report
        # 入力順を保ったまま返す (Loop が zip で結合するため)
        return [results[ind.individual_id] for ind in inds]


# ---------------------------------------------------------------------------
# Asyncio
# ---------------------------------------------------------------------------


AsyncFitness = Callable[[object], Awaitable[FitnessReport]]


@dataclass
class AsyncioScheduler:
    """asyncio.gather で並列評価 (I/O-bound, 例: LLM API).

    fitness は ``async def`` 形式の AsyncFitness. concurrency_limit で
    同時実行数を制限可能 (rate limit 対策).
    """

    async_fitness: AsyncFitness
    concurrency_limit: int = 16

    def __post_init__(self) -> None:
        if self.concurrency_limit <= 0:
            raise ValueError("concurrency_limit must be > 0")

    def __call__(
        self,
        fitness_fn: Fitness,
        individuals: Iterable[Individual],
    ) -> list[FitnessReport]:
        return asyncio.run(self._run(list(individuals)))

    async def _run(self, individuals: list[Individual]) -> list[FitnessReport]:
        sem = asyncio.Semaphore(self.concurrency_limit)

        async def _gated(ind: Individual) -> FitnessReport:
            async with sem:
                return await self.async_fitness(ind.genome)

        return await asyncio.gather(*[_gated(ind) for ind in individuals])


__all__ = [
    "AsyncFitness",
    "AsyncioScheduler",
    "MultiprocessingScheduler",
    "serial_scheduler",
]
