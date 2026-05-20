# SPDX-License-Identifier: Apache-2.0
"""Crossover — 親 2 体から子 genome を作る (llive v0.B EV-04).

2 種: Uniform (各 dim 独立に親から sample) / Blend (線形補間 + α 拡張).
すべて bounds で clip して返す.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from llive.perf.evolutionary.genome import Genome


@dataclass(frozen=True)
class UniformCrossover:
    """各 dim を独立に親 A / B からサンプリング (p の確率で A から)."""

    p: float = 0.5

    def __post_init__(self) -> None:
        if not (0.0 <= self.p <= 1.0):
            raise ValueError("p must be in [0, 1]")

    def __call__(
        self, parent_a: Genome, parent_b: Genome, rng: np.random.Generator
    ) -> Genome:
        if parent_a.bounds != parent_b.bounds:
            raise ValueError("parents have different bounds")
        a = parent_a.as_array()
        b = parent_b.as_array()
        mask = rng.random(size=a.shape) < self.p
        child = np.where(mask, a, b)
        return Genome.from_values(child, bounds=parent_a.bounds, labels=parent_a.labels)


@dataclass(frozen=True)
class BlendCrossover:
    """親値の線形補間 + α 拡張 (BLX-α). 連続パラメータ用 GA 標準."""

    alpha: float = 0.5

    def __post_init__(self) -> None:
        if self.alpha < 0:
            raise ValueError("alpha must be >= 0")

    def __call__(
        self, parent_a: Genome, parent_b: Genome, rng: np.random.Generator
    ) -> Genome:
        if parent_a.bounds != parent_b.bounds:
            raise ValueError("parents have different bounds")
        a = parent_a.as_array()
        b = parent_b.as_array()
        lo = np.minimum(a, b)
        hi = np.maximum(a, b)
        diff = hi - lo
        sample_lo = lo - self.alpha * diff
        sample_hi = hi + self.alpha * diff
        child = rng.uniform(low=sample_lo, high=sample_hi)
        return Genome.from_values(child, bounds=parent_a.bounds, labels=parent_a.labels)


@dataclass(frozen=True)
class SegmentCrossover:
    """染色体 (segment) 単位の交配. 生物的な gene segment swap 模倣.

    Genome を **複数 chromosome (= 連続 dim の segment)** に分け, 各 chromosome を
    親 A / B から独立に選ぶ. Uniform crossover の per-dim より **粗い粒度**で
    混ぜるため, 大きい構造的多様性を保ちやすい (ユーザー要望 2026-05-21).

    例: v0.C の 19 dim を [(0,10), (10,13), (13,14), (14,17), (17,19)] の
    5 segment に分ける → 子は 5 segment 単位で親を混合.

    Parameters
    ----------
    segments : Sequence[tuple[int, int]]
        ``(start, end)`` の半開区間 list. 全域カバー + 重複なしを要求.
    p : float
        各 segment を親 A から取る確率 (default 0.5).
    """

    segments: Sequence[tuple[int, int]]
    p: float = 0.5

    def __post_init__(self) -> None:
        if not self.segments:
            raise ValueError("segments must be non-empty")
        if not (0.0 <= self.p <= 1.0):
            raise ValueError("p must be in [0, 1]")
        # 重複 / 隙間 / 順序の検証
        prev_end = 0
        for start, end in self.segments:
            if start < prev_end:
                raise ValueError(f"segments overlap or out of order at {start}")
            if end <= start:
                raise ValueError(f"empty segment ({start}, {end})")
            prev_end = end

    def __call__(
        self, parent_a: Genome, parent_b: Genome, rng: np.random.Generator
    ) -> Genome:
        if parent_a.bounds != parent_b.bounds:
            raise ValueError("parents have different bounds")
        # genome 全域を segments がカバーする前提 (最後の end が n_dims と一致)
        n_dims = parent_a.bounds.n_dims
        last_end = self.segments[-1][1]
        if last_end > n_dims:
            raise ValueError(f"segments exceed genome dim ({last_end} > {n_dims})")
        a = parent_a.as_array()
        b = parent_b.as_array()
        child = b.copy()
        for start, end in self.segments:
            if rng.random() < self.p:
                child[start:end] = a[start:end]
        # 残った範囲 (segments がカバーしない区間) は親 B のまま (child 初期値)
        return Genome.from_values(child, bounds=parent_a.bounds, labels=parent_a.labels)


__all__ = ["BlendCrossover", "SegmentCrossover", "UniformCrossover"]
