# SPDX-License-Identifier: Apache-2.0
"""Math & Units vertical (MATH-01 〜 MATH-08).

llive の最初の specialised vertical — 数学・単位次元解析・内蔵計算エンジン
で「数学に強い AI」を実現する。設計は ``.planning/REQUIREMENTS.md`` の
v0.7-vertical MATH セクションを参照。

Public surface (v0 minimal):

* :class:`Dimensions` — SI 7 基本単位の次元ベクトル
* :class:`Quantity` — 値 + 次元のペア
* :func:`parse_unit` — "m/s" 等の単位文字列を Dimensions に変換
* :class:`UnitMismatchError` — 次元不一致時に raised
"""

from __future__ import annotations

from llive.math.calculator import (
    CalculationError,
    CalculationResult,
    SafeCalculator,
    extract_expressions,
)
from llive.math.units import (
    Dimensions,
    Quantity,
    UnitMismatchError,
    parse_unit,
)
from llive.math.verifier import (
    MathVerifier,
    VerificationResult,
)

__all__ = [
    "CalculationError",
    "CalculationResult",
    "Dimensions",
    "MathVerifier",
    "Quantity",
    "SafeCalculator",
    "UnitMismatchError",
    "VerificationResult",
    "extract_expressions",
    "parse_unit",
]
