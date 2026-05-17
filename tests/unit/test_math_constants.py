# SPDX-License-Identifier: Apache-2.0
"""MATH-05 — Physical constants tests."""

from __future__ import annotations

import pytest

from llive.math import (
    ConstantNotFoundError,
    ConstantsRegistry,
    PhysicalConstant,
    Quantity,
    get_constant,
    list_constants,
    parse_unit,
)


def test_speed_of_light_exact() -> None:
    c = get_constant("c")
    assert c.symbol == "c"
    assert c.quantity.value == pytest.approx(2.99792458e8)
    assert c.relative_uncertainty == 0.0
    assert "exact" in c.source.lower()


def test_lookup_by_alias_case_insensitive() -> None:
    assert get_constant("Planck").symbol == "h"
    assert get_constant("BOLTZMANN").symbol == "k_B"
    assert get_constant("avogadro").symbol == "N_A"


def test_measured_constants_have_uncertainty() -> None:
    g = get_constant("newtonian_gravitation")
    assert g.relative_uncertainty > 0.0
    me = get_constant("m_e")
    assert me.relative_uncertainty > 0.0


def test_unknown_constant_raises() -> None:
    with pytest.raises(ConstantNotFoundError):
        get_constant("bogus_constant_42")


def test_list_constants_contains_exact_seven() -> None:
    names = {c.name for c in list_constants()}
    # 7 exact SI-defining constants
    for required in (
        "speed_of_light_in_vacuum",
        "planck_constant",
        "elementary_charge",
        "boltzmann_constant",
        "avogadro_constant",
        "cesium_hyperfine_frequency",
        "luminous_efficacy",
    ):
        assert required in names


def test_quantity_attached_to_constant() -> None:
    c = get_constant("c")
    assert isinstance(c.quantity, Quantity)
    # Speed of light's dimensions = m/s
    expected = parse_unit("m/s")
    assert c.quantity.dimensions == expected


def test_registry_extension() -> None:
    reg = ConstantsRegistry()
    custom = PhysicalConstant(
        name="standard_atmosphere",
        symbol="atm",
        quantity=Quantity(value=101325.0, dimensions=parse_unit("Pa")),
        source="NIST SP 330 (conventional)",
    )
    reg.register(custom)
    assert reg.get("atm").quantity.value == pytest.approx(101325.0)


def test_registry_rejects_duplicate() -> None:
    reg = ConstantsRegistry()
    with pytest.raises(ValueError):
        reg.register(PhysicalConstant(name="c2", symbol="c", quantity=Quantity(value=1.0, dimensions=parse_unit("m/s"))))


def test_payload_round_trip() -> None:
    c = get_constant("k_B").to_payload()
    assert c["symbol"] == "k_B"
    assert c["relative_uncertainty"] == 0.0
    assert "value" in c
