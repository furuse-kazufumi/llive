# SPDX-License-Identifier: Apache-2.0
"""Genome — 実数ベクトル + per-dim bounds (llive v0.B EV-01).

JSON 化可能, immutable. mutation / crossover で生成された新 genome は
必ず bounds で clip されてから ``Genome`` instance になる.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(frozen=True)
class GenomeBounds:
    """各 dim の lower / upper bound. immutable.

    bounds.lower / bounds.upper は同じ shape (n_dims,). bounds は ``Genome`` の
    生成時に必ず適用される.
    """

    lower: tuple[float, ...]
    upper: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.lower) != len(self.upper):
            raise ValueError("lower/upper の長さが一致しない")
        for lo, up in zip(self.lower, self.upper, strict=True):
            if lo >= up:
                raise ValueError(f"lower ({lo}) >= upper ({up}) — invalid bound")

    @property
    def n_dims(self) -> int:
        return len(self.lower)

    def clip(self, values: np.ndarray) -> np.ndarray:
        """values を bounds 内に clip して返す (新 ndarray)."""
        arr = np.asarray(values, dtype=np.float64)
        if arr.shape != (self.n_dims,):
            raise ValueError(f"shape {arr.shape} != ({self.n_dims},)")
        return np.clip(arr, np.asarray(self.lower), np.asarray(self.upper))

    def sample_uniform(self, rng: np.random.Generator) -> np.ndarray:
        """bounds 内で uniform random sample."""
        return rng.uniform(
            low=np.asarray(self.lower),
            high=np.asarray(self.upper),
            size=self.n_dims,
        )

    def to_dict(self) -> dict[str, Any]:
        return {"lower": list(self.lower), "upper": list(self.upper)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GenomeBounds:
        return cls(lower=tuple(data["lower"]), upper=tuple(data["upper"]))


@dataclass(frozen=True)
class Genome:
    """実数ベクトル + bounds + 名前 ("labels") tuple.

    ``values`` は **常に bounds 内** に clip 済み (factory で保証).
    direct dataclass 構築は避け, :meth:`Genome.from_values` を使う.
    """

    values: tuple[float, ...]
    bounds: GenomeBounds
    labels: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if len(self.values) != self.bounds.n_dims:
            raise ValueError(
                f"values len {len(self.values)} != bounds n_dims {self.bounds.n_dims}"
            )
        if self.labels and len(self.labels) != self.bounds.n_dims:
            raise ValueError(
                f"labels len {len(self.labels)} != bounds n_dims {self.bounds.n_dims}"
            )

    # -- factories ---------------------------------------------------------

    @classmethod
    def from_values(
        cls,
        values: np.ndarray | list[float],
        bounds: GenomeBounds,
        labels: tuple[str, ...] = (),
    ) -> Genome:
        """values を bounds で clip してから Genome を作る."""
        clipped = bounds.clip(np.asarray(values, dtype=np.float64))
        return cls(values=tuple(float(v) for v in clipped), bounds=bounds, labels=labels)

    @classmethod
    def random(
        cls,
        bounds: GenomeBounds,
        rng: np.random.Generator,
        labels: tuple[str, ...] = (),
    ) -> Genome:
        return cls.from_values(bounds.sample_uniform(rng), bounds=bounds, labels=labels)

    # -- view --------------------------------------------------------------

    @property
    def n_dims(self) -> int:
        return self.bounds.n_dims

    def as_array(self) -> np.ndarray:
        """新 ndarray を返す (immutable 維持のため copy)."""
        return np.asarray(self.values, dtype=np.float64)

    def as_dict(self) -> dict[str, float]:
        """labels があれば labels をキーにした dict. なければ ``"dim_{i}"``."""
        if self.labels:
            return {label: v for label, v in zip(self.labels, self.values, strict=True)}
        return {f"dim_{i}": v for i, v in enumerate(self.values)}

    # -- serialize ---------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "values": list(self.values),
            "bounds": self.bounds.to_dict(),
            "labels": list(self.labels),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Genome:
        return cls.from_values(
            values=data["values"],
            bounds=GenomeBounds.from_dict(data["bounds"]),
            labels=tuple(data.get("labels", [])),
        )


__all__ = ["Genome", "GenomeBounds"]
