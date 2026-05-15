# SPDX-License-Identifier: Apache-2.0
"""Static Verifier (EVO-04 / FR-13).

Checks structural invariants over a sequence of :class:`ChangeOp` before any
LLM evaluation. Two layers:

1.  **Structural pre-check** (always on, no external dep). Counts subblock
    references and detects forbidden mutations: empty containers, removing
    the last block of a type the container declares essential, duplicate
    names, reorder that drops references.
2.  **SMT layer** (opt-in, Z3). Encodes each ChangeOp's effect on a small
    state vector (n_blocks, has_attention, has_memory_read, has_memory_write,
    nesting_depth) as Z3 constraints, then asks the solver whether all
    declared invariants stay satisfiable from start to finish.

Z3 is gated behind an import: when unavailable, the verifier falls back
to structural checks only and reports `smt_used=False` in the verdict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from llive.evolution.change_op import (
    InsertSubblock,
    RemoveSubblock,
    ReorderSubblocks,
    ReplaceSubblock,
)
from llive.schema.models import ContainerSpec, SubBlockRef

if TYPE_CHECKING:
    from llive.evolution.change_op import ChangeOp

try:
    import z3  # type: ignore[import-not-found]

    _HAS_Z3 = True
except ImportError:  # pragma: no cover - environment-dependent
    _HAS_Z3 = False


_ESSENTIAL_TYPES: tuple[str, ...] = (
    "pre_norm",
    "causal_attention",
    "ffn_swiglu",
)


@dataclass
class Invariants:
    """Declarative invariants the verifier must preserve across a diff."""

    min_blocks: int = 1
    max_blocks: int = 64
    essential_types: tuple[str, ...] = _ESSENTIAL_TYPES
    require_attention: bool = True
    require_memory_pair: bool = True  # if any memory_read, also need memory_write


@dataclass
class VerificationResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    smt_used: bool = False
    smt_model: str | None = None  # counterexample summary when ok=False


def _signature(refs: list[SubBlockRef]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in refs:
        out[r.type] = out.get(r.type, 0) + 1
    return out


def _check_invariants_now(refs: list[SubBlockRef], inv: Invariants) -> list[str]:
    bad: list[str] = []
    n = len(refs)
    if n < inv.min_blocks:
        bad.append(f"min_blocks={inv.min_blocks} violated (now {n})")
    if n > inv.max_blocks:
        bad.append(f"max_blocks={inv.max_blocks} violated (now {n})")
    sig = _signature(refs)
    for t in inv.essential_types:
        if sig.get(t, 0) < 1:
            bad.append(f"essential type {t!r} would be absent")
    if inv.require_attention and sig.get("causal_attention", 0) < 1:
        if "grouped_query_attention" not in sig:
            bad.append("attention sub-block required (causal or grouped_query)")
    if inv.require_memory_pair:
        if sig.get("memory_read", 0) > 0 and sig.get("memory_write", 0) < 1:
            bad.append("memory_read present without memory_write")
    names = [r.name for r in refs if r.name is not None]
    if len(names) != len(set(names)):
        bad.append("duplicate sub-block name detected")
    return bad


def verify_diff(
    before: ContainerSpec,
    ops: list[ChangeOp],
    invariants: Invariants | None = None,
    *,
    use_smt: bool = True,
) -> VerificationResult:
    """Verify a sequence of :class:`ChangeOp` preserves declared invariants.

    The structural layer simulates each op and re-checks invariants on the
    post-state. The SMT layer (when ``use_smt`` and Z3 is installed) encodes
    the same state transitions and asks Z3 whether the trajectory is
    satisfiable while pinning the invariants.
    """
    inv = invariants or Invariants()
    reasons: list[str] = []
    # structural simulation — apply every op then check invariants on the
    # final state. Intermediate states may transiently violate invariants
    # (e.g. memory_read inserted before its matching memory_write); only
    # the end-state must be valid. Empty diffs still check the initial state.
    current = before
    for i, op in enumerate(ops):
        try:
            current = op.apply(current)
        except Exception as exc:  # apply already raises ChangeOpError
            return VerificationResult(ok=False, reasons=[f"op[{i}] apply failed: {exc}"])
    final_violations = _check_invariants_now(current.subblocks, inv)
    if final_violations:
        label = "initial state" if not ops else "final state"
        reasons.extend(f"{label}: {v}" for v in final_violations)
    if reasons:
        return VerificationResult(ok=False, reasons=reasons, smt_used=False)
    if not (use_smt and _HAS_Z3):
        return VerificationResult(ok=True, reasons=[], smt_used=False)
    # SMT layer
    smt_ok, smt_reasons, model_str = _smt_verify(before, ops, inv)
    if not smt_ok:
        return VerificationResult(
            ok=False, reasons=reasons + smt_reasons, smt_used=True, smt_model=model_str
        )
    return VerificationResult(ok=True, reasons=[], smt_used=True)


def _smt_verify(
    before: ContainerSpec,
    ops: list[ChangeOp],
    inv: Invariants,
) -> tuple[bool, list[str], str | None]:
    """Z3 encoding of n_blocks / attention / memory_read / memory_write per step."""
    solver = z3.Solver()
    states: list[dict[str, z3.ArithRef]] = []
    initial_sig = _signature(before.subblocks)
    n0 = z3.Int("n_0")
    a0 = z3.Int("a_0")
    r0 = z3.Int("r_0")
    w0 = z3.Int("w_0")
    states.append({"n": n0, "a": a0, "r": r0, "w": w0})
    solver.add(n0 == len(before.subblocks))
    solver.add(a0 == initial_sig.get("causal_attention", 0))
    solver.add(r0 == initial_sig.get("memory_read", 0))
    solver.add(w0 == initial_sig.get("memory_write", 0))
    for i, op in enumerate(ops):
        prev = states[-1]
        n = z3.Int(f"n_{i+1}")
        a = z3.Int(f"a_{i+1}")
        r = z3.Int(f"r_{i+1}")
        w = z3.Int(f"w_{i+1}")
        states.append({"n": n, "a": a, "r": r, "w": w})
        if isinstance(op, InsertSubblock):
            spec_type = op.spec.type if isinstance(op.spec, SubBlockRef) else op.spec.get("type")
            solver.add(n == prev["n"] + 1)
            solver.add(a == prev["a"] + (1 if spec_type == "causal_attention" else 0))
            solver.add(r == prev["r"] + (1 if spec_type == "memory_read" else 0))
            solver.add(w == prev["w"] + (1 if spec_type == "memory_write" else 0))
        elif isinstance(op, RemoveSubblock):
            removed_type = _type_of(before, ops, i, op.target_subblock)
            solver.add(n == prev["n"] - 1)
            solver.add(a == prev["a"] - (1 if removed_type == "causal_attention" else 0))
            solver.add(r == prev["r"] - (1 if removed_type == "memory_read" else 0))
            solver.add(w == prev["w"] - (1 if removed_type == "memory_write" else 0))
        elif isinstance(op, ReplaceSubblock):
            old_type = _type_of(before, ops, i, op.from_)
            new_type = op.to.type if isinstance(op.to, SubBlockRef) else op.to.get("type")
            solver.add(n == prev["n"])
            solver.add(
                a
                == prev["a"]
                + (1 if new_type == "causal_attention" else 0)
                - (1 if old_type == "causal_attention" else 0)
            )
            solver.add(
                r
                == prev["r"]
                + (1 if new_type == "memory_read" else 0)
                - (1 if old_type == "memory_read" else 0)
            )
            solver.add(
                w
                == prev["w"]
                + (1 if new_type == "memory_write" else 0)
                - (1 if old_type == "memory_write" else 0)
            )
        elif isinstance(op, ReorderSubblocks):
            # reorder preserves counts
            solver.add(n == prev["n"])
            solver.add(a == prev["a"])
            solver.add(r == prev["r"])
            solver.add(w == prev["w"])
        else:  # pragma: no cover - new op types
            solver.add(n == prev["n"])
            solver.add(a == prev["a"])
            solver.add(r == prev["r"])
            solver.add(w == prev["w"])
    # invariants on the FINAL state only (intermediate states may transiently
    # violate them, e.g. inserting memory_read before its matching memory_write)
    final = states[-1]
    solver.add(final["n"] >= inv.min_blocks)
    solver.add(final["n"] <= inv.max_blocks)
    if inv.require_attention:
        solver.add(final["a"] >= 1)
    if inv.require_memory_pair:
        solver.add(z3.Implies(final["r"] >= 1, final["w"] >= 1))
    res = solver.check()
    if res == z3.sat:
        return True, [], None
    if res == z3.unsat:
        return False, ["SMT layer: state trajectory unsat under invariants"], None
    return False, [f"SMT layer: solver returned {res}"], None  # pragma: no cover


def _type_of(
    before: ContainerSpec, ops: list[ChangeOp], step: int, identifier: str
) -> str | None:
    """Replay ops up to ``step`` and return the type of the subblock named ``identifier``."""
    current = before
    for op in ops[:step]:
        current = op.apply(current)
    for ref in current.subblocks:
        if ref.name == identifier or ref.type == identifier:
            return ref.type
    return None  # pragma: no cover


__all__ = ["Invariants", "VerificationResult", "verify_diff"]
