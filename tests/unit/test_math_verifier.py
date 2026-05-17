# SPDX-License-Identifier: Apache-2.0
"""MATH-02 — MathVerifier (Sympy + Z3) tests."""

from __future__ import annotations

import pytest

from llive.math import MathVerifier, VerificationResult


# ---------------------------------------------------------------------------
# VerificationResult contract
# ---------------------------------------------------------------------------


def test_result_to_payload_is_json_friendly() -> None:
    r = VerificationResult(
        kind="equivalence",
        verdict="equivalent",
        solver="sympy",
        inputs=("x + 0", "x"),
        rationale="ok",
        source_id="brief:foo",
    )
    payload = r.to_payload()
    assert payload["kind"] == "equivalence"
    assert payload["verdict"] == "equivalent"
    assert payload["solver"] == "sympy"
    assert payload["inputs"] == ["x + 0", "x"]
    assert payload["source_id"] == "brief:foo"


def test_is_positive_reflects_verdict() -> None:
    assert VerificationResult(kind="x", verdict="equivalent", solver="sympy", inputs=(), rationale="").is_positive
    assert VerificationResult(kind="x", verdict="valid", solver="z3", inputs=(), rationale="").is_positive
    assert VerificationResult(kind="x", verdict="satisfiable", solver="z3", inputs=(), rationale="").is_positive
    assert not VerificationResult(kind="x", verdict="not_equivalent", solver="sympy", inputs=(), rationale="").is_positive
    assert not VerificationResult(kind="x", verdict="invalid", solver="z3", inputs=(), rationale="").is_positive
    assert not VerificationResult(kind="x", verdict="unsatisfiable", solver="z3", inputs=(), rationale="").is_positive


# ---------------------------------------------------------------------------
# check_equivalence
# ---------------------------------------------------------------------------


def test_equivalence_simple_algebraic() -> None:
    v = MathVerifier()
    r = v.check_equivalence("(x + 1)**2", "x**2 + 2*x + 1")
    assert r.verdict == "equivalent"
    assert r.solver == "sympy"
    assert r.elapsed_s >= 0.0


def test_equivalence_detects_inequality_with_counterexample() -> None:
    v = MathVerifier()
    r = v.check_equivalence("(x + 1)**2", "x**2 + 1")
    assert r.verdict == "not_equivalent"
    # numerical witness with x=1: (1+1)^2=4 vs 1^2+1=2 → diff=2
    assert "diff" in r.counterexample
    assert r.counterexample["diff"] == pytest.approx(2.0)


def test_equivalence_handles_parse_error() -> None:
    v = MathVerifier()
    r = v.check_equivalence("x +", "y")
    assert r.verdict == "error"
    assert r.error is not None


def test_equivalence_carries_source_id() -> None:
    v = MathVerifier(source_id="brief:default")
    r = v.check_equivalence("x", "x")
    assert r.source_id == "brief:default"
    r2 = v.check_equivalence("x", "x", source_id="override")
    assert r2.source_id == "override"


# ---------------------------------------------------------------------------
# check_implication
# ---------------------------------------------------------------------------


def test_implication_valid_when_premise_forces_conclusion() -> None:
    v = MathVerifier()
    r = v.check_implication(["x > 5"], "x > 3")
    assert r.verdict == "valid"
    assert r.solver == "z3"


def test_implication_invalid_with_counterexample() -> None:
    v = MathVerifier()
    r = v.check_implication(["x > 0"], "x > 5")
    assert r.verdict == "invalid"
    # z3 should find e.g. x = 1 or similar witness
    assert "x" in r.counterexample
    assert r.counterexample["x"] <= 5


def test_implication_handles_unsupported_node() -> None:
    v = MathVerifier()
    # sin() is intentionally unsupported by the z3 lowering in v0.7
    r = v.check_implication(["sin(x) > 0"], "x > 0")
    assert r.verdict == "error"
    assert r.error is not None


# ---------------------------------------------------------------------------
# check_satisfiable
# ---------------------------------------------------------------------------


def test_satisfiable_returns_model() -> None:
    v = MathVerifier()
    r = v.check_satisfiable(["x > 0", "x < 10"])
    assert r.verdict == "satisfiable"
    assert "x" in r.counterexample
    assert 0 < r.counterexample["x"] < 10


def test_unsatisfiable_for_contradictory_constraints() -> None:
    v = MathVerifier()
    r = v.check_satisfiable(["x > 5", "x < 3"])
    assert r.verdict == "unsatisfiable"
    assert r.counterexample == {}


def test_satisfiable_error_on_unsupported_node() -> None:
    v = MathVerifier()
    r = v.check_satisfiable(["cos(x) > 0"])
    assert r.verdict == "error"
    assert r.error is not None
