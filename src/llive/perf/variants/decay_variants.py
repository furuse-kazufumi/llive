# SPDX-License-Identifier: Apache-2.0
"""Edge weight decay の複数 implementation variants.

llive memory tier の edge graph (associations / context links) は時間で
重みを減衰させる. 一括 decay は規模により最良 implementation が変動する:

- ``decay_python_loop``         — 純 Python for loop で multiply
- ``decay_python_listcomp``     — list comprehension (interpreter 最適化を期待)
- ``decay_python_map``          — ``map(lambda x: x*r, ...)`` (overhead 確認用)
- ``decay_numpy_inplace``       — numpy `arr *= rate` (代入式)
- ``decay_numpy_einsum``        — numpy einsum で scale (general API 確認用)

signature: ``(weights: Sequence[float] | np.ndarray, rate: float) -> list[float] | np.ndarray``

返却型は input 型を保つ (純 Python は list, numpy は ndarray).
SynapticSelector 経由で benchmark するときは return 型に依存しないようにする.

このモジュールは production hot path に **注入しない**. 自動収束観察のみ.
"""
from __future__ import annotations

from typing import Any, Callable, Sequence

import numpy as np

__all__ = [
    "decay_python_loop",
    "decay_python_listcomp",
    "decay_python_map",
    "decay_numpy_inplace",
    "decay_numpy_einsum",
    "PYTHON_VARIANTS",
    "NUMPY_VARIANTS",
    "ALL_VARIANTS",
]


# ---------------------------------------------------------------------------
# Python-side variants — input は list[float], output は list[float]
# ---------------------------------------------------------------------------


def decay_python_loop(weights: Sequence[float], rate: float) -> list[float]:
    out: list[float] = [0.0] * len(weights)
    for i, w in enumerate(weights):
        out[i] = w * rate
    return out


def decay_python_listcomp(weights: Sequence[float], rate: float) -> list[float]:
    return [w * rate for w in weights]


def decay_python_map(weights: Sequence[float], rate: float) -> list[float]:
    return list(map(lambda w: w * rate, weights))


# ---------------------------------------------------------------------------
# numpy-side variants — input は ndarray, output は ndarray
# ---------------------------------------------------------------------------


def decay_numpy_inplace(weights: np.ndarray, rate: float) -> np.ndarray:
    # コピーして in-place する (caller 側で copy したくない場合に備える)
    out = np.asarray(weights, dtype=np.float64).copy()
    out *= rate
    return out


def decay_numpy_einsum(weights: np.ndarray, rate: float) -> np.ndarray:
    a = np.asarray(weights, dtype=np.float64)
    # einsum で broadcast 乗算. dot より遅い可能性が高い (overhead 確認用).
    return np.einsum("i,->i", a, np.float64(rate))


PYTHON_VARIANTS: tuple[tuple[str, Callable[[Any, float], Any]], ...] = (
    ("py_loop", decay_python_loop),
    ("py_listcomp", decay_python_listcomp),
    ("py_map", decay_python_map),
)

NUMPY_VARIANTS: tuple[tuple[str, Callable[[Any, float], Any]], ...] = (
    ("np_inplace", decay_numpy_inplace),
    ("np_einsum", decay_numpy_einsum),
)

ALL_VARIANTS = PYTHON_VARIANTS + NUMPY_VARIANTS
