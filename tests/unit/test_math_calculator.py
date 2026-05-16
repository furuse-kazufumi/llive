# SPDX-License-Identifier: Apache-2.0
"""Tests for MATH-08 SafeCalculator (内蔵計算エンジン, 差別化軸)."""

from __future__ import annotations

import math

import pytest

from llive.math import (
    CalculationError,
    CalculationResult,
    SafeCalculator,
    extract_expressions,
)


# ---------------------------------------------------------------------------
# Arithmetic — basic correctness
# ---------------------------------------------------------------------------


@pytest.fixture
def calc() -> SafeCalculator:
    return SafeCalculator()


def test_calc_simple_addition(calc: SafeCalculator) -> None:
    r = calc.evaluate("2 + 3")
    assert isinstance(r, CalculationResult)
    assert r.value == pytest.approx(5.0)
    assert r.operation_count == 1


def test_calc_operator_precedence(calc: SafeCalculator) -> None:
    r = calc.evaluate("2 + 3 * 4")
    assert r.value == pytest.approx(14.0)


def test_calc_parentheses(calc: SafeCalculator) -> None:
    r = calc.evaluate("(2 + 3) * 4")
    assert r.value == pytest.approx(20.0)


def test_calc_float_precision(calc: SafeCalculator) -> None:
    # The headline case: LLM-typed "(2.5 * 7.8) / 0.3" is computed exactly
    # (within IEEE 754) — no token-by-token approximation.
    r = calc.evaluate("(2.5 * 7.8) / 0.3")
    assert r.value == pytest.approx(2.5 * 7.8 / 0.3)


def test_calc_unary_minus(calc: SafeCalculator) -> None:
    assert calc.evaluate("-5 + 3").value == pytest.approx(-2.0)
    assert calc.evaluate("-(2 + 3)").value == pytest.approx(-5.0)


def test_calc_power(calc: SafeCalculator) -> None:
    assert calc.evaluate("2 ** 10").value == pytest.approx(1024.0)


# ---------------------------------------------------------------------------
# Whitelisted functions and constants
# ---------------------------------------------------------------------------


def test_calc_sqrt(calc: SafeCalculator) -> None:
    r = calc.evaluate("sqrt(16)")
    assert r.value == pytest.approx(4.0)
    assert "sqrt" in r.used_functions


def test_calc_pi_constant(calc: SafeCalculator) -> None:
    r = calc.evaluate("pi * 2")
    assert r.value == pytest.approx(math.tau)


def test_calc_trig(calc: SafeCalculator) -> None:
    assert calc.evaluate("sin(0)").value == pytest.approx(0.0)
    assert calc.evaluate("cos(pi)").value == pytest.approx(-1.0)


def test_calc_log(calc: SafeCalculator) -> None:
    assert calc.evaluate("log10(100)").value == pytest.approx(2.0)
    assert calc.evaluate("log2(8)").value == pytest.approx(3.0)


def test_calc_nested_functions(calc: SafeCalculator) -> None:
    r = calc.evaluate("sqrt(abs(-25))")
    assert r.value == pytest.approx(5.0)
    assert set(r.used_functions) == {"sqrt", "abs"}


# ---------------------------------------------------------------------------
# Safety — refuses dangerous patterns
# ---------------------------------------------------------------------------


def test_calc_refuses_function_call_to_unknown(calc: SafeCalculator) -> None:
    # The attack chain bottoms out at .system being an attribute access,
    # so the visitor rejects it before the function call layer is reached.
    with pytest.raises(CalculationError):
        calc.evaluate("__import__('os').system('rm')")


def test_calc_refuses_non_whitelisted_function(calc: SafeCalculator) -> None:
    with pytest.raises(CalculationError, match="not in whitelist"):
        calc.evaluate("eval(1)")


def test_calc_refuses_attribute_access(calc: SafeCalculator) -> None:
    with pytest.raises(CalculationError):
        calc.evaluate("os.system")


def test_calc_refuses_string_literals(calc: SafeCalculator) -> None:
    with pytest.raises(CalculationError):
        calc.evaluate("'hello'")


def test_calc_refuses_division_by_zero(calc: SafeCalculator) -> None:
    with pytest.raises(CalculationError, match="zero division"):
        calc.evaluate("5 / 0")


def test_calc_refuses_unknown_name(calc: SafeCalculator) -> None:
    with pytest.raises(CalculationError, match="unknown name"):
        calc.evaluate("foo + 1")


def test_calc_refuses_empty_input(calc: SafeCalculator) -> None:
    with pytest.raises(CalculationError):
        calc.evaluate("")
    with pytest.raises(CalculationError):
        calc.evaluate("   ")


def test_calc_refuses_syntax_error(calc: SafeCalculator) -> None:
    with pytest.raises(CalculationError, match="syntax error"):
        calc.evaluate("2 +")


# ---------------------------------------------------------------------------
# Operation count metric (Brief 複雑度評価用)
# ---------------------------------------------------------------------------


def test_calc_operation_count_simple(calc: SafeCalculator) -> None:
    assert calc.evaluate("1 + 1").operation_count == 1
    assert calc.evaluate("(1 + 2) * 3").operation_count == 2
    assert calc.evaluate("sqrt(2 + 2)").operation_count == 2


# ---------------------------------------------------------------------------
# Expression extraction — pull arithmetic out of Brief text
# ---------------------------------------------------------------------------


def test_extract_simple_expression() -> None:
    text = "The total is (2.5 * 7.8) / 0.3 grams."
    exprs = extract_expressions(text)
    assert any("2.5 * 7.8" in e for e in exprs)


def test_extract_bare_arithmetic() -> None:
    text = "Set the value to 100 / 4."
    exprs = extract_expressions(text)
    assert any("100" in e and "4" in e for e in exprs)


def test_extract_dedupes() -> None:
    text = "Compute 3 + 4 and also 3 + 4 again."
    exprs = extract_expressions(text)
    assert exprs.count("3 + 4") <= 1


def test_extract_ignores_pure_numbers() -> None:
    text = "There are 42 widgets."
    exprs = extract_expressions(text)
    assert exprs == []


# ---------------------------------------------------------------------------
# End-to-end: extract → evaluate → grounded result
# ---------------------------------------------------------------------------


def test_e2e_pipeline_brief_to_calculation(calc: SafeCalculator) -> None:
    """The full MATH-08 path: pull math out of a Brief and ground its results."""
    brief_text = (
        "Compute (2.5 * 7.8) / 0.3 first, then verify sqrt(16) is exact."
    )
    grounded_lines: list[str] = []
    for expr in extract_expressions(brief_text):
        try:
            r = calc.evaluate(expr)
            grounded_lines.append(f"{r.expression} = {r.value}")
        except CalculationError:
            continue
    assert any("2.5 * 7.8" in line for line in grounded_lines)
