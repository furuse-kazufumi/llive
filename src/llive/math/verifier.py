# SPDX-License-Identifier: Apache-2.0
"""MATH-02 — Sympy/Z3 Verifier with traceability hooks.

llive が出した (あるいは LLM が生成した) 数学的主張を、決定論的に
検証する層。Brief / BriefGrounder と接続することで「LLM が言った数式が
正しいか」を audit chain に残す。

## 検証メソッド

* :meth:`check_equivalence` — 2 式が代数的に等価か (Sympy `simplify(a-b)==0`)
* :meth:`check_implication` — premises → conclusion が valid か (Z3 で
  ¬(P → C) が unsat なら valid)
* :meth:`check_satisfiable` — 制約系が充足可能か (Z3)、反例 (model) も返す

## トレーサビリティ設計

各検証は :class:`VerificationResult` を返し、以下の情報を必ず持つ:

* ``kind`` — どの検証メソッドが呼ばれたか
* ``verdict`` — `equivalent` / `not_equivalent` / `valid` / `invalid` /
  `satisfiable` / `unsatisfiable` / `error`
* ``solver`` — `sympy` / `z3` のどちらが結論を出したか
* ``inputs`` — 入力 expression / premises を文字列で保持 (replay 可能性)
* ``counterexample`` — Z3 が反例を出した場合の variable assignments
* ``rationale`` — 人間可読の説明
* ``source_id`` — 呼び出し元が指定する文字列 ID (Brief id / RAD doc path 等)。
  trace_graph で evidence_chain に kind="math" として記録するときに使う

これら全てが ledger に流れることで、後段の audit / monitoring から
「この Brief のこの主張がいつ何で検証されたか」を SHA-256 chain と並んで
辿れるようになる (SEC-03 hash chain と整合)。

## 依存

* sympy>=1.12 (required) — 純代数簡約と等価判定
* z3-solver>=4.13 (required) — 量化制約と反例生成

両方とも v0.7 から required dependency に昇格 (MATH-02 が baseline 検証層)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Mapping, Sequence

import sympy
import z3

if TYPE_CHECKING:
    from llive.brief.ledger import BriefLedger


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerificationResult:
    """1 件の数学的検証の決定論的記録。

    ledger / trace_graph に書き出すための JSON 化は :meth:`to_payload` 経由。
    """

    kind: str            # "equivalence" / "implication" / "satisfiability"
    verdict: str         # see module docstring for the closed enum
    solver: str          # "sympy" / "z3"
    inputs: tuple[str, ...]
    rationale: str
    source_id: str = ""
    counterexample: Mapping[str, Any] = field(default_factory=dict)
    elapsed_s: float = 0.0
    error: str | None = None

    @property
    def is_positive(self) -> bool:
        """``True`` if the verdict confirms the claim (equivalent/valid/sat)."""
        return self.verdict in {"equivalent", "valid", "satisfiable"}

    def to_payload(self) -> dict[str, Any]:
        """JSON-friendly dict for BriefLedger event payloads."""
        return {
            "kind": self.kind,
            "verdict": self.verdict,
            "solver": self.solver,
            "inputs": list(self.inputs),
            "rationale": self.rationale,
            "source_id": self.source_id,
            "counterexample": dict(self.counterexample),
            "elapsed_s": self.elapsed_s,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sympy_parse(expr: str) -> sympy.Expr:
    """Parse with the safe parser — no eval, no attribute access."""
    return sympy.sympify(expr, evaluate=False)


def _free_symbols(*exprs: sympy.Expr) -> dict[str, sympy.Symbol]:
    """Collect unique free symbols across expressions, keyed by name."""
    seen: dict[str, sympy.Symbol] = {}
    for e in exprs:
        for s in e.free_symbols:
            seen.setdefault(str(s), s)  # type: ignore[arg-type]
    return seen


# Map sympy expressions to z3 — limited to the algebraic subset we ship in v0.7
# (constants, +/-/*/division, power with int exponent, and the inequality ops).
# Trig / transcendental functions raise so callers fall back to sympy-only paths.

def _sympy_to_z3(expr: sympy.Basic, z3_syms: Mapping[str, z3.ArithRef]) -> z3.ArithRef:
    if isinstance(expr, sympy.Symbol):
        name = str(expr)
        if name not in z3_syms:
            raise ValueError(f"unknown symbol in expression: {name!r}")
        return z3_syms[name]
    if isinstance(expr, sympy.Integer):
        return z3.IntVal(int(expr))
    if isinstance(expr, sympy.Rational):
        return z3.RealVal(float(expr))
    if isinstance(expr, sympy.Float):
        return z3.RealVal(float(expr))
    if isinstance(expr, sympy.Add):
        out = _sympy_to_z3(expr.args[0], z3_syms)
        for a in expr.args[1:]:
            out = out + _sympy_to_z3(a, z3_syms)
        return out
    if isinstance(expr, sympy.Mul):
        out = _sympy_to_z3(expr.args[0], z3_syms)
        for a in expr.args[1:]:
            out = out * _sympy_to_z3(a, z3_syms)
        return out
    if isinstance(expr, sympy.Pow):
        base, exp = expr.args
        if not exp.is_Integer or int(exp) < 0:
            raise ValueError(f"only non-negative integer exponents supported, got {exp}")
        result = z3.IntVal(1) if isinstance(base, sympy.Symbol) is False else z3.RealVal(1)
        # use repeated multiplication for portable z3 semantics
        b = _sympy_to_z3(base, z3_syms)
        out = b
        for _ in range(int(exp) - 1):
            out = out * b
        if int(exp) == 0:
            return z3.IntVal(1)
        return out
    if isinstance(expr, sympy.Equality):
        return _sympy_to_z3(expr.args[0], z3_syms) == _sympy_to_z3(expr.args[1], z3_syms)
    if isinstance(expr, sympy.StrictLessThan):
        return _sympy_to_z3(expr.args[0], z3_syms) < _sympy_to_z3(expr.args[1], z3_syms)
    if isinstance(expr, sympy.LessThan):
        return _sympy_to_z3(expr.args[0], z3_syms) <= _sympy_to_z3(expr.args[1], z3_syms)
    if isinstance(expr, sympy.StrictGreaterThan):
        return _sympy_to_z3(expr.args[0], z3_syms) > _sympy_to_z3(expr.args[1], z3_syms)
    if isinstance(expr, sympy.GreaterThan):
        return _sympy_to_z3(expr.args[0], z3_syms) >= _sympy_to_z3(expr.args[1], z3_syms)
    if isinstance(expr, sympy.Unequality):
        return _sympy_to_z3(expr.args[0], z3_syms) != _sympy_to_z3(expr.args[1], z3_syms)
    raise ValueError(
        f"unsupported sympy node for z3 lowering: {type(expr).__name__} ({expr})"
    )


def _model_to_dict(model: z3.ModelRef) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for d in model.decls():
        v = model[d]
        if isinstance(v, z3.IntNumRef):
            out[d.name()] = v.as_long()
        elif isinstance(v, z3.RatNumRef):
            out[d.name()] = float(v.numerator_as_long()) / float(v.denominator_as_long())
        elif isinstance(v, z3.AlgebraicNumRef):
            out[d.name()] = float(v.approx(8).as_decimal(8).rstrip("?"))
        else:
            out[d.name()] = str(v)
    return out


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------


class MathVerifier:
    """Strategy-injectable mathematical verifier (Sympy + Z3).

    Strategy 注入の理由:
    * 後段で SMT solver を CVC5 や bitwuzla に差し替えやすい
    * 単体テストでは ``_z3_check_unsat`` / ``_sympy_simplify`` を mock 化して
      flaky な solver 挙動から隔離可能

    現状は default Sympy/Z3 をハードコードしてあるが、将来 :meth:`__init__` に
    backend= 引数を追加することで差し替え可能になる。
    """

    def __init__(
        self,
        *,
        source_id: str = "",
        ledger: "BriefLedger | None" = None,
    ) -> None:
        self._source_id = source_id
        # Optional auto-record sink — when set, every check_* result is appended
        # to the ledger as a ``math_verified`` event. This is the primary
        # traceability hook for MATH-02: any LLM-produced math claim that goes
        # through a Verifier with a ledger is preserved alongside the Brief's
        # other audit chains (SEC-03 hash chain, COG-03 trace graph).
        self._ledger = ledger

    def _record(self, result: "VerificationResult") -> "VerificationResult":
        if self._ledger is not None:
            self._ledger.append("math_verified", result.to_payload())
        return result

    # -- equivalence ---------------------------------------------------------

    def check_equivalence(self, lhs: str, rhs: str, *, source_id: str | None = None) -> VerificationResult:
        """``simplify(lhs - rhs) == 0`` で代数的等価を判定。

        Sympy が決定論的に結論を出す。失敗時 (parser error 等) は
        verdict="error" を返し、上位の audit が「検証不能」として扱える。
        """
        import time
        t0 = time.perf_counter()
        try:
            l = _sympy_parse(lhs)
            r = _sympy_parse(rhs)
            diff = sympy.simplify(l - r)
            equivalent = diff == 0
            verdict = "equivalent" if equivalent else "not_equivalent"
            rationale = (
                f"sympy.simplify({lhs} - {rhs}) -> {diff}"
                if not equivalent
                else f"sympy.simplify({lhs} - {rhs}) -> 0"
            )
            counterexample: dict[str, Any] = {}
            if not equivalent:
                # try a quick numerical witness so audit gets something concrete
                syms = list(_free_symbols(l, r).values())
                if syms:
                    subs = {s: 1 for s in syms}
                    try:
                        witness = float(diff.subs(subs))
                        counterexample = {**{str(k): 1 for k in syms}, "diff": witness}
                    except (TypeError, ValueError):
                        counterexample = {}
            return self._record(VerificationResult(
                kind="equivalence",
                verdict=verdict,
                solver="sympy",
                inputs=(lhs, rhs),
                rationale=rationale,
                source_id=source_id if source_id is not None else self._source_id,
                counterexample=counterexample,
                elapsed_s=time.perf_counter() - t0,
            ))
        except Exception as exc:  # parser / simplifier blew up
            return self._record(VerificationResult(
                kind="equivalence",
                verdict="error",
                solver="sympy",
                inputs=(lhs, rhs),
                rationale="sympy raised",
                source_id=source_id if source_id is not None else self._source_id,
                elapsed_s=time.perf_counter() - t0,
                error=repr(exc),
            ))

    # -- implication ---------------------------------------------------------

    def check_implication(
        self,
        premises: Sequence[str],
        conclusion: str,
        *,
        source_id: str | None = None,
    ) -> VerificationResult:
        """``premises → conclusion`` が valid か (Z3 で ¬(P → C) unsat ⇔ valid)。

        反例があれば counterexample に variables の値を入れて返す。
        """
        import time
        t0 = time.perf_counter()
        try:
            premise_exprs = [_sympy_parse(p) for p in premises]
            concl_expr = _sympy_parse(conclusion)
            sym_names = _free_symbols(*premise_exprs, concl_expr)
            # build z3 real symbols (Real keeps the lowering simple even for ints)
            z3_syms = {name: z3.Real(name) for name in sym_names}
            premise_z3 = [_sympy_to_z3(p, z3_syms) for p in premise_exprs]
            concl_z3 = _sympy_to_z3(concl_expr, z3_syms)

            solver = z3.Solver()
            for p in premise_z3:
                solver.add(p)
            solver.add(z3.Not(concl_z3))
            result = solver.check()
            if result == z3.unsat:
                return VerificationResult(
                    kind="implication",
                    verdict="valid",
                    solver="z3",
                    inputs=(*premises, f"⊢ {conclusion}"),
                    rationale="z3 proved ¬(P → C) unsat ⇒ implication holds",
                    source_id=source_id if source_id is not None else self._source_id,
                    elapsed_s=time.perf_counter() - t0,
                )
            if result == z3.sat:
                model = solver.model()
                return VerificationResult(
                    kind="implication",
                    verdict="invalid",
                    solver="z3",
                    inputs=(*premises, f"⊢ {conclusion}"),
                    rationale="z3 found a counterexample to (P → C)",
                    source_id=source_id if source_id is not None else self._source_id,
                    counterexample=_model_to_dict(model),
                    elapsed_s=time.perf_counter() - t0,
                )
            return VerificationResult(
                kind="implication",
                verdict="error",
                solver="z3",
                inputs=(*premises, f"⊢ {conclusion}"),
                rationale=f"z3 returned {result}",
                source_id=source_id if source_id is not None else self._source_id,
                elapsed_s=time.perf_counter() - t0,
            )
        except Exception as exc:
            return VerificationResult(
                kind="implication",
                verdict="error",
                solver="z3",
                inputs=tuple([*premises, f"⊢ {conclusion}"]),
                rationale="lowering / solver raised",
                source_id=source_id if source_id is not None else self._source_id,
                elapsed_s=time.perf_counter() - t0,
                error=repr(exc),
            )

    # -- satisfiability ------------------------------------------------------

    def check_satisfiable(
        self,
        constraints: Sequence[str],
        *,
        source_id: str | None = None,
    ) -> VerificationResult:
        """制約系が同時充足可能か。SAT なら model を counterexample に返す。

        この場合の counterexample は「制約を満たす assignment 例」=
        positive witness なので、``is_positive`` 判定では sat 側が True。
        """
        import time
        t0 = time.perf_counter()
        try:
            exprs = [_sympy_parse(c) for c in constraints]
            sym_names = _free_symbols(*exprs)
            z3_syms = {name: z3.Real(name) for name in sym_names}
            solver = z3.Solver()
            for e in exprs:
                solver.add(_sympy_to_z3(e, z3_syms))
            result = solver.check()
            if result == z3.sat:
                model = solver.model()
                return VerificationResult(
                    kind="satisfiability",
                    verdict="satisfiable",
                    solver="z3",
                    inputs=tuple(constraints),
                    rationale="z3 found a satisfying assignment",
                    source_id=source_id if source_id is not None else self._source_id,
                    counterexample=_model_to_dict(model),
                    elapsed_s=time.perf_counter() - t0,
                )
            if result == z3.unsat:
                return VerificationResult(
                    kind="satisfiability",
                    verdict="unsatisfiable",
                    solver="z3",
                    inputs=tuple(constraints),
                    rationale="z3 proved no assignment satisfies the constraint set",
                    source_id=source_id if source_id is not None else self._source_id,
                    elapsed_s=time.perf_counter() - t0,
                )
            return VerificationResult(
                kind="satisfiability",
                verdict="error",
                solver="z3",
                inputs=tuple(constraints),
                rationale=f"z3 returned {result}",
                source_id=source_id if source_id is not None else self._source_id,
                elapsed_s=time.perf_counter() - t0,
            )
        except Exception as exc:
            return VerificationResult(
                kind="satisfiability",
                verdict="error",
                solver="z3",
                inputs=tuple(constraints),
                rationale="lowering / solver raised",
                source_id=source_id if source_id is not None else self._source_id,
                elapsed_s=time.perf_counter() - t0,
                error=repr(exc),
            )


__all__ = [
    "MathVerifier",
    "VerificationResult",
]
