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
    # ---- time conventions (倍率は v0 で無視、次元のみ。MATH-06 で scale 化) ----
    # 2026-05-17 grounding-observation で "5 days" 等が UNKNOWN だった対応。
    # 「これは時間単位だ」という次元認識だけ与え、scale conversion は後段。
    "second": Dimensions(s=1),
    "seconds": Dimensions(s=1),
    "min": Dimensions(s=1),
    "h": Dimensions(s=1),       # hour (conflict 注意: 質量定数 'h' は constants 側で別管理)
    "hour": Dimensions(s=1),
    "hours": Dimensions(s=1),
    "day": Dimensions(s=1),
    "days": Dimensions(s=1),
    "week": Dimensions(s=1),
    "weeks": Dimensions(s=1),
    "month": Dimensions(s=1),
    "months": Dimensions(s=1),
    "year": Dimensions(s=1),
    "years": Dimensions(s=1),
}


# SI 接頭辞 (倍率は v0 では無視、次元解釈のみに用いる)
# 2026-05-17 grounding-observation で "500 nm" が UNKNOWN だった対応。
# 接頭辞付きの単位記号 (nm, μs, kHz, MeV, ...) を base unit 次元に reduce する。
_SI_PREFIXES: frozenset[str] = frozenset({
    "Y", "Z", "E", "P", "T", "G", "M", "k", "h", "da",
    "d", "c", "m", "μ", "u", "n", "p", "f", "a", "z", "y",
})

# MATH-06 minimal scale layer: SI prefix → multiplier. Quantity 自体は
# 触らず unit_scale_factor() 経由でのみ公開。互換性破壊を避けるため。
_SI_PREFIX_SCALE: dict[str, float] = {
    "Y": 1e24, "Z": 1e21, "E": 1e18, "P": 1e15, "T": 1e12,
    "G": 1e9, "M": 1e6, "k": 1e3, "h": 1e2, "da": 1e1,
    "d": 1e-1, "c": 1e-2, "m": 1e-3, "μ": 1e-6, "u": 1e-6,
    "n": 1e-9, "p": 1e-12, "f": 1e-15, "a": 1e-18, "z": 1e-21, "y": 1e-24,
}

# 時間慣用単位 → seconds への変換係数。次元は既に _DERIVED で Dimensions(s=1)
# として扱っているので、scale だけここで持つ。
_TIME_SCALE: dict[str, float] = {
    "second": 1.0, "seconds": 1.0, "s": 1.0,
    "min": 60.0,
    "h": 3600.0, "hour": 3600.0, "hours": 3600.0,
    "day": 86400.0, "days": 86400.0,
    "week": 604800.0, "weeks": 604800.0,
    "month": 2629800.0, "months": 2629800.0,   # 平均月 = 30.4375 日
    "year": 31557600.0, "years": 31557600.0,   # 365.25 日 (Julian year)
}

# 質量慣用 (g→kg)。_DERIVED で 'g' は Dimensions(kg=1) として登録済 (次元のみ)、
# scale はここで持つ。
_MASS_SCALE: dict[str, float] = {
    "g": 1e-3,
    "kg": 1.0,
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


def unit_scale_factor(unit_text: str) -> float:
    """Return the SI-base conversion factor for a unit text (MATH-06 minimal).

    Example::

        unit_scale_factor("days") -> 86400.0
        unit_scale_factor("km")   -> 1000.0
        unit_scale_factor("m")    -> 1.0
        unit_scale_factor("kHz")  -> 1000.0

    Unknown or composite expressions raise :class:`UnitMismatchError`. This
    layer is **scalar-only** — composite units like ``m/s`` use scale 1.0
    (both prefixes are SI base by default); when prefixed compounds appear
    (``km/h``), the scale is the product of prefix scales on each term.
    """
    if unit_text is None or not unit_text.strip():
        return 1.0
    # Normalise like parse_unit does
    normalised = re.sub(r"\s+", "", unit_text).replace("·", "*")
    sign = 1
    scale = 1.0
    current = ""
    for ch in normalised + "*":
        if ch in ("*", "/"):
            if current:
                scale *= _term_scale(current) ** sign
                current = ""
            sign = 1 if ch == "*" else -1
        else:
            current += ch
    return scale


def _term_scale(term: str) -> float:
    """Scale factor for one term, mirroring _term_dimensions."""
    # Strip exponent: kg^2 → ('kg', 2)
    if "^" in term:
        sym, exp_s = term.split("^", 1)
        try:
            exp = int(exp_s)
        except ValueError as e:
            raise UnitMismatchError(f"bad exponent in unit term {term!r}") from e
    else:
        sym, exp = term, 1
    # 1. Direct hit in scale tables
    if sym in _TIME_SCALE:
        return _TIME_SCALE[sym] ** exp
    if sym in _MASS_SCALE:
        return _MASS_SCALE[sym] ** exp
    if sym in _DERIVED:
        return 1.0 ** exp  # SI base-equivalent or dimensionless
    # 2. Try SI prefix
    for plen in (2, 1):
        if len(sym) > plen and sym[:plen] in _SI_PREFIX_SCALE and sym[plen:] in _DERIVED:
            return _SI_PREFIX_SCALE[sym[:plen]] ** exp
    raise UnitMismatchError(f"unknown unit symbol {sym!r}")


def _term_dimensions(term: str, sign: int) -> Dimensions:
    """Parse a single term like ``m^2`` or ``kg`` and apply sign as exponent multiplier.

    Falls back to SI-prefix stripping (e.g. ``nm`` → ``n`` + ``m``) when the
    raw symbol is not directly registered, so ``nm`` / ``μs`` / ``kHz`` /
    ``MeV`` etc. resolve to their base-unit dimension. The scale factor
    associated with the prefix is intentionally **ignored** at this layer;
    we only care about the dimension vector here (scale handling is
    MATH-06's job).
    """
    if "^" in term:
        sym, exp_s = term.split("^", 1)
        try:
            exp = int(exp_s)
        except ValueError as e:
            raise UnitMismatchError(f"bad exponent in unit term {term!r}") from e
    else:
        sym, exp = term, 1
    if sym in _DERIVED:
        return _DERIVED[sym] ** (exp * sign)
    # Try stripping a SI prefix (longest-first so 'da' wins over 'd')
    for plen in (2, 1):
        if len(sym) > plen and sym[:plen] in _SI_PREFIXES and sym[plen:] in _DERIVED:
            return _DERIVED[sym[plen:]] ** (exp * sign)
    raise UnitMismatchError(f"unknown unit symbol {sym!r}")
