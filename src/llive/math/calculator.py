# SPDX-License-Identifier: Apache-2.0
"""SafeCalculator — 内蔵計算エンジン (MATH-08, 差別化軸).

LLM に **数値計算をさせない** という設計を実装する。

設計の核:

* Brief 内に含まれる算術式 (例: ``(2.5 * 7.8) / 0.3``) を正規表現で抽出
* :class:`SafeCalculator` が AST を解析し、決定論的に評価
* 結果を ledger に固定記録 → LLM はそれを「事実」として参照するだけ

「LLM が計算する」 → 浮動小数点幻覚、桁落ち、簡単な誤り
「llive が計算する」 → IEEE 754 精度、再現可能、引用可能

`Safe` の意味:

* ``eval()`` は使わない (任意コード実行回避)
* AST visitor で許可ノード (BinOp / UnaryOp / Num / Constant) のみ通す
* 関数呼び出しは whitelist (math.sin, math.sqrt 等) のみ
* 0 除算は :class:`CalculationError` で安全に reject

このモジュールは sympy 等の重量依存なしで動く。`Quantity` (MATH-01) と
組み合わせて単位付き計算を投げ込めば、最終 :class:`CalculationResult` は
``value + dimensions + provenance`` の triple として ledger に乗る。
"""

from __future__ import annotations

import ast
import math
import operator
import re
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable


class CalculationError(ValueError):
    """式が解析不能、未許可演算、0 除算等で計算が安全に行えない場合に raised."""


@dataclass(frozen=True)
class CalculationResult:
    """1 件の式評価結果 — ledger 引用 / Brief grounded injection 用."""

    expression: str
    value: float
    operation_count: int  # AST 内の演算ノード数（複雑度メトリクス）
    used_functions: tuple[str, ...] = ()
    note: str = ""


# AST ノード → 演算子マッピング (whitelist 方式)
_BINOPS: dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARYOPS: dict[type, Callable[[Any], Any]] = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# 許可された関数の whitelist — math モジュールと統計のみ
_ALLOWED_FUNCTIONS: dict[str, Callable[..., float]] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "sqrt": math.sqrt,
    "exp": math.exp,
    "log": math.log,
    "log2": math.log2,
    "log10": math.log10,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "atan2": math.atan2,
    "sinh": math.sinh,
    "cosh": math.cosh,
    "tanh": math.tanh,
    "floor": math.floor,
    "ceil": math.ceil,
    "factorial": math.factorial,
    "gcd": math.gcd,
    "mean": statistics.mean,
    "median": statistics.median,
    "stdev": statistics.stdev,
    "variance": statistics.variance,
}

# 許可された定数
_ALLOWED_CONSTANTS: dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
    "inf": math.inf,
    "nan": math.nan,
}


class SafeCalculator:
    """AST visitor で式を評価する safe interpreter.

    使い方::

        calc = SafeCalculator()
        result = calc.evaluate("(2.5 * 7.8) / 0.3")
        print(result.value, result.operation_count)

    LLM 出力に対する典型的な利用例 — Brief の goal 文中に出現する算術式を
    抜き出して評価し、結果を grounded prompt として stim.content に注入:

        for expr in extract_expressions(brief.goal):
            r = calc.evaluate(expr)
            goal_with_proof += f"\n[計算結果] {expr} = {r.value}"
    """

    def evaluate(self, expression: str) -> CalculationResult:
        if not expression or not expression.strip():
            raise CalculationError("empty expression")
        try:
            tree = ast.parse(expression.strip(), mode="eval")
        except SyntaxError as e:
            raise CalculationError(f"syntax error in {expression!r}: {e}") from e

        functions_used: set[str] = set()
        op_count = self._count_operations(tree)
        value = self._eval(tree.body, functions_used)
        return CalculationResult(
            expression=expression.strip(),
            value=float(value),
            operation_count=op_count,
            used_functions=tuple(sorted(functions_used)),
        )

    # -- internals -----------------------------------------------------------

    def _eval(self, node: ast.AST, functions_used: set[str]) -> float:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return float(node.value)
            raise CalculationError(f"non-numeric constant {node.value!r}")
        if isinstance(node, ast.Name):
            if node.id in _ALLOWED_CONSTANTS:
                return _ALLOWED_CONSTANTS[node.id]
            raise CalculationError(f"unknown name {node.id!r}")
        if isinstance(node, ast.BinOp):
            op_cls = type(node.op)
            if op_cls not in _BINOPS:
                raise CalculationError(f"disallowed binary op {op_cls.__name__}")
            left = self._eval(node.left, functions_used)
            right = self._eval(node.right, functions_used)
            try:
                return _BINOPS[op_cls](left, right)
            except ZeroDivisionError as e:
                raise CalculationError(f"zero division in {ast.unparse(node)!r}") from e
            except (OverflowError, ValueError) as e:
                raise CalculationError(f"numeric error in {ast.unparse(node)!r}: {e}") from e
        if isinstance(node, ast.UnaryOp):
            op_cls = type(node.op)
            if op_cls not in _UNARYOPS:
                raise CalculationError(f"disallowed unary op {op_cls.__name__}")
            return _UNARYOPS[op_cls](self._eval(node.operand, functions_used))
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise CalculationError("only direct function names are allowed")
            fname = node.func.id
            if fname not in _ALLOWED_FUNCTIONS:
                raise CalculationError(f"function {fname!r} not in whitelist")
            functions_used.add(fname)
            args = [self._eval(arg, functions_used) for arg in node.args]
            try:
                return float(_ALLOWED_FUNCTIONS[fname](*args))
            except (ValueError, OverflowError, ZeroDivisionError) as e:
                raise CalculationError(f"{fname}({args}) failed: {e}") from e
        if isinstance(node, ast.Tuple):
            # statistics fns accept a sequence — tuple literal OK
            return tuple(self._eval(elt, functions_used) for elt in node.elts)  # type: ignore[return-value]
        if isinstance(node, ast.List):
            return [self._eval(elt, functions_used) for elt in node.elts]  # type: ignore[return-value]
        raise CalculationError(f"disallowed AST node {type(node).__name__}")

    @staticmethod
    def _count_operations(tree: ast.AST) -> int:
        count = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.BinOp, ast.UnaryOp, ast.Call)):
                count += 1
        return count


# ---------------------------------------------------------------------------
# Expression extraction from free-text Briefs
# ---------------------------------------------------------------------------

# Crude regex — pulls out parenthesised arithmetic expressions or simple
# `a OP b` patterns from natural language. Misses corner cases but is the
# minimum viable "find me the math in this Brief" tool.
_ARITH_RE = re.compile(
    r"""
    (?:                                    # an expression is...
        \(                                 # opens with (
        [\d\s+\-*/.,()^]+                  #   contains arithmetic chars
        \)                                 # closes with )
        (?:\s*[\^*/%]\s*\d+(?:\.\d+)?)?    # optional trailing exponent/mul
    )
    |                                       # ... OR ...
    (?:                                    # bare a OP b pattern
        \d+(?:\.\d+)?                      # number
        (?:\s*[+\-*/^]\s*\d+(?:\.\d+)?){1,} # at least one OP number
    )
    """,
    re.VERBOSE,
)


def extract_expressions(text: str) -> list[str]:
    """Pull arithmetic expressions out of free-text. Returns deduped order-preserved list."""
    seen: list[str] = []
    for m in _ARITH_RE.finditer(text or ""):
        expr = m.group(0).strip()
        # Drop obvious false positives (single digit, no operator)
        if not any(op in expr for op in "+-*/^"):
            continue
        if expr not in seen:
            seen.append(expr)
    return seen
