# SPDX-License-Identifier: Apache-2.0
"""Diversity preservation for v0.E (CE-24〜29).

ユーザー指示 (2026-05-21):
    「出来るだけ, 思考の軸が被らないように llive 亜種を生成する必要があります」

GA 古典の niching / fitness sharing / novelty search / quality-diversity の
集合体. 4 つの主要機構:

1. **LatinHypercubeInitialization** (E.14, CE-28) — 初期集団を空間的に分散
2. **NoveltyScore** (E.15, CE-27) — k-NN ベース新規性スコア
3. **DiversityPreservingGeneration** (E.16, CE-24) — 子の reject+resample
4. **DiversityMonitor** (E.18, CE-29) — 世代単位 metric + 閾値 alarm

参照:
- Goldberg & Richardson (1987). Fitness sharing.
- De Jong (1975) / Mahfoud (1995). Crowding.
- Lehman & Stanley (2008/2011). Novelty Search.
- Mouret & Clune (2015). MAP-Elites.

要件根拠: ``docs/requirements_v0.E_competitive_coevolution.md`` 0.8 節.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
from scipy.stats import qmc

from llive.perf.evolutionary.genome import Genome, GenomeBounds
from llive.perf.evolutionary.genome_3d import genome_flat_vector
from llive.perf.evolutionary.individual import Individual
from llive.perf.evolutionary.population import Population, PopulationStats

# ---------------------------------------------------------------------------
# E.14 — Latin Hypercube Initialization
# ---------------------------------------------------------------------------


def latin_hypercube_population(
    bounds: GenomeBounds,
    *,
    size: int,
    seed: int,
    labels: tuple[str, ...] = (),
    scramble: bool = True,
) -> Population:
    """LHS で初期集団を生成. uniform random より空間的に均等.

    scipy.stats.qmc.LatinHypercube を使う. seed は qmc に渡される
    (deterministic).

    Parameters
    ----------
    bounds : GenomeBounds
    size : int
    seed : int
    labels : tuple[str, ...]
        Genome label tuple.
    scramble : bool
        LHS の randomization (default True 推奨).
    """
    if size <= 0:
        raise ValueError("size must be > 0")
    n = bounds.n_dims
    sampler = qmc.LatinHypercube(d=n, scramble=scramble, seed=seed)
    raw = sampler.random(n=size)  # shape (size, n) in [0, 1]^n
    lower = np.asarray(bounds.lower, dtype=np.float64)
    upper = np.asarray(bounds.upper, dtype=np.float64)
    scaled = lower + raw * (upper - lower)
    individuals = [
        Individual.from_genome(
            Genome.from_values(scaled[i], bounds=bounds, labels=labels)
        )
        for i in range(size)
    ]
    return Population(
        individuals=individuals,
        bounds=bounds,
        generation=0,
        seed=seed,
        generation_seeds=[seed],
    )


# ---------------------------------------------------------------------------
# E.15 — Novelty Score
# ---------------------------------------------------------------------------


@dataclass
class NoveltyScorer:
    """k-NN ベース novelty score 計算機.

    novelty(x) = mean(distance(x, k-nearest in archive)).

    Archive は append-only で蓄積. 集団内 ↔ archive の双方を見る.
    Lehman-Stanley 2008/2011 の novelty search の核.

    Attributes
    ----------
    k : int
        k-nearest 近傍数. default 5.
    archive : list[np.ndarray]
        過去の genome value vector 群 (内部蓄積).
    archive_max_size : int
        Archive 上限 (default 1000). 上限超過は FIFO で古い entry を破棄.
    """

    k: int = 5
    archive: list[np.ndarray] = field(default_factory=list)
    archive_max_size: int = 1000

    def __post_init__(self) -> None:
        if self.k < 1:
            raise ValueError("k must be >= 1")
        if self.archive_max_size < 1:
            raise ValueError("archive_max_size must be >= 1")

    def add_to_archive(self, values: np.ndarray) -> None:
        """1 個体の genome values を archive に追加."""
        self.archive.append(np.asarray(values, dtype=np.float64).copy())
        if len(self.archive) > self.archive_max_size:
            # FIFO で先頭を捨てる
            self.archive = self.archive[-self.archive_max_size :]

    def add_population(self, pop: Population) -> None:
        for ind in pop.individuals:
            self.add_to_archive(genome_flat_vector(ind.genome))

    def novelty(self, values: np.ndarray) -> float:
        """1 個体の novelty score を返す.

        Archive が空 / k 未満なら 1.0 (最大). k 個以上なら k-NN 平均距離.
        """
        if not self.archive:
            return 1.0
        arr = np.asarray(values, dtype=np.float64)
        archive_arr = np.stack(self.archive)
        # L2 distance
        diffs = archive_arr - arr[None, :]
        dists = np.linalg.norm(diffs, axis=1)
        k_use = min(self.k, len(dists))
        nearest = np.sort(dists)[:k_use]
        return float(nearest.mean())

    def novelty_batch(self, pop: Population) -> np.ndarray:
        """集団全員の novelty score を一括計算 (shape: (size,))."""
        scores = np.zeros(pop.size, dtype=np.float64)
        for i, ind in enumerate(pop.individuals):
            scores[i] = self.novelty(genome_flat_vector(ind.genome))
        return scores


# ---------------------------------------------------------------------------
# E.16 — Diversity-Preserving Generation (breed-time novelty rejection)
# ---------------------------------------------------------------------------


@dataclass
class DiversityPreservingBreedFilter:
    """子個体生成時に novelty threshold で reject + resample する filter.

    EvolutionLoop の _breed_next_generation を直接書き換えるのではなく
    **生成後フィルタ** として使う設計:

        next_inds = loop._breed_next_generation(pop, rng)
        next_inds = filter.filter_children(next_inds, parents=pop, rng=rng)

    Attributes
    ----------
    scorer : NoveltyScorer
    min_novelty : float
        子個体に要求する最小 novelty (parent + sibling 比較). default 0.05.
    max_attempts : int
        1 child あたりの retry 上限. default 5. 超過しても採用 (集団 size 維持).
    novelty_pool : str
        ``parents`` (default, parent 集団のみ比較) / ``archive`` (scorer.archive
        も含める) / ``both`` (parents + archive).
    """

    scorer: NoveltyScorer
    min_novelty: float = 0.05
    max_attempts: int = 5
    novelty_pool: str = "both"

    def __post_init__(self) -> None:
        if self.min_novelty < 0:
            raise ValueError("min_novelty must be >= 0")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.novelty_pool not in ("parents", "archive", "both"):
            raise ValueError(f"unknown novelty_pool: {self.novelty_pool!r}")

    def filter_children(
        self,
        children: list[Individual],
        *,
        parents: Population,
        resample_fn: Callable[[], Individual],
        rng: np.random.Generator,
    ) -> list[Individual]:
        """各 child の novelty を計算し, threshold 未達なら resample.

        Parameters
        ----------
        children : list[Individual]
            crossover+mutation で生成された子集団.
        parents : Population
            親世代 (novelty 比較対象).
        resample_fn : Callable
            novelty 未達のとき新しい child を 1 個生成する factory.
        rng : np.random.Generator
            (Future use; not yet consumed by this filter.)

        Returns
        -------
        list[Individual]
            同じ長さの filtered children.
        """
        pool_vectors: list[np.ndarray] = []
        if self.novelty_pool in ("parents", "both"):
            for p in parents.individuals:
                pool_vectors.append(genome_flat_vector(p.genome))
        if self.novelty_pool in ("archive", "both"):
            pool_vectors.extend(self.scorer.archive)

        if not pool_vectors:
            # 何も pool に無いなら novelty unbounded — そのまま通す
            return children

        pool_arr = np.stack(pool_vectors)

        def _novelty(values: np.ndarray) -> float:
            diffs = pool_arr - values[None, :]
            dists = np.linalg.norm(diffs, axis=1)
            k_use = min(self.scorer.k, len(dists))
            return float(np.sort(dists)[:k_use].mean())

        filtered: list[Individual] = []
        for child in children:
            candidate = child
            attempts = 0
            while attempts < self.max_attempts and _novelty(
                genome_flat_vector(candidate.genome)
            ) < self.min_novelty:
                candidate = resample_fn()
                attempts += 1
            filtered.append(candidate)
        return filtered


# ---------------------------------------------------------------------------
# E.18 — Diversity Monitor
# ---------------------------------------------------------------------------


@dataclass
class DiversityMetrics:
    """1 世代の diversity 観察値."""

    generation: int
    n_individuals: int
    diversity_l2: float
    spread: float            # max pairwise distance
    median_distance: float
    bounding_volume_log: float  # log(prod(genome_range)) — 関心の領域比較用
    alarm: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "generation": int(self.generation),
            "n_individuals": int(self.n_individuals),
            "diversity_l2": float(self.diversity_l2),
            "spread": float(self.spread),
            "median_distance": float(self.median_distance),
            "bounding_volume_log": float(self.bounding_volume_log),
            "alarm": list(self.alarm),
        }


@dataclass
class DiversityMonitor:
    """世代単位 diversity metric の集計 + 閾値違反 alarm.

    EvolutionLoop.on_generation_end hook として使える:

        monitor = DiversityMonitor(min_diversity_l2=2.0)
        loop = EvolutionLoop(
            ...,
            on_generation_end=lambda pop, stats: monitor.observe(pop, stats),
        )

    Attributes
    ----------
    min_diversity_l2 : float
        diversity_l2 がこの値を下回ったら alarm.
    min_spread : float
        spread (max pairwise) が下回ったら alarm.
    history : list[DiversityMetrics]
        observe ごとに append される.
    on_alarm : Callable[[DiversityMetrics], None] | None
        alarm 発生時に呼ばれる callback.
    """

    min_diversity_l2: float = 1.0
    min_spread: float = 0.5
    history: list[DiversityMetrics] = field(default_factory=list)
    on_alarm: Callable[[DiversityMetrics], None] | None = None

    def __post_init__(self) -> None:
        if self.min_diversity_l2 < 0:
            raise ValueError("min_diversity_l2 must be >= 0")
        if self.min_spread < 0:
            raise ValueError("min_spread must be >= 0")

    def observe(
        self,
        pop: Population,
        stats: PopulationStats | None = None,
    ) -> DiversityMetrics:
        """1 世代の metric を計算 + history に append + alarm 判定."""
        n = pop.size
        gen = pop.generation if stats is None else stats.generation
        if n < 2:
            metrics = DiversityMetrics(
                generation=gen,
                n_individuals=n,
                diversity_l2=0.0,
                spread=0.0,
                median_distance=0.0,
                bounding_volume_log=0.0,
            )
        else:
            values = np.stack([genome_flat_vector(ind.genome) for ind in pop.individuals])
            # pairwise L2
            diffs = values[:, None, :] - values[None, :, :]
            dists = np.linalg.norm(diffs, axis=-1)
            iu = np.triu_indices(n, k=1)
            pairs = dists[iu]
            div_l2 = float(pairs.mean()) if len(pairs) else 0.0
            spread = float(pairs.max()) if len(pairs) else 0.0
            median_d = float(np.median(pairs)) if len(pairs) else 0.0
            ranges = values.max(axis=0) - values.min(axis=0)
            # bounding volume の log (添字幅が 0 の dim を避ける)
            log_range = np.log(np.clip(ranges, 1e-12, None)).sum()
            metrics = DiversityMetrics(
                generation=gen,
                n_individuals=n,
                diversity_l2=div_l2,
                spread=spread,
                median_distance=median_d,
                bounding_volume_log=float(log_range),
            )
        # alarm 判定
        if metrics.diversity_l2 < self.min_diversity_l2:
            metrics.alarm.append(
                f"diversity_l2 below threshold ({metrics.diversity_l2:.4f} < {self.min_diversity_l2})"
            )
        if metrics.spread < self.min_spread:
            metrics.alarm.append(
                f"spread below threshold ({metrics.spread:.4f} < {self.min_spread})"
            )
        self.history.append(metrics)
        if metrics.alarm and self.on_alarm is not None:
            self.on_alarm(metrics)
        return metrics


__all__ = [
    "DiversityMetrics",
    "DiversityMonitor",
    "DiversityPreservingBreedFilter",
    "NoveltyScorer",
    "latin_hypercube_population",
]
