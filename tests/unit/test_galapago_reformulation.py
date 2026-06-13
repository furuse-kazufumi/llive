# SPDX-License-Identifier: Apache-2.0
"""MATH-02 — general trig-normalization improvement for MathVerifier.

これは特定ドメイン由来の機能ではなく、**任意の三角恒等式に効く一般的な
正規化バグ**の修正に対する回帰テスト。``check_equivalence`` は
``simplify(lhs - rhs) == 0`` を主経路とするが、sympy の ``simplify`` は
``sin(n*theta)/sin(theta)`` のような式を Chebyshev 多項式 ``U_{n-1}(cos theta)``
へ自動で書き換えないため、両者を「非同値」と **誤判定 (false negative)** する。

本テストは:

1. **多項式同値パス** (companion 行列冪 = 漸化式 = 閉形式) が確実に通ること
   — 回帰の土台。主経路 (simplify) で結論が出るはずのケース。
2. **符号誤植版** が ``not_equivalent`` のままであること
   — verifier の健全性 (false positive を作らない) の回帰。
3. **三角形式** ``sin(n*theta)/sin(theta)`` ⇄ ``chebyshevu(n-1, cos theta)``
   を additive フォールバック (``expand_trig`` → ``rewrite(exp)``) で
   等価判定できること。
4. **倍角 / 和積 / 複素指数往復** 等、別系統の三角恒等式も等価判定できること
   — 一般改善であることの担保。
5. **非同値な三角式** が ``not_equivalent`` のままであること
   — フォールバック経由でも false positive を作らない担保。
"""

from __future__ import annotations

import sympy
from sympy import Integer, binomial, expand

from llive.math import MathVerifier

# ---------------------------------------------------------------------------
# Helpers — generate the three polynomial forms of the Lucas U_n sequence.
#
# Companion matrix M = [[0, -q], [1, p]] has characteristic polynomial
# t^2 - p t + q, so M^n[1, 0] == U_n where U_n = p U_{n-1} - q U_{n-2},
# U_0 = 0, U_1 = 1.  The closed form is the binomial sum below.  All three
# describe the same polynomial in (p, q) — the "companion 冪 = 漸化式 =
# 閉形式" identity used as the regression baseline (a fixed generator such as
# z = 1+i instantiates to p = z + z̄ = 2, q = z·z̄ = 2).
# ---------------------------------------------------------------------------


def _companion_U(n: int) -> sympy.Expr:
    """U_n as the [1, 0] entry of the companion-matrix n-th power."""
    M = sympy.Matrix([[0, -sympy.Symbol("q")], [1, sympy.Symbol("p")]])
    return expand((M**n)[1, 0])


def _recurrence_U(n: int) -> sympy.Expr:
    """U_n via the two-term recurrence U_n = p U_{n-1} - q U_{n-2}."""
    p, q = sympy.symbols("p q")
    u0, u1 = Integer(0), Integer(1)
    if n == 0:
        return u0
    if n == 1:
        return u1
    for _ in range(2, n + 1):
        u0, u1 = u1, expand(p * u1 - q * u0)
    return u1


def _closed_form_U(n: int, *, sign: bool = True) -> sympy.Expr:
    """U_n via the binomial closed form.

    With ``sign=True`` this is the correct ``(-1)^l`` Chebyshev-style sum.
    With ``sign=False`` the alternating ``(-1)^l`` factor is dropped (the
    ``(+l)^k`` sign typo) — a deliberately wrong formula used to confirm the
    verifier does not produce a false positive.
    """
    p, q = sympy.symbols("p q")
    total = Integer(0)
    upper = (n - 1) // 2
    for k in range(upper + 1):
        coeff = (-1) ** k if sign else 1
        total += coeff * binomial(n - 1 - k, k) * p ** (n - 1 - 2 * k) * q**k
    return expand(total)


# ---------------------------------------------------------------------------
# (1) Polynomial path: companion power == recurrence == closed form.
#     This goes through the *primary* simplify path — it must already pass and
#     is the regression baseline the fallback must not perturb.
# ---------------------------------------------------------------------------


def test_polynomial_companion_equals_recurrence() -> None:
    v = MathVerifier()
    for n in range(2, 8):
        comp = str(_companion_U(n))
        rec = str(_recurrence_U(n))
        r = v.check_equivalence(comp, rec)
        assert r.verdict == "equivalent", f"n={n}: {comp} vs {rec} -> {r.rationale}"
        assert r.solver == "sympy"


def test_polynomial_companion_equals_closed_form() -> None:
    v = MathVerifier()
    for n in range(2, 8):
        comp = str(_companion_U(n))
        closed = str(_closed_form_U(n))
        r = v.check_equivalence(comp, closed)
        assert r.verdict == "equivalent", f"n={n}: {comp} vs {closed} -> {r.rationale}"


# ---------------------------------------------------------------------------
# (2) Sign-typo guard: a wrong closed form must stay not_equivalent.
#     Confirms the verifier's soundness — no false positives on the poly path.
# ---------------------------------------------------------------------------


def test_polynomial_sign_typo_is_not_equivalent() -> None:
    v = MathVerifier()
    # n >= 3 is where the (-1)^l factor first changes a coefficient sign.
    for n in range(3, 8):
        rec = str(_recurrence_U(n))
        bad = str(_closed_form_U(n, sign=False))
        r = v.check_equivalence(rec, bad)
        assert r.verdict == "not_equivalent", f"n={n}: {rec} vs {bad} -> {r.rationale}"


# ---------------------------------------------------------------------------
# (3) Trig form: sin(n*theta)/sin(theta) == chebyshevu(n-1, cos theta).
#     The bug: sympy.simplify does not rewrite the trig quotient into the
#     Chebyshev polynomial, so the primary path returns not_equivalent.
#     The additive expand_trig -> rewrite(exp) fallback fixes it.
# ---------------------------------------------------------------------------


def test_trig_sin_ratio_equals_chebyshev_n5() -> None:
    v = MathVerifier()
    r = v.check_equivalence("sin(5*theta)/sin(theta)", "chebyshevu(4, cos(theta))")
    assert r.verdict == "equivalent", r.rationale


def test_trig_sin_ratio_equals_chebyshev_n7() -> None:
    v = MathVerifier()
    r = v.check_equivalence("sin(7*theta)/sin(theta)", "chebyshevu(6, cos(theta))")
    assert r.verdict == "equivalent", r.rationale


def test_trig_sin_ratio_equals_chebyshev_n11() -> None:
    v = MathVerifier()
    r = v.check_equivalence("sin(11*theta)/sin(theta)", "chebyshevu(10, cos(theta))")
    assert r.verdict == "equivalent", r.rationale


# ---------------------------------------------------------------------------
# (4) Other trig-identity families — general-improvement coverage.
# ---------------------------------------------------------------------------


def test_trig_double_angle_families_equivalent() -> None:
    v = MathVerifier()
    cases = [
        ("sin(2*x)", "2*sin(x)*cos(x)"),            # double angle
        ("cos(2*x)", "1 - 2*sin(x)**2"),            # double angle (cos)
        ("sin(a + b)", "sin(a)*cos(b) + cos(a)*sin(b)"),  # angle addition
        ("cos(a + b)", "cos(a)*cos(b) - sin(a)*sin(b)"),  # angle addition
        ("sin(3*x)", "3*sin(x) - 4*sin(x)**3"),     # triple angle
    ]
    for lhs, rhs in cases:
        r = v.check_equivalence(lhs, rhs)
        assert r.verdict == "equivalent", f"{lhs} vs {rhs} -> {r.rationale}"


def test_complex_exponential_roundtrip_equivalent() -> None:
    v = MathVerifier()
    # Euler: cos(x) == (exp(I x) + exp(-I x)) / 2.  rewrite(exp) closes this.
    r = v.check_equivalence("cos(x)", "(exp(I*x) + exp(-I*x))/2")
    assert r.verdict == "equivalent", r.rationale


# ---------------------------------------------------------------------------
# (5) False-positive guard on the trig path: genuinely non-equivalent trig
#     expressions must remain not_equivalent even after the fallback runs.
# ---------------------------------------------------------------------------


def test_trig_non_equivalent_stays_not_equivalent() -> None:
    v = MathVerifier()
    cases = [
        ("sin(2*x)", "2*sin(x)"),                       # missing cos factor
        ("cos(2*x)", "1 - sin(x)**2"),                  # wrong coefficient
        ("sin(3*theta)/sin(theta)", "chebyshevu(4, cos(theta))"),  # wrong degree
        ("sin(x)", "cos(x)"),                           # different functions
    ]
    for lhs, rhs in cases:
        r = v.check_equivalence(lhs, rhs)
        assert r.verdict == "not_equivalent", f"{lhs} vs {rhs} -> {r.rationale}"
