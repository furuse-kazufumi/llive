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

from dataclasses import dataclass

import numpy as np

from llive.perf.evolutionary.individual import Individual
from llive.perf.evolutionary.mating import LexicaseSelection
from llive.perf.evolutionary.population import Population


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


def _infer_numeric_criteria(individuals: list[Individual]) -> tuple[str, ...]:
    """集団全体の breakdown から数値 criterion キーを出現順で抽出."""
    keys: list[str] = []
    seen: set[str] = set()
    for ind in individuals:
        for key in _numeric_breakdown(ind):
            if key not in seen:
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
        動的抽出（例 ``fitness_rich`` の ``archetype::*`` / ``factor_score`` / ...）。
    epsilon:
        ε-lexicase の許容範囲（同点扱い）。
    gate:
        :class:`MinimalCriterionGate`（None なら gate 無し）。全個体が落ちる場合は無視。
    higher_is_better:
        True なら各軸とも大きいほど良い。
    """

    criteria: tuple[str, ...] = ()
    epsilon: float = 0.01
    gate: MinimalCriterionGate | None = None
    higher_is_better: bool = True

    def __call__(self, population: Population, rng: np.random.Generator) -> Individual:
        candidates = list(population.individuals)
        if not candidates:
            raise ValueError("population is empty")

        criteria = self.criteria or _infer_numeric_criteria(candidates)
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
