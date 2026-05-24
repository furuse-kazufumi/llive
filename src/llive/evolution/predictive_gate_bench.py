# SPDX-License-Identifier: Apache-2.0
"""予測検証メタゲート 定量比較 PoC (Gemini ブレスト #1).

[[project_idea_predictive_verification]]: 高コストな verifier (full Z3 dataflow 等) の
**前段に安価なメタゲート** (軽い充足可能性チェック / heuristic) を置き、明らかに無効な
ChangeOp を早期 reject して **重い verifier 呼び出しを減らす**。本 PoC はその
**コスト削減率**と**有効候補の誤却下リスク (品質コスト)** を定量比較する。

モデル (アルゴリズム寄り simulation):

* ``n_candidates`` 件の ChangeOp。``invalid_rate`` が無効 (panic burst では特に高い)。
* **baseline**: 全件を重い verifier (``verify_cost_ms``) に通す。
* **gated**: 全件を安価ゲート (``cheap_cost_ms``) に通し、ゲート通過分だけ重い verifier へ。
  - ゲートは無効を ``gate_recall`` の率で捕捉 (true reject) = コスト削減源。
  - ゲートは有効を ``gate_false_reject`` の率で誤って弾く = **品質コスト** (良い候補を喪失)。
  - ゲートをすり抜けた無効は重い verifier が確実に捕まえる (品質には無害、コストのみ浪費)。

    py -3.11 -m llive.evolution.predictive_gate_bench
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class GateModel:
    n_candidates: int = 4000
    invalid_rate: float = 0.6          # 無効候補の割合 (panic burst で上昇)
    gate_recall: float = 0.90          # 無効をゲートが捕捉する率
    gate_false_reject: float = 0.05    # 有効をゲートが誤却下する率 (品質コスト)
    cheap_cost_ms: float = 0.5         # 前段ゲート 1 件
    verify_cost_ms: float = 50.0       # 重い verifier 1 件


@dataclass(frozen=True)
class GateResult:
    invalid_rate: float
    baseline_cost_ms: float
    gated_cost_ms: float
    cost_saving: float                 # 1 - gated/baseline
    lost_valid_rate: float             # 有効候補のうち誤却下された率 (品質コスト)
    verify_calls_baseline: int
    verify_calls_gated: int


def simulate(model: GateModel, *, seed: int = 0) -> GateResult:
    rng = np.random.default_rng(seed)
    n = model.n_candidates
    is_invalid = rng.random(n) < model.invalid_rate
    roll = rng.random(n)
    # ゲート却下: 無効は recall で、有効は false_reject で弾かれる
    gate_reject = np.where(is_invalid, roll < model.gate_recall, roll < model.gate_false_reject)

    verify_calls_baseline = n
    verify_calls_gated = int((~gate_reject).sum())

    baseline_cost = n * model.verify_cost_ms
    gated_cost = n * model.cheap_cost_ms + verify_calls_gated * model.verify_cost_ms

    valid = ~is_invalid
    n_valid = int(valid.sum())
    lost_valid = int((valid & gate_reject).sum())
    return GateResult(
        invalid_rate=model.invalid_rate,
        baseline_cost_ms=baseline_cost,
        gated_cost_ms=gated_cost,
        cost_saving=1.0 - gated_cost / baseline_cost,
        lost_valid_rate=(lost_valid / n_valid) if n_valid else 0.0,
        verify_calls_baseline=verify_calls_baseline,
        verify_calls_gated=verify_calls_gated,
    )


# 無効率を sweep (通常運転 vs panic burst)
INVALID_RATES = (0.3, 0.6, 0.9)


def sweep(*, seed: int = 0, **kw) -> list[GateResult]:
    return [simulate(GateModel(invalid_rate=r, **kw), seed=seed) for r in INVALID_RATES]


def _ensure_utf8_stdout() -> None:
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass


def main() -> None:
    _ensure_utf8_stdout()
    print("# 予測検証メタゲート — 定量比較 PoC (cheap=0.5ms / verify=50ms)\n")
    print("| invalid率 | コスト削減 | verify呼出 削減 | 有効候補 誤却下率 |")
    print("|---|---|---|---|")
    for r in sweep():
        reduced = 1.0 - r.verify_calls_gated / r.verify_calls_baseline
        print(
            f"| {r.invalid_rate:.0%} | {r.cost_saving:.0%} | {reduced:.0%} | "
            f"{r.lost_valid_rate:.1%} |"
        )


if __name__ == "__main__":
    main()
