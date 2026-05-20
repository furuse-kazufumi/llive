# SPDX-License-Identifier: Apache-2.0
"""Cosine similarity の複数 implementation variants.

llive の memory tier (`memory/surprise.py`, `cognitive_mesh/embedding_similarity.py`)
が cosine 類似度を多用する. 既存実装は numpy ベース. 本 module はそれを
触らず, **新規 wrapper** として 4 variants を提供する:

- ``cosine_pure_python`` — math + zip + sum. 小次元 / no-numpy 環境向け.
- ``cosine_numpy_dot`` — `np.dot` + `np.linalg.norm`. 既存 production と同等.
- ``cosine_numpy_einsum`` — `np.einsum("i,i->", v1, v2)`. 場合により dot より速い.
- ``cosine_numpy_normalized`` — 事前 L2 normalize 済 input 前提の高速版.

すべて入力検証無しの **inner-loop 専用**. caller 側で None / shape /
dtype を保証する.

各 variant の signature は統一: ``(v1: ArrayLike, v2: ArrayLike) -> float``.
SynapticSelector に直接 load 可能.

import 軽量化のため numpy import は module load 時 1 回.
"""
from __future__ import annotations

import math
from typing import Any, Callable

import numpy as np

__all__ = [
    "cosine_pure_python",
    "cosine_numpy_dot",
    "cosine_numpy_einsum",
    "cosine_numpy_normalized",
    "ALL_VARIANTS",
]


def cosine_pure_python(v1: Any, v2: Any) -> float:
    """純 Python 実装. ArrayLike を tuple として扱う.

    小次元 (~16) では numpy 化のオーバーヘッドを下回ることがある.
    """
    s = 0.0
    n1 = 0.0
    n2 = 0.0
    for a, b in zip(v1, v2):
        s += a * b
        n1 += a * a
        n2 += b * b
    if n1 == 0.0 or n2 == 0.0:
        return 0.0
    return s / (math.sqrt(n1) * math.sqrt(n2))


def cosine_numpy_dot(v1: Any, v2: Any) -> float:
    """`np.dot` + `np.linalg.norm` の標準実装.

    既存 production (`embedding_similarity.py`) と同じ式.
    """
    a = np.asarray(v1, dtype=np.float64)
    b = np.asarray(v2, dtype=np.float64)
    n1 = float(np.linalg.norm(a))
    n2 = float(np.linalg.norm(b))
    if n1 == 0.0 or n2 == 0.0:
        return 0.0
    return float(np.dot(a, b) / (n1 * n2))


def cosine_numpy_einsum(v1: Any, v2: Any) -> float:
    """`np.einsum("i,i->", v1, v2)` を内積に使った亜種.

    実装系の最適化により dot より速いことがあるが, 一般には拮抗.
    """
    a = np.asarray(v1, dtype=np.float64)
    b = np.asarray(v2, dtype=np.float64)
    n1 = float(np.sqrt(np.einsum("i,i->", a, a)))
    n2 = float(np.sqrt(np.einsum("i,i->", b, b)))
    if n1 == 0.0 or n2 == 0.0:
        return 0.0
    return float(np.einsum("i,i->", a, b) / (n1 * n2))


def cosine_numpy_normalized(v1: Any, v2: Any) -> float:
    """事前 L2 normalize 済 input 前提.

    ``v1, v2`` がすでに単位ベクトルなら norm 計算を省ける. caller 側で
    L2 normalize を 1 度だけ済ませる cache 設計と組合せる.
    本実装は **norm 計算をしない** — `dot(v1, v2)` だけ. 誤入力時は
    数学的に不正な値を返す (safe 用途には他 variant を選ぶ).
    """
    a = np.asarray(v1, dtype=np.float64)
    b = np.asarray(v2, dtype=np.float64)
    return float(np.dot(a, b))


# 公開 variant 列. SynapticSelector に load する時の標準セット.
ALL_VARIANTS: tuple[tuple[str, Callable[[Any, Any], float]], ...] = (
    ("pure_python", cosine_pure_python),
    ("numpy_dot", cosine_numpy_dot),
    ("numpy_einsum", cosine_numpy_einsum),
    ("numpy_normalized", cosine_numpy_normalized),
)
