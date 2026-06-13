# SPDX-License-Identifier: Apache-2.0
"""適応推論予算 (IBPO / early-exit) 定量比較 PoC.

「易しい入力には浅い推論、難しい入力には深い推論」(Inference Budget-Constrained
Policy Optimization / early-exit) が、**固定深さ**に対し**同品質で平均計算量を下げる**
かを定量比較する。予測符号化「誤差がある所だけ計算する」の test-time 版であり、
llive `RecursionDepthGene` (L2 adaptive scaling) の理論裏付け検証。

モデル (アルゴリズム寄り simulation):

* 各タスクに難易度 ``d∈[0,1]``。正答に必要な深さ ``required = 1 + round(d·(max-1))``。
* **fixed**: 常に ``max_depth`` 実行 → 全問正答だが計算量は最大。
* **adaptive**: confidence 推定 (``required`` のノイズ付き推定) で early-exit。
  推定が正確なら ``required`` 付近で抜け平均計算量↓ (品質維持)。推定がノイズ大だと
  早抜けして品質が落ちる = IBPO のトレードオフを定量化。

    py -3.11 -m llive.perf.adaptive_budget_bench
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class BudgetModel:
    max_depth: int = 8
    n_tasks: int = 4000
    confidence_noise: float = 0.0   # 0 = 完全な confidence 推定器

    def required_depth(self, difficulty: np.ndarray) -> np.ndarray:
        return np.clip(
            np.round(1 + difficulty * (self.max_depth - 1)), 1, self.max_depth
        ).astype(int)


@dataclass(frozen=True)
class BudgetResult:
    mode: str
    avg_depth: float
    total_compute: int
    accuracy: float
    n_tasks: int


def simulate(model: BudgetModel, *, adaptive: bool, seed: int = 0) -> BudgetResult:
    rng = np.random.default_rng(seed)
    difficulty = rng.uniform(0.0, 1.0, size=model.n_tasks)
    required = model.required_depth(difficulty)

    if not adaptive:
        depths = np.full(model.n_tasks, model.max_depth, dtype=int)
    else:
        # confidence 推定器が required を推定して early-exit (ノイズ付き)
        jitter = rng.normal(0.0, model.confidence_noise * model.max_depth, size=model.n_tasks)
        est = np.clip(np.round(required + jitter), 1, model.max_depth).astype(int)
        depths = est

    correct = depths >= required
    return BudgetResult(
        mode="adaptive" if adaptive else "fixed",
        avg_depth=float(depths.mean()),
        total_compute=int(depths.sum()),
        accuracy=float(correct.mean()),
        n_tasks=model.n_tasks,
    )


@dataclass(frozen=True)
class CompareResult:
    noise: float
    fixed: BudgetResult
    adaptive: BudgetResult
    compute_saving: float       # 1 - adaptive/fixed
    accuracy_delta: float       # adaptive - fixed


def compare(model: BudgetModel, *, seed: int = 0) -> CompareResult:
    fixed = simulate(model, adaptive=False, seed=seed)
    adaptive = simulate(model, adaptive=True, seed=seed)
    return CompareResult(
        noise=model.confidence_noise,
        fixed=fixed,
        adaptive=adaptive,
        compute_saving=1.0 - adaptive.total_compute / fixed.total_compute,
        accuracy_delta=adaptive.accuracy - fixed.accuracy,
    )


# confidence 推定器の精度 (noise) を sweep
NOISE_LEVELS = (0.0, 0.05, 0.10, 0.20)


def sweep(*, max_depth: int = 8, n_tasks: int = 4000, seed: int = 0) -> list[CompareResult]:
    return [
        compare(BudgetModel(max_depth=max_depth, n_tasks=n_tasks, confidence_noise=nz), seed=seed)
        for nz in NOISE_LEVELS
    ]


def _ensure_utf8_stdout() -> None:
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass


def main() -> None:
    _ensure_utf8_stdout()
    print("# 適応推論予算 (IBPO/early-exit) — 定量比較 PoC\n")
    print("| confidence noise | compute 削減 | adaptive 精度 | fixed 精度 | accuracy 差 |")
    print("|---|---|---|---|---|")
    for r in sweep():
        print(
            f"| {r.noise:.2f} | {r.compute_saving:.0%} | {r.adaptive.accuracy:.1%} | "
            f"{r.fixed.accuracy:.1%} | {r.accuracy_delta:+.1%} |"
        )


if __name__ == "__main__":
    main()
