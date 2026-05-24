# SPDX-License-Identifier: Apache-2.0
"""推定器較正 (calibration) + 安定性 (stability) 評価 PoC.

速度 PoC は推定器精度 (hit_rate / IBPO confidence / gate recall) を**仮定値**で置く。
本 PoC は仮定の妥当性を 2 方向で評価:

1. **較正 (calibration)**: 推定器の confidence が観測頻度と一致するか (ECE / Brier)。
   over-confidence なら「主張精度 (claimed) > 実精度 (realized)」のギャップが出る →
   速度 PoC は speedup を過大評価する。
2. **安定性 (stability)**: 確率的 PoC (Antifragile の脱出) が seed に依存しないか。
   seed batch ごとの escape rate 分散を測り「seed 運でない」ことを確認する。

    py -3.11 -m llive.perf.calibration_bench
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from llive.evolution.antifragile_bench import run_ga

# ---------------------------------------------------------------------------
# 較正 (calibration)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CalibrationResult:
    bias: float
    ece: float                 # Expected Calibration Error (低いほど良)
    brier: float               # Brier score (低いほど良)
    claimed_accuracy: float    # システムが主張する精度 (predicted confidence 平均)
    realized_accuracy: float   # 実際の精度 (outcome 平均)
    gap: float                 # claimed - realized (正=over-confident=危険)


def evaluate_calibration(
    *, base_rate: float = 0.7, bias: float = 0.0, noise: float = 0.05,
    n: int = 4000, seed: int = 0,
) -> CalibrationResult:
    """confidence 推定器の較正を ECE/Brier で評価。bias>0 で over-confident。"""
    rng = np.random.default_rng(seed)
    outcomes = (rng.random(n) < base_rate).astype(float)
    conf = np.clip(base_rate + bias + rng.normal(0.0, noise, n), 0.0, 1.0)

    edges = np.linspace(0.0, 1.0, 11)
    ece = 0.0
    for i in range(10):
        lo, hi = edges[i], edges[i + 1]
        mask = (conf >= lo) & (conf < hi) if i < 9 else (conf >= lo) & (conf <= hi)
        cnt = int(mask.sum())
        if cnt == 0:
            continue
        ece += abs(float(conf[mask].mean()) - float(outcomes[mask].mean())) * cnt / n

    return CalibrationResult(
        bias=bias,
        ece=float(ece),
        brier=float(((conf - outcomes) ** 2).mean()),
        claimed_accuracy=float(conf.mean()),
        realized_accuracy=float(outcomes.mean()),
        gap=float(conf.mean() - outcomes.mean()),
    )


BIASES = (-0.1, 0.0, 0.1, 0.2)  # under / 較正済 / over-confident


def calibration_sweep(*, seed: int = 0) -> list[CalibrationResult]:
    return [evaluate_calibration(bias=b, seed=seed) for b in BIASES]


# ---------------------------------------------------------------------------
# 安定性 (stability)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StabilityResult:
    metric: str
    n_batches: int
    batch_size: int
    mean: float
    std: float
    min: float
    max: float


def stability_antifragile(*, n_batches: int = 8, batch_size: int = 15) -> StabilityResult:
    """Antifragile 脱出率を seed batch ごとに測り分散を見る (seed 運でないか)."""
    rates: list[float] = []
    for b in range(n_batches):
        escs = [
            run_ga(use_antifragile=True, seed=b * batch_size + i).reached_global
            for i in range(batch_size)
        ]
        rates.append(sum(escs) / batch_size)
    arr = np.asarray(rates, dtype=float)
    return StabilityResult(
        metric="antifragile_escape_rate",
        n_batches=n_batches,
        batch_size=batch_size,
        mean=float(arr.mean()),
        std=float(arr.std()),
        min=float(arr.min()),
        max=float(arr.max()),
    )


def _ensure_utf8_stdout() -> None:
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass


def main() -> None:
    _ensure_utf8_stdout()
    print("# 較正 (calibration) — 推定器 confidence の妥当性\n")
    print("| bias | ECE | Brier | claimed | realized | gap |")
    print("|---|---|---|---|---|---|")
    for r in calibration_sweep():
        print(
            f"| {r.bias:+.2f} | {r.ece:.3f} | {r.brier:.3f} | {r.claimed_accuracy:.3f} | "
            f"{r.realized_accuracy:.3f} | {r.gap:+.3f} |"
        )
    print("\n→ over-confidence (bias>0) は claimed > realized = 速度 PoC が speedup を過大評価。\n")
    print("# 安定性 (stability) — Antifragile 脱出率の seed 分散\n")
    s = stability_antifragile()
    print(f"- escape rate: mean={s.mean:.2f} std={s.std:.3f} min={s.min:.2f} max={s.max:.2f} "
          f"({s.n_batches}x{s.batch_size} seeds)")
    print("- std≈0 かつ min 高 = seed 運でなく頑健。" if s.std < 0.1 else "- std 大 = seed 依存に注意。")


if __name__ == "__main__":
    main()
