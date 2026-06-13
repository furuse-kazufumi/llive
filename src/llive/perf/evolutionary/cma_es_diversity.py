# SPDX-License-Identifier: Apache-2.0
"""CMA-ES diversity loop 配線 — llive v0.F DIV-01 (genome diversity addendum).

既存 :class:`CMAESAdapter` (``cma_es.py``) を **既存の多様性機構** に接続する
orchestration driver。CMA-ES の ``ask()`` 候補を NoveltyScorer / novelty_lane で
評価し、fitness+novelty を MultiObjectiveSelector で多目的合成して ``tell()`` に
渡し、候補を MAPElitesGrid に behavior descriptor 化して投入する。

> **extend-only 原則 (addendum §1-3 / premap §5-1)**
>
> 本 module は既存 13 機構 (CMAESAdapter / NoveltyScorer /
> compute_novelty_scores / MultiObjectiveSelector / MAPElitesGrid /
> default_thought_features) を **import して使うのみ**。これらの class /
> function を再定義・改変しない。束ねる新 driver (本 module) だけが新規。
>
> **対象は ``c_factors`` の 40-dim continuous サブ空間専用** (addendum §1-2)。
> 離散 / bitmask dim は既存 GA operator のまま。新 dim を足さない。

# 接続図 (data flow)

```
  CMAESAdapter.ask()  ->  λ × 40 候補
        |                      |
        | frozen index clip    | (FrozenGene で freeze された factor index を固定)
        v                      v
  fitness_fn(x)          NoveltyScorer.novelty(x) / compute_novelty_scores
        |                      |
        +----------+-----------+
                   v
        MultiObjectiveSelector.select(fitness, novelty)   (多目的合成)
                   |
        +----------+-----------+
        v                      v
  CMAESAdapter.tell(...)   MAPElitesGrid.submit(Individual, fit, descriptor)
   (共分散 / step-size 更新)   (QD archive に cell 充填)
```

# frozen gene ガード (addendum §1-4 / premap §5-5)

``FrozenGene.gene_path`` が ``c_factors`` の factor / (factor, layer) を指す場合、
``ask()`` 出力をその flat index で **freeze 時点の値に固定 clip** し、CMA-ES が
mutate しないようにする。path 解釈は :func:`parse_frozen_factor_indices`。

References:
* addendum: ``docs/requirements_v0.F_genome_diversity_addendum.md`` §DIV-01.
* premap: ``docs/SPEC_COHERENCE_v0.J_premap.md`` §1, §2.3-2, §5.
* Hansen (2016) arXiv:1604.00772 / Lehman & Stanley (2008/2011) / Mouret & Clune (2015).
"""
from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np

# --- 既存機構 (import only — 一切改変しない) -------------------------------
from llive.perf.evolutionary.cma_es import CMAESAdapter
from llive.perf.evolutionary.diversity import NoveltyScorer
from llive.perf.evolutionary.frozen_gene import FrozenGene
from llive.perf.evolutionary.genome import Genome, GenomeBounds
from llive.perf.evolutionary.genome_version import (
    FACTOR_GENOME_DIM,
    NUM_MEMORY_LAYERS,
    NUM_THOUGHT_FACTORS,
    assert_factor_dim,
)
from llive.perf.evolutionary.individual import Individual
from llive.perf.evolutionary.novelty_lane import (
    MultiObjectiveSelector,
    NoveltyDescriptor,
    compute_novelty_scores,
)
from llive.perf.evolutionary.persona import THOUGHT_FACTORS
from llive.perf.evolutionary.quality_diversity import MAPElitesGrid

# c_factors 40-dim の box 制約 ([0, 1])。新 dim は足さない。
_FACTOR_BOUNDS: tuple[float, float] = (0.0, 1.0)

# behavior descriptor 用の代表因子 index (default_thought_features と同じ思想)。
_STRUCTURIZE_IDX: int = THOUGHT_FACTORS.index("factor_structurize")
_EXPLORATION_IDX: int = THOUGHT_FACTORS.index("factor_exploration")


# ---------------------------------------------------------------------------
# Frozen gene path 解釈
# ---------------------------------------------------------------------------

# 受理する path 形式:
#   "c_factors[<factor>][<layer>]"  -> 単一 (factor, layer) cell
#   "c_factors[<factor>]"           -> factor 行全体 (全 layer)
#   "c-factors..." / "c_factors..." 大小・ハイフン許容
_CFACTORS_CELL_RE = re.compile(
    r"^c[_-]?factors\[(\d+)\]\[(\d+)\]$", re.IGNORECASE
)
_CFACTORS_ROW_RE = re.compile(r"^c[_-]?factors\[(\d+)\]$", re.IGNORECASE)


def parse_frozen_factor_indices(
    frozen_genes: Sequence[FrozenGene],
    *,
    n_factors: int = NUM_THOUGHT_FACTORS,
    n_layers: int = NUM_MEMORY_LAYERS,
    now_iso: str | None = None,
) -> list[int]:
    """``FrozenGene`` 群から c_factors の **flat index** 集合を抽出する。

    flat index は ``factor * n_layers + layer`` (row-major、``as_flat()`` と整合)。
    期限切れ (``is_expired``) の gene は無視する。c_factors を指さない path は
    無視する (他 chromosome の freeze は CMA-ES 対象外)。

    Args:
        frozen_genes: 凍結 gene の列。
        n_factors: 思考因子数 (default 10)。
        n_layers: メモリ層数 (default 4)。
        now_iso: 期限判定の基準時刻 (テスト再現性のため引数化)。

    Returns:
        昇順・重複なしの flat index list (各値 ∈ [0, n_factors*n_layers))。
    """
    indices: set[int] = set()
    for fg in frozen_genes:
        if fg.is_expired(now_iso):
            continue
        path = fg.gene_path.strip()
        m_cell = _CFACTORS_CELL_RE.match(path)
        if m_cell is not None:
            fi, li = int(m_cell.group(1)), int(m_cell.group(2))
            if 0 <= fi < n_factors and 0 <= li < n_layers:
                indices.add(fi * n_layers + li)
            continue
        m_row = _CFACTORS_ROW_RE.match(path)
        if m_row is not None:
            fi = int(m_row.group(1))
            if 0 <= fi < n_factors:
                for li in range(n_layers):
                    indices.add(fi * n_layers + li)
            continue
        # c_factors を指さない path は CMA-ES 対象外 — 無視
    return sorted(indices)


# ---------------------------------------------------------------------------
# Behavior descriptor helpers (新 dim を足さない)
# ---------------------------------------------------------------------------


def candidate_to_thought_features(x: np.ndarray) -> tuple[float, float]:
    """40-dim c_factors flatten 候補 → thought_factor 2 軸 descriptor。

    :func:`quality_diversity.default_thought_features` と同じ代表因子
    (structurize / exploration) を使うが、PersonaComposition ではなく
    生 c_factors 行列の **factor 行平均** から読み出す (CMA-ES 候補に PersonaComp
    が無いため)。matrix shape は (10, 4) に reshape して行平均を取る。
    """
    mat = np.asarray(x, dtype=np.float64).reshape(NUM_THOUGHT_FACTORS, NUM_MEMORY_LAYERS)
    row_means = mat.mean(axis=1)  # 各因子の層平均 (10,)
    return (float(row_means[_STRUCTURIZE_IDX]), float(row_means[_EXPLORATION_IDX]))


def candidate_to_map_elites_features(
    x: np.ndarray,
) -> tuple[float, float, float, float]:
    """40-dim 候補 → MAPElitesGrid 4 軸 descriptor (persona 2 軸 + thought 2 軸)。

    MAPElitesGrid は (2 persona 軸 + 2 thought_factor 軸) = 4 軸を要求する。
    CMA-ES 候補に persona は無いので persona 2 軸は flatten 全体の
    (mean, std) で代用し、thought 2 軸は :func:`candidate_to_thought_features`
    を使う。grid 自体は再定義しない (4 軸契約を尊重)。
    """
    flat = np.asarray(x, dtype=np.float64).reshape(-1)
    p_mean = float(flat.mean())
    p_std = float(flat.std())
    t_struct, t_explore = candidate_to_thought_features(flat)
    return (p_mean, p_std, t_struct, t_explore)


def _candidate_to_individual(
    x: np.ndarray, bounds: GenomeBounds, generation: int
) -> Individual:
    """40-dim 候補を [0,1]^40 Genome に包んだ Individual に変換 (MAP-Elites 投入用)。"""
    flat = np.clip(np.asarray(x, dtype=np.float64).reshape(-1), *_FACTOR_BOUNDS)
    genome = Genome.from_values(flat, bounds=bounds)
    return Individual.from_genome(genome, birth_generation=generation)


# ---------------------------------------------------------------------------
# Generation result
# ---------------------------------------------------------------------------


@dataclass
class CMAESDiversityGenerationResult:
    """1 世代の CMA-ES diversity loop 結果スナップショット (観測用)。"""

    generation: int
    candidates: np.ndarray              # (λ, 40) frozen clip 適用後
    fitnesses: np.ndarray               # (λ,)
    novelty_scores: np.ndarray          # (λ,)
    selected_ids: list[str]             # MultiObjectiveSelector 出力
    grid_accepted: int                  # この世代で grid に新規採用された cell 数
    grid_coverage: float                # 世代末の grid coverage
    sigma: float                        # tell 後の step-size


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


@dataclass
class CMAESDiversityDriver:
    """CMA-ES を既存多様性機構に束ねる orchestration driver (DIV-01)。

    既存 class を **保持 (compose) するだけ** で改変しない。``adapter`` が
    None なら 40-dim 専用の :class:`CMAESAdapter` を内部生成する。

    Attributes
    ----------
    adapter : CMAESAdapter | None
        CMA-ES 本体。None なら dim=40 で生成。dim != 40 は拒否 (c_factors 専用)。
    novelty_scorer : NoveltyScorer | None
        genome 空間 k-NN novelty (archive 蓄積)。None なら default 生成。
    grid : MAPElitesGrid | None
        QD archive。None なら default 生成。
    selector : MultiObjectiveSelector | None
        fitness+novelty 多目的選択。None なら n:m を λ の 0.6:0.4 で生成。
    frozen_genes : Sequence[FrozenGene]
        freeze 対象 gene。c_factors を指すものは ask() 出力を固定 clip する。
    novelty_weight : float
        tell() に渡す合成 fitness の novelty 重み。``fit + w * novelty``。
    novelty_distance : str
        compute_novelty_scores の距離関数。
    rng : np.random.Generator | None
        再現性用 RNG。frozen 固定値の初期 anchor に使う。
    """

    adapter: CMAESAdapter | None = None
    novelty_scorer: NoveltyScorer | None = None
    grid: MAPElitesGrid | None = None
    selector: MultiObjectiveSelector | None = None
    frozen_genes: Sequence[FrozenGene] = field(default_factory=tuple)
    novelty_weight: float = 0.4
    novelty_distance: str = "euclidean"
    rng: np.random.Generator | None = None

    # 内部状態
    _bounds: GenomeBounds = field(init=False, repr=False)
    _frozen_idx: list[int] = field(init=False, repr=False)
    _frozen_values: np.ndarray = field(init=False, repr=False)
    _generation: int = field(init=False, default=0, repr=False)

    def __post_init__(self) -> None:
        if self.novelty_weight < 0:
            raise ValueError(
                f"novelty_weight must be >= 0, got {self.novelty_weight}"
            )
        if self.rng is None:
            self.rng = np.random.default_rng()

        # CMA-ES adapter — c_factors 40-dim 専用 (新 dim を足さない)
        if self.adapter is None:
            self.adapter = CMAESAdapter(
                dim=FACTOR_GENOME_DIM,
                bounds=_FACTOR_BOUNDS,
                mean0=np.full(FACTOR_GENOME_DIM, 0.5),
                rng=self.rng,
            )
        if self.adapter.dim != FACTOR_GENOME_DIM:
            raise ValueError(
                f"CMA-ES diversity loop is c_factors 40-dim only; "
                f"adapter.dim={self.adapter.dim} (expected {FACTOR_GENOME_DIM})"
            )

        if self.novelty_scorer is None:
            self.novelty_scorer = NoveltyScorer(k=5)
        if self.grid is None:
            self.grid = MAPElitesGrid()
        if self.selector is None:
            lam = self.adapter.population_size
            n_fit = max(1, int(round(lam * 0.6)))
            m_nov = max(0, lam - n_fit)
            self.selector = MultiObjectiveSelector(n_fitness=n_fit, m_novelty=m_nov)

        # [0,1]^40 box (Genome 包み込み用)
        self._bounds = GenomeBounds(
            lower=tuple([_FACTOR_BOUNDS[0]] * FACTOR_GENOME_DIM),
            upper=tuple([_FACTOR_BOUNDS[1]] * FACTOR_GENOME_DIM),
        )

        # frozen gene → flat index + freeze 時点 anchor 値 (mean を採用)
        self._frozen_idx = parse_frozen_factor_indices(self.frozen_genes)
        anchor = np.asarray(self.adapter.mean, dtype=np.float64).reshape(-1)
        self._frozen_values = anchor[self._frozen_idx].copy() if self._frozen_idx else np.empty(0)

    # ----- frozen guard ---------------------------------------------------

    def _apply_frozen_clip(self, candidates: np.ndarray) -> np.ndarray:
        """``ask()`` 出力の frozen index を anchor 値に固定する (mutate 禁止)。"""
        if not self._frozen_idx:
            return candidates
        out = np.array(candidates, dtype=np.float64, copy=True)
        out[:, self._frozen_idx] = self._frozen_values[None, :]
        return out

    @property
    def frozen_indices(self) -> list[int]:
        """freeze された c_factors flat index (観測用)。"""
        return list(self._frozen_idx)

    @property
    def generation(self) -> int:
        return self._generation

    # ----- 1 世代 step ----------------------------------------------------

    def step(
        self,
        fitness_fn: Callable[[np.ndarray], float],
        *,
        minimize: bool = True,
    ) -> CMAESDiversityGenerationResult:
        """CMA-ES diversity loop を 1 世代回す。

        Args:
            fitness_fn: 40-dim 候補 → fitness (scalar)。``minimize`` 規約に従う。
            minimize: True なら fitness 小が良い (CMA-ES tell の規約)。

        Returns:
            CMAESDiversityGenerationResult — 候補 / fitness / novelty / 選択 ID /
            grid 採用数 / coverage / sigma。

        Note:
            既存 class の API は ``ask`` / ``tell`` / ``novelty`` /
            ``compute_novelty_scores`` / ``select`` / ``submit`` を呼ぶのみ。
        """
        assert self.adapter is not None
        assert self.novelty_scorer is not None
        assert self.grid is not None
        assert self.selector is not None

        # 1. ask() → frozen clip
        raw = self.adapter.ask()
        candidates = self._apply_frozen_clip(raw)
        assert_factor_dim(candidates[0])  # 40-dim 不変条件 (premap §5-2)
        lam = candidates.shape[0]

        # 2. fitness
        fitnesses = np.array(
            [float(fitness_fn(candidates[i])) for i in range(lam)],
            dtype=np.float64,
        )

        # 3. novelty (genome 空間 archive k-NN + behavior 空間 k-NN を併用)
        archive_novelty = np.array(
            [self.novelty_scorer.novelty(candidates[i]) for i in range(lam)],
            dtype=np.float64,
        )
        ids = [f"g{self._generation}_c{i}" for i in range(lam)]
        descriptors = [
            (ids[i], NoveltyDescriptor(embedding=tuple(candidates[i].tolist())))
            for i in range(lam)
        ]
        behavior_scores = compute_novelty_scores(
            descriptors,
            k=min(self.novelty_scorer.k, lam),
            distance=self.novelty_distance,
        )
        behavior_novelty = np.array([s.score for s in behavior_scores], dtype=np.float64)
        novelty = 0.5 * archive_novelty + 0.5 * behavior_novelty

        # archive を更新 (次世代以降の novelty 比較用)
        for i in range(lam):
            self.novelty_scorer.add_to_archive(candidates[i])

        # 4. multi-objective select (fitness は大が良い形に統一して selector へ)
        fitness_for_select = -fitnesses if minimize else fitnesses
        fitness_map = {ids[i]: float(fitness_for_select[i]) for i in range(lam)}
        novelty_map = {ids[i]: float(novelty[i]) for i in range(lam)}
        selected_ids = self.selector.select(fitness_map, novelty_map)

        # 5. tell() — 合成 fitness (fitness + w * novelty)。minimize 規約のため
        #    novelty が大きいほど良い → minimize 側では引く。
        if minimize:
            combined = fitnesses - self.novelty_weight * novelty
        else:
            combined = fitnesses + self.novelty_weight * novelty
        self.adapter.tell(candidates, combined, minimize=minimize)

        # 6. MAP-Elites grid に投入 (behavior descriptor 化)
        #    grid fitness は「大が良い」前提なので minimize 側は符号反転。
        grid_fit = -fitnesses if minimize else fitnesses
        accepted = 0
        for i in range(lam):
            ind = _candidate_to_individual(
                candidates[i], self._bounds, self._generation
            )
            feats = candidate_to_map_elites_features(candidates[i])
            if self.grid.submit(
                ind, float(grid_fit[i]), feats, generation=self._generation
            ):
                accepted += 1

        result = CMAESDiversityGenerationResult(
            generation=self._generation,
            candidates=candidates,
            fitnesses=fitnesses,
            novelty_scores=novelty,
            selected_ids=selected_ids,
            grid_accepted=accepted,
            grid_coverage=self.grid.coverage,
            sigma=self.adapter.sigma,
        )
        self._generation += 1
        return result

    def run(
        self,
        fitness_fn: Callable[[np.ndarray], float],
        *,
        generations: int,
        minimize: bool = True,
    ) -> list[CMAESDiversityGenerationResult]:
        """``generations`` 世代を回し、各世代の結果 list を返す。"""
        if generations < 1:
            raise ValueError(f"generations must be >= 1, got {generations}")
        return [
            self.step(fitness_fn, minimize=minimize) for _ in range(generations)
        ]


__all__ = [
    "CMAESDiversityDriver",
    "CMAESDiversityGenerationResult",
    "candidate_to_map_elites_features",
    "candidate_to_thought_features",
    "parse_frozen_factor_indices",
]
