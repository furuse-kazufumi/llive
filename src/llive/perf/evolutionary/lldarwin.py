# SPDX-License-Identifier: Apache-2.0
"""lldarwin — multi-pressure selection (選択圧コンポーネント).

設計正本: fullsense ``docs/vision/LLDARWIN_DESIGN.md``。

lleval（眼鏡＝評価）が個体の ``FitnessReport.breakdown`` に入れた**複数の選択圧
(pressure)** を、集約せず **ε-lexicase で独立評価**して淘汰する。単一スカラー fitness の
argmax（``fitness_rich`` の ``nearest=max(sims)`` 単一化 = best=1.0 飽和の真因, 要件 SEL-2）を
避け、ある軸で突出した specialist（他軸で平凡）を生存させて多極構造を自動維持する。

破綻回避（世代を重ねても全滅しない, ユーザー 2026-05-25）:
  - :class:`MinimalCriterionGate` — 各軸の最低基準で繁殖可否（SEL-4）。全員 fail なら
    gate を無視（monoculture/全滅を構造的に防ぐ）。
  - :func:`standardize_breakdowns` — 集団内 per-dim z-score（STD-1）。「全軸平均高」＝
    無特徴を優位にせず、逸脱（中心からの距離）を選択圧に（SEL-1 中央一致除外）。

既存の :class:`~llive.perf.evolutionary.mating.LexicaseSelection`（ε付き・実装済だが未配線）を
主選択に再利用する薄いオーケストレータ。``EvolutionLoop.selection`` に注入して使う。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from llive.perf.evolutionary.diversity import NoveltyScorer
from llive.perf.evolutionary.individual import Individual
from llive.perf.evolutionary.mating import LexicaseSelection
from llive.perf.evolutionary.population import Population
from llive.perf.evolutionary.quality_diversity import FactorSubspaceNovelty

#: 個体ごとの導出値・カテゴリ index で、独立した選択圧 (pressure) ではないため
#: lexicase の case から既定で除外するキー。``factor_score`` は max-archetype の
#: 単一スカラー (= argmax, SEL-2 違反 → best=1.0 飽和の真因) を再導入してしまい、
#: ``nearest_persona_idx`` は順序に意味のないカテゴリ index を「大きいほど良い」と
#: 誤解釈させる。どちらも淘汰圧から外す (Stage1, 設計 §1.1 SEL-2)。
DEFAULT_EXCLUDED_CRITERIA: frozenset[str] = frozenset(
    {"factor_score", "nearest_persona_idx"}
)


def _numeric_breakdown(ind: Individual) -> dict[str, float]:
    """個体の fitness.breakdown から数値 criterion だけを抽出（未評価なら空 dict）."""
    fitness = getattr(ind, "fitness", None)
    bd = getattr(fitness, "breakdown", None) or {}
    out: dict[str, float] = {}
    for key, val in bd.items():
        if isinstance(val, bool):  # bool は数値扱いしない
            continue
        if isinstance(val, (int, float)):
            out[key] = float(val)
    return out


def _infer_numeric_criteria(
    individuals: list[Individual],
    exclude: frozenset[str] = frozenset(),
) -> tuple[str, ...]:
    """集団全体の breakdown から数値 criterion キーを出現順で抽出.

    ``exclude`` のキー (導出スカラー / カテゴリ index 等) は淘汰圧から外す。
    """
    keys: list[str] = []
    seen: set[str] = set()
    for ind in individuals:
        for key in _numeric_breakdown(ind):
            if key in exclude or key in seen:
                continue
            seen.add(key)
            keys.append(key)
    return tuple(keys)


@dataclass
class MinimalCriterionGate:
    """各 pressure 軸の最低基準で繁殖可否を判定（要件 SEL-4, 全滅回避）.

    ``criteria[axis]`` = その軸で満たすべき最低スコア。個体の breakdown が
    **全軸で基準以上**なら通過。該当軸を持たない個体はその軸を skip（緩和）。
    呼び出し側（:class:`MultiPressureSelector`）は**全個体が落ちる場合 gate を無視**し、
    全滅を構造的に防ぐ。
    """

    criteria: dict[str, float]
    higher_is_better: bool = True

    def passes(self, breakdown: dict[str, float]) -> bool:
        for axis, threshold in self.criteria.items():
            if axis not in breakdown:
                continue
            value = breakdown[axis]
            if self.higher_is_better and value < threshold:
                return False
            if not self.higher_is_better and value > threshold:
                return False
        return True


def standardize_breakdowns(
    individuals: list[Individual], criteria: tuple[str, ...]
) -> dict[str, dict[str, float]]:
    """集団内 per-dim z-score（要件 STD-1, 中央一致除外）.

    各 criterion 軸を集団内で z-score 化した ``{individual_id: {axis: z}}`` を返す。
    分散ほぼ 0 の軸（全個体が同値＝無特徴）は 0.0（優位を得ない）。
    """
    by_id: dict[str, dict[str, float]] = {
        ind.individual_id: {} for ind in individuals
    }
    for axis in criteria:
        ids: list[str] = []
        vals: list[float] = []
        for ind in individuals:
            bd = _numeric_breakdown(ind)
            if axis in bd:
                ids.append(ind.individual_id)
                vals.append(bd[axis])
        if not vals:
            continue
        arr = np.asarray(vals, dtype=float)
        mu = float(arr.mean())
        sd = float(arr.std())
        for iid, value in zip(ids, vals):
            by_id[iid][axis] = (value - mu) / sd if sd > 1e-12 else 0.0
    return by_id


@dataclass
class MultiPressureSelector:
    """複数選択圧の多目的淘汰（lldarwin の中核）.

    pressure profile（個体の breakdown にある複数 criterion）を集約せず ε-lexicase で
    独立評価する。``EvolutionLoop.selection`` に注入して 1 体ずつ親を選ぶ。

    Parameters
    ----------
    criteria:
        breakdown のキー（pressure 名）。空 tuple なら集団の breakdown から数値キーを
        動的抽出（例 ``fitness_rich`` の ``archetype::*`` 等）。``exclude_criteria`` の
        キーは自動抽出時に淘汰圧から外す。
    epsilon:
        ε-lexicase の許容範囲（同点扱い）。
    gate:
        :class:`MinimalCriterionGate`（None なら gate 無し）。全個体が落ちる場合は無視。
    higher_is_better:
        True なら各軸とも大きいほど良い。
    exclude_criteria:
        自動抽出時に除外するキー。既定 :data:`DEFAULT_EXCLUDED_CRITERIA`
        (``factor_score`` = argmax / ``nearest_persona_idx`` = カテゴリ index)。
        明示 ``criteria`` 指定時は適用しない（呼び出し側の指定を尊重）。
    use_novelty:
        True なら毎世代 k-NN novelty（過去世代 archive との平均距離）を z-score 化して
        ``breakdown['novelty']`` に書き、追加の lexicase case にする。停滞時に集団から
        外れた個体へ探索圧をかけ、空いたニッチを埋め戻す（``poc_evolution_env`` で
        行動 monoculture 0.05 を実証した核機構, 設計 §6 Stage1）。
    novelty_k:
        novelty の k-NN 近傍数。
    factor_subspace_weight:
        factor 部分空間 novelty のブレンド比 [0, 1]（QD-3）。0 で無効（既定）。>0 かつ
        ``factor_extractor`` 指定時、全体 novelty と factor novelty を各々 z-score 化して
        ``(1-w)·full + w·factor`` でブレンドし意味次元の多様性を個別保護する（PoC#6）。
    factor_extractor:
        個体 ``genome`` → factor 部分空間ベクトルを返す callable。循環 import 回避のため
        呼び出し側（lldarwin_v2）が注入する。
    """

    criteria: tuple[str, ...] = ()
    epsilon: float = 0.01
    gate: MinimalCriterionGate | None = None
    higher_is_better: bool = True
    exclude_criteria: frozenset[str] = DEFAULT_EXCLUDED_CRITERIA
    use_novelty: bool = False
    novelty_k: int = 5
    factor_subspace_weight: float = 0.0
    factor_extractor: Callable[[object], np.ndarray] | None = None
    _scorer: NoveltyScorer | None = field(
        default=None, init=False, repr=False, compare=False
    )
    _factor_novelty: FactorSubspaceNovelty | None = field(
        default=None, init=False, repr=False, compare=False
    )
    _pop_sig: tuple[int, tuple[str, ...]] | None = field(
        default=None, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if not (0.0 <= self.factor_subspace_weight <= 1.0):
            raise ValueError(
                "factor_subspace_weight must be in [0, 1], got "
                f"{self.factor_subspace_weight}"
            )

    @staticmethod
    def _zscore(raw: np.ndarray) -> np.ndarray:
        """集団内 z-score（分散ほぼ 0 = 無特徴は 0, SEL-1/STD-1）."""
        mu = float(raw.mean())
        sd = float(raw.std())
        if sd <= 1e-12:
            return np.zeros_like(raw)
        return (raw - mu) / sd

    def _ensure_novelty(self, population: Population) -> None:
        """集団（世代）ごとに 1 回だけ novelty を計算し z-score 化して書き込む.

        novelty = 過去世代 archive との k-NN 平均距離（Lehman-Stanley 2008/2011）。
        集団内で z-score 化（STD-1）して「集団から外れた個体ほど高 novelty」を
        相対量にし、``breakdown['novelty']`` へ書く。``__call__`` は 1 世代に
        個体数ぶん呼ばれるため、population の (generation, ids) 署名で 1 回だけ計算。

        ``factor_subspace_weight > 0`` かつ ``factor_extractor`` 指定時は factor 部分空間
        novelty（QD-3, :class:`FactorSubspaceNovelty`）も計算し、全体 novelty と **各々
        z-score 化してから** ``(1-w)·full + w·factor`` でブレンドして意味次元の多様性を
        個別保護する（PoC#6）。部分空間ごとに距離 scale が異なるため raw でなく標準化後に
        ブレンドする。
        """
        ids = tuple(ind.individual_id for ind in population.individuals)
        sig = (int(getattr(population, "generation", 0)), ids)
        if sig == self._pop_sig:
            return
        self._pop_sig = sig
        if self._scorer is None:
            self._scorer = NoveltyScorer(k=self.novelty_k)
        z = self._zscore(self._scorer.novelty_batch(population))  # 全体 novelty
        if self.factor_subspace_weight > 0.0 and self.factor_extractor is not None:
            if self._factor_novelty is None:
                self._factor_novelty = FactorSubspaceNovelty(
                    factor_extractor=self.factor_extractor, k=self.novelty_k
                )
            z_factor = self._zscore(self._factor_novelty.novelty_batch(population))
            w = self.factor_subspace_weight
            z = (1.0 - w) * z + w * z_factor  # 標準化後ブレンド (PoC#6 改良)
            self._factor_novelty.add_population(population)
        for ind, value in zip(population.individuals, z):
            if ind.fitness is None:
                continue
            ind.fitness.breakdown["novelty"] = float(value)
        # 採点後に今世代を archive へ追加（novelty は「過去との差」を測る）。
        self._scorer.add_population(population)

    def __call__(self, population: Population, rng: np.random.Generator) -> Individual:
        candidates = list(population.individuals)
        if not candidates:
            raise ValueError("population is empty")

        if self.use_novelty:
            # novelty を breakdown に書いてから criteria を抽出（case に含める）。
            self._ensure_novelty(population)

        # 適応 gate（例: pressures.AdaptivePercentileGate）は世代ごとに floor を
        # 集団分位から再計算する。duck typing で ``update`` を持つ gate だけ呼ぶため、
        # 固定 :class:`MinimalCriterionGate` は影響を受けない（後方互換）。
        if self.gate is not None and hasattr(self.gate, "update"):
            self.gate.update(population)

        criteria = self.criteria or _infer_numeric_criteria(
            candidates, self.exclude_criteria
        )
        if not criteria:
            # pressure が一つも無い → random fallback（全滅回避の最終手段）。
            return candidates[int(rng.integers(len(candidates)))]

        # minimal-criterion gate: 全員 fail なら無視（全滅を構造的に防ぐ, SEL-4）。
        if self.gate is not None:
            passed = [c for c in candidates if self.gate.passes(_numeric_breakdown(c))]
            if passed:
                candidates = passed

        # ε-lexicase（既存 LexicaseSelection を再利用, specialist 保存）。
        lexicase = LexicaseSelection(
            criteria=criteria,
            epsilon=self.epsilon,
            higher_is_better=self.higher_is_better,
        )
        return lexicase(Population(individuals=candidates), rng)
