# SPDX-License-Identifier: Apache-2.0
"""Evolutionary optimization layer (llive v0.B).

ロボット歩行進化の AI 版. 集団 → 評価 → 選別 → 交配 → 突然変異 → 次世代 を
回して hyperparameter を進化させる. 既存 UCBSynapticSelector (収束型) と
直交し, 個体内 variant 選択は UCB, 個体間競争は GA に分担できる.

主要シンボル (Phase 1 公開):

* :class:`Genome` — 実数ベクトル + bounds
* :class:`Individual` — Genome + history + fitness
* :class:`Population` — Individual の集団 + 世代管理 + RNG seed
* :class:`FitnessReport` — 評価結果 (score + breakdown + runtime metadata)

Phase 2 で追加予定:

* :class:`Selection`, :class:`Crossover`, :class:`Mutation`
* :class:`EvolutionLoop`
"""

from llive.perf.evolutionary.genome import Genome, GenomeBounds
from llive.perf.evolutionary.individual import FitnessReport, Individual
from llive.perf.evolutionary.population import Population

__all__ = [
    "FitnessReport",
    "Genome",
    "GenomeBounds",
    "Individual",
    "Population",
]
