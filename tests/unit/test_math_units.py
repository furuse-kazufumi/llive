# SPDX-License-Identifier: Apache-2.0
"""Tests for MATH-01 SI dimensional analysis (minimal skeleton)."""

from __future__ import annotations

import pytest

from llive.math import Dimensions, Quantity, UnitMismatchError, parse_unit


# ---------------------------------------------------------------------------
# Dimensions algebra
# ---------------------------------------------------------------------------


def test_dimensions_default_is_dimensionless() -> None:
    d = Dimensions()
    assert d.is_dimensionless
    assert str(d) == "1"


def test_dimensions_basic_components() -> None:
    d = Dimensions(m=1, s=-1)
    assert not d.is_dimensionless
    assert "m" in str(d)
    assert "s^-1" in str(d)


def test_dimensions_multiplication_adds_exponents() -> None:
    a = Dimensions(m=1, s=-1)  # m/s
    b = Dimensions(s=1)         # s
    assert (a * b).matches(Dimensions(m=1))


def test_dimensions_division_subtracts_exponents() -> None:
    a = Dimensions(m=2)
    b = Dimensions(m=1)
    assert (a / b).matches(Dimensions(m=1))


def test_dimensions_power() -> None:
    speed = Dimensions(m=1, s=-1)
    assert (speed ** 2).matches(Dimensions(m=2, s=-2))


def test_dimensions_matches_is_order_independent() -> None:
    a = Dimensions(m=1, kg=1, s=-2)  # Newton
    b = Dimensions(s=-2, kg=1, m=1)
    assert a.matches(b)


# ---------------------------------------------------------------------------
# Quantity arithmetic — the cornerstone of MATH-01: refuses unit mismatches.
# ---------------------------------------------------------------------------


def test_quantity_addition_same_dim_ok() -> None:
    q = Quantity(5.0, Dimensions(m=1, s=-1))
    r = Quantity(3.0, Dimensions(m=1, s=-1))
    out = q + r
    assert out.value == pytest.approx(8.0)
    assert out.dimensions.matches(Dimensions(m=1, s=-1))


def test_quantity_addition_dim_mismatch_raises() -> None:
    """LLM の典型的な幻覚 `5 m/s + 3 s` を必ず止める."""
    q = Quantity(5.0, Dimensions(m=1, s=-1))   # m/s
    r = Quantity(3.0, Dimensions(s=1))          # s
    with pytest.raises(UnitMismatchError):
        _ = q + r


def test_quantity_subtraction_dim_mismatch_raises() -> None:
    q = Quantity(10.0, Dimensions(m=1))
    r = Quantity(2.0, Dimensions(kg=1))
    with pytest.raises(UnitMismatchError):
        _ = q - r


def test_quantity_multiplication_combines_dimensions() -> None:
    v = Quantity(5.0, Dimensions(m=1, s=-1))   # m/s
    t = Quantity(2.0, Dimensions(s=1))          # s
    d = v * t
    assert d.value == pytest.approx(10.0)
    assert d.dimensions.matches(Dimensions(m=1))


def test_quantity_division_combines_dimensions() -> None:
    d = Quantity(100.0, Dimensions(m=1))
    t = Quantity(4.0, Dimensions(s=1))
    v = d / t
    assert v.value == pytest.approx(25.0)
    assert v.dimensions.matches(Dimensions(m=1, s=-1))


def test_quantity_scalar_multiply() -> None:
    q = Quantity(5.0, Dimensions(kg=1))
    r = q * 2
    assert r.value == pytest.approx(10.0)
    assert r.dimensions.matches(Dimensions(kg=1))


# ---------------------------------------------------------------------------
# parse_unit — string → Dimensions
# ---------------------------------------------------------------------------


def test_parse_simple_base_unit() -> None:
    assert parse_unit("m").matches(Dimensions(m=1))
    assert parse_unit("s").matches(Dimensions(s=1))
    assert parse_unit("kg").matches(Dimensions(kg=1))


def test_parse_division_creates_negative_exponent() -> None:
    assert parse_unit("m/s").matches(Dimensions(m=1, s=-1))


def test_parse_multiplication_combines() -> None:
    assert parse_unit("kg*m").matches(Dimensions(kg=1, m=1))
    assert parse_unit("kg·m").matches(Dimensions(kg=1, m=1))


def test_parse_exponent() -> None:
    assert parse_unit("m^2").matches(Dimensions(m=2))
    assert parse_unit("m^2/s^2").matches(Dimensions(m=2, s=-2))


def test_parse_derived_units() -> None:
    # Newton = kg·m/s²
    assert parse_unit("N").matches(Dimensions(m=1, kg=1, s=-2))
    # Joule = kg·m²/s²
    assert parse_unit("J").matches(Dimensions(m=2, kg=1, s=-2))
    # Watt = kg·m²/s³
    assert parse_unit("W").matches(Dimensions(m=2, kg=1, s=-3))
    # Pascal = kg/(m·s²)
    assert parse_unit("Pa").matches(Dimensions(kg=1, m=-1, s=-2))
    # Hertz = 1/s
    assert parse_unit("Hz").matches(Dimensions(s=-1))


def test_parse_empty_yields_dimensionless() -> None:
    assert parse_unit("").is_dimensionless
    assert parse_unit("   ").is_dimensionless


def test_parse_unknown_unit_raises() -> None:
    with pytest.raises(UnitMismatchError):
        parse_unit("furlong")


def test_parse_bad_exponent_raises() -> None:
    with pytest.raises(UnitMismatchError):
        parse_unit("m^X")


# ---------------------------------------------------------------------------
# End-to-end: refuse "5 m/s + 3 s" style hallucination
# ---------------------------------------------------------------------------


def test_e2e_refuses_unit_mismatch_via_parse() -> None:
    v = Quantity(5.0, parse_unit("m/s"))
    t = Quantity(3.0, parse_unit("s"))
    with pytest.raises(UnitMismatchError):
        _ = v + t
    # but v * t = displacement is fine
    d = v * t
    assert d.dimensions.matches(parse_unit("m"))


def test_e2e_force_times_distance_is_energy() -> None:
    """F·d should have units of energy (Joules)."""
    F = Quantity(10.0, parse_unit("N"))
    d = Quantity(5.0, parse_unit("m"))
    E = F * d
    assert E.value == pytest.approx(50.0)
    assert E.dimensions.matches(parse_unit("J"))


# ---------------------------------------------------------------------------
# SI prefix stripping (2026-05-17 grounding-observation 課題 1)
# ---------------------------------------------------------------------------


def test_parse_nm_is_meter_dimension() -> None:
    """500 nm — nanometre, dimension = length."""
    assert parse_unit("nm").matches(Dimensions(m=1))


def test_parse_us_micro_is_seconds() -> None:
    """μs / us — microseconds, dimension = time."""
    assert parse_unit("μs").matches(Dimensions(s=1))
    assert parse_unit("us").matches(Dimensions(s=1))


def test_parse_kHz_is_frequency() -> None:
    """kHz — kilohertz, dimension = 1/s."""
    assert parse_unit("kHz").matches(Dimensions(s=-1))


def test_parse_MeV_is_energy() -> None:
    """MeV — million electron volts, but as a unit symbol resolves only the
    SI base — V (volt). Note: 'eV' is not in our table yet; this test
    intentionally documents how the prefix layer handles a prefix+volt
    combination that does exist."""
    assert parse_unit("MV").matches(parse_unit("V"))


def test_parse_compound_with_prefix() -> None:
    """'kg' is base (do NOT misread as kilo-g) — verified by composition test."""
    # kg by itself = base mass dimension
    assert parse_unit("kg").matches(Dimensions(kg=1))
    # kHz / (km) — derived combo with prefixes
    assert parse_unit("kHz").matches(Dimensions(s=-1))
    assert parse_unit("km").matches(Dimensions(m=1))


# ---------------------------------------------------------------------------
# Time conventions (2026-05-17 grounding-observation 課題 2)
# ---------------------------------------------------------------------------


def test_parse_days_is_time_dimension() -> None:
    """'5 days' should resolve to a time dimension, not UNKNOWN."""
    assert parse_unit("days").matches(Dimensions(s=1))
    assert parse_unit("day").matches(Dimensions(s=1))


def test_parse_weeks_hours_min_year() -> None:
    for word in ("week", "weeks", "hour", "hours", "min", "year", "years"):
        assert parse_unit(word).matches(Dimensions(s=1)), word
