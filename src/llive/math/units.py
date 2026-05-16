# SPDX-License-Identifier: Apache-2.0
"""SI 単位次元解析 — MATH-01 minimal skeleton.

7 基本単位 (m / kg / s / A / K / mol / cd) の次元ベクトルだけを扱う最小実装。
Pint 等の外部依存を避け、stdlib のみで動く。LLM の出力に含まれる単位混入
ミスを silent corrupt させないための「最後の砦」として使う。

設計判断:

* **frozen dataclass** — Dimensions / Quantity ともに immutable。同じ
  Brief を複数回 ground しても次元情報が破壊されない。
* **演算ごとに次元検算** — `+`/`-` は同次元同士のみ許可、不一致なら
  :class:`UnitMismatchError`。`*`/`/` は次元を加減算する。
* **dimensionless** — すべて 0 の Dimensions。スカラー演算用。
* **派生単位** — `N` (kg·m/s²), `J` (kg·m²/s²), `Pa` (kg/(m·s²)), `W`
  (kg·m²/s³), `Hz` (1/s) を頻出範囲のみ実装。完全カバーは MATH-06 で。

将来の拡張点:

* 倍率 (m → km, g → kg) — 別レイヤで scale を持つ
* CODATA 物理定数辞書 (MATH-05)
* Buckingham π 無次元化 (MATH-06)
* LaTeX/MathML 式解析 (MATH-03)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields
from typing import Iterator


class UnitMismatchError(ValueError):
    """加減算時に次元が一致しない / 不正な単位文字列を渡された場合に raised."""


# Order matters — SI 公式順序 (BIPM):
#   length, mass, time, electric current, temperature, amount, luminous intensity
_BASIC_ORDER: tuple[str, ...] = ("m", "kg", "s", "A", "K", "mol", "cd")


@dataclass(frozen=True)
class Dimensions:
    """SI 7 基本単位の次元ベクトル.

    例: ``m/s`` → ``Dimensions(m=1, s=-1)``、
       ``kg·m/s²`` → ``Dimensions(m=1, kg=1, s=-2)``、
       ``J = kg·m²/s²`` → ``Dimensions(m=2, kg=1, s=-2)``.
    """

    m: int = 0
    kg: int = 0
    s: int = 0
    A: int = 0
    K: int = 0
    mol: int = 0
    cd: int = 0

    # -- arithmetic ----------------------------------------------------------

    def __mul__(self, other: "Dimensions") -> "Dimensions":
        return Dimensions(**{f.name: getattr(self, f.name) + getattr(other, f.name) for f in fields(self)})

    def __truediv__(self, other: "Dimensions") -> "Dimensions":
        return Dimensions(**{f.name: getattr(self, f.name) - getattr(other, f.name) for f in fields(self)})

    def __pow__(self, n: int) -> "Dimensions":
        n = int(n)
        return Dimensions(**{f.name: getattr(self, f.name) * n for f in fields(self)})

    # -- predicates ----------------------------------------------------------

    @property
    def is_dimensionless(self) -> bool:
        return all(getattr(self, f.name) == 0 for f in fields(self))

    def matches(self, other: "Dimensions") -> bool:
        return all(getattr(self, f.name) == getattr(other, f.name) for f in fields(self))

    # -- introspection -------------------------------------------------------

    def as_pairs(self) -> Iterator[tuple[str, int]]:
        for name in _BASIC_ORDER:
            v = getattr(self, name)
            if v != 0:
                yield (name, v)

    def __str__(self) -> str:
        pairs = list(self.as_pairs())
        if not pairs:
            return "1"  # dimensionless
        return "·".join(f"{n}^{e}" if e != 1 else n for n, e in pairs)


@dataclass(frozen=True)
class Quantity:
    """値と次元を一緒に持つ最小型.

    演算は次元ベクトルを検算する。``5 m/s + 3 s`` のような不正計算は
    :class:`UnitMismatchError` で reject される。
    """

    value: float
    dimensions: Dimensions = field(default_factory=Dimensions)

    def __add__(self, other: "Quantity") -> "Quantity":
        if not self.dimensions.matches(other.dimensions):
            raise UnitMismatchError(
                f"cannot add {self.dimensions} and {other.dimensions}"
            )
        return Quantity(self.value + other.value, self.dimensions)

    def __sub__(self, other: "Quantity") -> "Quantity":
        if not self.dimensions.matches(other.dimensions):
            raise UnitMismatchError(
                f"cannot subtract {self.dimensions} from {other.dimensions}"
            )
        return Quantity(self.value - other.value, self.dimensions)

    def __mul__(self, other: "Quantity | float | int") -> "Quantity":
        if isinstance(other, Quantity):
            return Quantity(self.value * other.value, self.dimensions * other.dimensions)
        return Quantity(self.value * float(other), self.dimensions)

    def __truediv__(self, other: "Quantity | float | int") -> "Quantity":
        if isinstance(other, Quantity):
            return Quantity(self.value / other.value, self.dimensions / other.dimensions)
        return Quantity(self.value / float(other), self.dimensions)

    def __pow__(self, n: int) -> "Quantity":
        return Quantity(self.value ** int(n), self.dimensions ** int(n))

    def __str__(self) -> str:
        return f"{self.value} {self.dimensions}"


# ---------------------------------------------------------------------------
# Derived-unit lookup (頻出のみ; 拡張は MATH-06)
# ---------------------------------------------------------------------------

_DERIVED: dict[str, Dimensions] = {
    # base
    "m": Dimensions(m=1),
    "kg": Dimensions(kg=1),
    "g": Dimensions(kg=1),  # 注: 倍率は v0 では無視 (MATH-06 で正式対応)
    "s": Dimensions(s=1),
    "A": Dimensions(A=1),
    "K": Dimensions(K=1),
    "mol": Dimensions(mol=1),
    "cd": Dimensions(cd=1),
    # derived (頻出)
    "N": Dimensions(m=1, kg=1, s=-2),       # force
    "J": Dimensions(m=2, kg=1, s=-2),       # energy
    "W": Dimensions(m=2, kg=1, s=-3),       # power
    "Pa": Dimensions(kg=1, m=-1, s=-2),     # pressure
    "Hz": Dimensions(s=-1),                  # frequency
    "C": Dimensions(s=1, A=1),               # charge (Coulomb)
    "V": Dimensions(m=2, kg=1, s=-3, A=-1),  # voltage
    "ohm": Dimensions(m=2, kg=1, s=-3, A=-2),
    # ratio / dimensionless
    "1": Dimensions(),
    "rad": Dimensions(),
    "sr": Dimensions(),
}


# Tokeniser: split on `/` and `*` (and `·`), keep ^N exponents.
_TOKEN_RE = re.compile(r"\s*([*/·])\s*|\s+")


def parse_unit(text: str) -> Dimensions:
    """Parse a unit expression like ``"m/s"`` or ``"kg*m/s^2"`` into Dimensions.

    Supported:
        * `*` and `·` as multiplication, `/` as division
        * `^N` exponent on each token (e.g. ``m^2``)
        * derived unit symbols (N, J, W, Pa, Hz, C, V, ohm)

    Unknown symbols raise :class:`UnitMismatchError`.
    """
    if text is None or not text.strip():
        return Dimensions()  # dimensionless

    # normalize separators
    normalised = re.sub(r"\s+", "", text).replace("·", "*")
    # split into terms, tracking sign (numerator vs denominator)
    sign = 1
    accum = Dimensions()
    current = ""
    for ch in normalised + "*":  # sentinel terminator
        if ch in ("*", "/"):
            if current:
                accum = accum * _term_dimensions(current, sign)
                current = ""
            sign = 1 if ch == "*" else -1
        else:
            current += ch
    return accum


def _term_dimensions(term: str, sign: int) -> Dimensions:
    """Parse a single term like ``m^2`` or ``kg`` and apply sign as exponent multiplier."""
    if "^" in term:
        sym, exp_s = term.split("^", 1)
        try:
            exp = int(exp_s)
        except ValueError as e:
            raise UnitMismatchError(f"bad exponent in unit term {term!r}") from e
    else:
        sym, exp = term, 1
    if sym not in _DERIVED:
        raise UnitMismatchError(f"unknown unit symbol {sym!r}")
    return _DERIVED[sym] ** (exp * sign)
