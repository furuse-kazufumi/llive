# SPDX-License-Identifier: Apache-2.0
"""MATH-05 — Physical constants from CODATA 2022 / NIST.

llive の数学 vertical で「LLM が定数を間違える」事故を防ぐ defensive 層。
LLM が話に出した定数値は、本辞書経由で問い合わせて :class:`Quantity` として
取り出す前提。値はすべて CODATA 2022 ( https://physics.nist.gov/cuu/Constants/ )
または NIST SP 330 (SI 単位の定義) から。

Public surface:

* :class:`PhysicalConstant` — 値 + Quantity + uncertainty + source citation
* :func:`get_constant(name)` — name または alias で lookup、見つからなければ raises
* :func:`list_constants()` — 全件を tuple で返す
* :class:`ConstantsRegistry` — extend したい場合 (例: NIST 標準気圧、AVOGADRO 等)

設計:

* CODATA 2022 で **exact** 定義された 7 定数 (c, h, e, k_B, N_A, ΔνCs, Kcd) は
  uncertainty=0.0
* 派生定数 (G, m_e, m_p 等) は CODATA 公表値 + 相対標準不確かさを併記
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from llive.math.units import Dimensions, Quantity, parse_unit


@dataclass(frozen=True)
class PhysicalConstant:
    """1 つの物理定数 — :class:`Quantity` + メタ情報。"""

    name: str
    symbol: str
    quantity: Quantity
    relative_uncertainty: float = 0.0  # 0.0 = exact / definitional
    source: str = "CODATA 2022"
    aliases: tuple[str, ...] = ()
    description: str = ""

    def to_payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "symbol": self.symbol,
            "value": self.quantity.value,
            "unit": self.quantity.dimensions.symbol,
            "relative_uncertainty": self.relative_uncertainty,
            "source": self.source,
            "aliases": list(self.aliases),
            "description": self.description,
        }


def _q(value: float, unit_str: str) -> Quantity:
    return Quantity(value=value, dimensions=parse_unit(unit_str))


# ---------------------------------------------------------------------------
# CODATA 2022 — exact (definitional) SI constants
# ---------------------------------------------------------------------------

_CODATA_EXACT: tuple[PhysicalConstant, ...] = (
    PhysicalConstant(
        name="speed_of_light_in_vacuum", symbol="c",
        quantity=_q(2.99792458e8, "m/s"),
        relative_uncertainty=0.0,
        source="CODATA 2022 (exact SI definition)",
        aliases=("c", "speed_of_light", "lightspeed"),
        description="真空中の光速 (SI 基本定数、exact)",
    ),
    PhysicalConstant(
        name="planck_constant", symbol="h",
        quantity=_q(6.62607015e-34, "kg*m^2/s"),
        relative_uncertainty=0.0,
        source="CODATA 2022 (exact SI definition)",
        aliases=("h", "planck"),
        description="プランク定数 (SI 基本定数、exact)",
    ),
    PhysicalConstant(
        name="elementary_charge", symbol="e",
        quantity=_q(1.602176634e-19, "C"),
        relative_uncertainty=0.0,
        source="CODATA 2022 (exact SI definition)",
        aliases=("e", "elementary_charge", "q_e"),
        description="素電荷 (SI 基本定数、exact)",
    ),
    PhysicalConstant(
        name="boltzmann_constant", symbol="k_B",
        quantity=_q(1.380649e-23, "kg*m^2/s^2/K"),
        relative_uncertainty=0.0,
        source="CODATA 2022 (exact SI definition)",
        aliases=("kB", "k_b", "boltzmann"),
        description="ボルツマン定数 (SI 基本定数、exact)",
    ),
    PhysicalConstant(
        name="avogadro_constant", symbol="N_A",
        quantity=Quantity(value=6.02214076e23, dimensions=Dimensions()),
        relative_uncertainty=0.0,
        source="CODATA 2022 (exact SI definition)",
        aliases=("NA", "N_a", "avogadro"),
        description="アボガドロ定数 (SI 基本定数、exact、無次元 / mol 数として)",
    ),
    PhysicalConstant(
        name="cesium_hyperfine_frequency", symbol="ΔνCs",
        quantity=_q(9.192631770e9, "Hz"),
        relative_uncertainty=0.0,
        source="CODATA 2022 (exact SI definition of the second)",
        aliases=("delta_nu_cs", "cesium_frequency"),
        description="セシウム原子超微細遷移周波数 (秒の SI 定義)",
    ),
    PhysicalConstant(
        name="luminous_efficacy", symbol="Kcd",
        quantity=_q(683.0, "1"),  # cd*sr*kg^-1*m^-2*s^3 ≈ dimensionless ratio for our purposes
        relative_uncertainty=0.0,
        source="CODATA 2022 (exact SI definition of the candela)",
        aliases=("kcd", "luminous_efficacy_540_thz"),
        description="540 THz 単色放射の発光効率 (カンデラの SI 定義)",
    ),
)


# ---------------------------------------------------------------------------
# CODATA 2022 — measured (non-exact) constants
# ---------------------------------------------------------------------------

_CODATA_MEASURED: tuple[PhysicalConstant, ...] = (
    PhysicalConstant(
        name="newtonian_gravitation", symbol="G",
        quantity=_q(6.67430e-11, "m^3/kg/s^2"),
        relative_uncertainty=2.2e-5,
        source="CODATA 2022",
        aliases=("gravitation", "big_g"),
        description="万有引力定数 (CODATA 2022 推奨値). 注: 'G' は symbol 経由で lookup 可、'g' (小文字) は standard_gravity を指す",
    ),
    PhysicalConstant(
        name="electron_mass", symbol="m_e",
        quantity=_q(9.1093837139e-31, "kg"),
        relative_uncertainty=3.1e-10,
        source="CODATA 2022",
        aliases=("me", "m_e", "electron_rest_mass"),
        description="電子の静止質量",
    ),
    PhysicalConstant(
        name="proton_mass", symbol="m_p",
        quantity=_q(1.67262192595e-27, "kg"),
        relative_uncertainty=3.1e-10,
        source="CODATA 2022",
        aliases=("mp", "m_p"),
        description="陽子の静止質量",
    ),
    PhysicalConstant(
        name="vacuum_electric_permittivity", symbol="ε_0",
        quantity=_q(8.8541878188e-12, "1"),  # F/m — kept as 1 to avoid F derivation noise
        relative_uncertainty=1.6e-10,
        source="CODATA 2022",
        aliases=("epsilon_0", "vacuum_permittivity", "e0"),
        description="真空の誘電率 (関連: μ_0 c^2 ε_0 = 1)",
    ),
    PhysicalConstant(
        name="vacuum_magnetic_permeability", symbol="μ_0",
        quantity=_q(1.25663706127e-6, "1"),  # H/m
        relative_uncertainty=1.6e-10,
        source="CODATA 2022",
        aliases=("mu_0", "vacuum_permeability", "m0"),
        description="真空の透磁率",
    ),
    PhysicalConstant(
        name="standard_acceleration_of_gravity", symbol="g_n",
        quantity=_q(9.80665, "m/s^2"),
        relative_uncertainty=0.0,
        source="NIST SP 330 (conventional value)",
        aliases=("g", "gn", "standard_gravity"),
        description="標準重力加速度 (慣用値、地理的に exact)",
    ),
)


_ALL: tuple[PhysicalConstant, ...] = _CODATA_EXACT + _CODATA_MEASURED


# ---------------------------------------------------------------------------
# Lookup API
# ---------------------------------------------------------------------------


class ConstantNotFoundError(KeyError):
    """Raised by :func:`get_constant` when a name / alias is unknown."""


def _index() -> dict[str, PhysicalConstant]:
    out: dict[str, PhysicalConstant] = {}
    for c in _ALL:
        out[c.name.lower()] = c
        out[c.symbol.lower()] = c
        for a in c.aliases:
            out[a.lower()] = c
    return out


_INDEX: dict[str, PhysicalConstant] = _index()


def get_constant(name: str) -> PhysicalConstant:
    """Lookup by canonical name / symbol / alias (case-insensitive)."""
    key = name.lower()
    if key not in _INDEX:
        raise ConstantNotFoundError(f"unknown physical constant: {name!r}")
    return _INDEX[key]


def list_constants() -> tuple[PhysicalConstant, ...]:
    """All known constants, in definition order (exact first)."""
    return _ALL


class ConstantsRegistry:
    """In-memory mutable registry — extend defaults without reloading the module."""

    def __init__(self, base: Iterable[PhysicalConstant] | None = None) -> None:
        self._items: dict[str, PhysicalConstant] = {}
        for c in (base if base is not None else _ALL):
            self._add(c)

    def _add(self, c: PhysicalConstant) -> None:
        for key in (c.name.lower(), c.symbol.lower(), *(a.lower() for a in c.aliases)):
            if key in self._items and self._items[key] is not c:
                raise ValueError(f"duplicate constant key {key!r}")
            self._items[key] = c

    def register(self, c: PhysicalConstant) -> None:
        self._add(c)

    def get(self, name: str) -> PhysicalConstant:
        key = name.lower()
        if key not in self._items:
            raise ConstantNotFoundError(f"unknown physical constant: {name!r}")
        return self._items[key]


__all__ = [
    "ConstantNotFoundError",
    "ConstantsRegistry",
    "PhysicalConstant",
    "get_constant",
    "list_constants",
]
