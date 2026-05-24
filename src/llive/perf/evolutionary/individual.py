# SPDX-License-Identifier: Apache-2.0
"""Individual + FitnessReport — Genome + 評価履歴 (llive v0.B EV-01/02)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from llive.perf.evolutionary.genome import Genome
from llive.perf.evolutionary.genome_3d import Genome3D

# A genome carried by an Individual is either the flat v0.B Genome or the
# multi-layer Genome3D. The infra is generic over this union; serialization
# tags which one so resume can reconstruct the right type (G1/G7).
GenomeT = Genome | Genome3D


def _genome_type_tag(genome: GenomeT) -> str:
    """Serialization tag used by Individual.to_dict/from_dict to branch on type."""
    return "Genome3D" if isinstance(genome, Genome3D) else "Genome"


@dataclass(frozen=True)
class FitnessReport:
    """1 個体 1 評価の結果 (EV-02).

    Fitness は **大きいほど良い** convention. 最小化問題は呼び出し側で
    符号反転する.
    """

    score: float
    breakdown: dict[str, float] = field(default_factory=dict)
    runtime_metadata: dict[str, str] = field(default_factory=dict)
    n_samples: int = 1
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": float(self.score),
            "breakdown": dict(self.breakdown),
            "runtime_metadata": dict(self.runtime_metadata),
            "n_samples": int(self.n_samples),
            "notes": str(self.notes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FitnessReport:
        return cls(
            score=float(data["score"]),
            breakdown=dict(data.get("breakdown", {})),
            runtime_metadata=dict(data.get("runtime_metadata", {})),
            n_samples=int(data.get("n_samples", 1)),
            notes=str(data.get("notes", "")),
        )


@dataclass
class Individual:
    """1 個体. Genome + 履歴 + 現世代の fitness.

    immutable ではない (fitness と history を世代ごとに更新するため). 直接の
    dataclass 操作は避け, ``record_fitness`` 経由で更新する.
    """

    genome: GenomeT
    individual_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    parent_ids: tuple[str, ...] = field(default_factory=tuple)
    birth_generation: int = 0
    fitness: FitnessReport | None = None
    history: list[FitnessReport] = field(default_factory=list)

    def record_fitness(self, report: FitnessReport) -> None:
        """現世代の fitness を更新 + 履歴 append."""
        self.fitness = report
        self.history.append(report)

    @property
    def score(self) -> float:
        """現 fitness の score. 未評価なら -inf を返す."""
        return float("-inf") if self.fitness is None else self.fitness.score

    # -- factory -----------------------------------------------------------

    @classmethod
    def from_genome(
        cls,
        genome: GenomeT,
        parent_ids: tuple[str, ...] = (),
        birth_generation: int = 0,
    ) -> Individual:
        return cls(genome=genome, parent_ids=parent_ids, birth_generation=birth_generation)

    # -- serialize ---------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "individual_id": self.individual_id,
            "parent_ids": list(self.parent_ids),
            "birth_generation": int(self.birth_generation),
            "genome_type": _genome_type_tag(self.genome),
            "genome": self.genome.to_dict(),
            "fitness": None if self.fitness is None else self.fitness.to_dict(),
            "history": [h.to_dict() for h in self.history],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Individual:
        # `genome_type` defaults to "Genome": snapshots written before the
        # Genome3D split (no tag) are flat, so this stays backward-compatible.
        genome_type = data.get("genome_type", "Genome")
        if genome_type == "Genome3D":
            genome: GenomeT = Genome3D.from_dict(data["genome"])
        else:
            genome = Genome.from_dict(data["genome"])
        ind = cls(
            genome=genome,
            individual_id=str(data["individual_id"]),
            parent_ids=tuple(data.get("parent_ids", [])),
            birth_generation=int(data.get("birth_generation", 0)),
        )
        if data.get("fitness") is not None:
            ind.fitness = FitnessReport.from_dict(data["fitness"])
        ind.history = [FitnessReport.from_dict(h) for h in data.get("history", [])]
        return ind


__all__ = ["FitnessReport", "GenomeT", "Individual"]
