# SPDX-License-Identifier: Apache-2.0
"""組み合わせ PoC — 高速化候補のペア synergy を定量比較.

単体 PoC (antifragile_bench / predictive_gate_bench) を **合成**して、ブレストで
指摘された組み合わせ効果を測る:

* **Combo-A — Antifragile x Speculative Mesh**: panic mode の探索候補を idle mesh peer へ
  **並行投機**すると、同じ脱出世代でも 1 世代あたりの **wall-clock が ~並行度分の 1** に
  なる。antifragile が「脱出を可能にし」、mesh が「各 panic 世代を高速化する」二段効果。
* **Combo-C — Antifragile x 予測検証ゲート**: panic は変異を爆発させ **無効 ChangeOp の
  burst** を生む。前段ゲートはこの高 invalid burst で最大効果 → panic 中の verifier 負荷を
  安価に抑える。antifragile が gate の価値を**増幅**する。

    py -3.11 -m llive.evolution.combo_bench
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from llive.evolution.antifragile_bench import run_ga
from llive.evolution.predictive_gate_bench import GateModel, simulate

# ---------------------------------------------------------------------------
# Combo-A: Antifragile × Speculative Mesh (並行投機で panic 世代を高速化)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComboAResult:
    parallel_width: int
    escape_rate: float
    mean_gens_to_escape: float | None
    per_gen_serial_ms: float
    per_gen_mesh_ms: float
    walltime_speedup: float


def combo_a(
    *,
    parallel_width: int,
    seeds: int = 20,
    pop: int = 30,
    eval_ms: float = 10.0,
    mesh_overhead_ms: float = 1.0,
) -> ComboAResult:
    """antifragile の脱出に mesh 並行投機を重ねた wall-clock を測る."""
    results = [run_ga(use_antifragile=True, seed=s, pop=pop) for s in range(seeds)]
    escaped = [r for r in results if r.reached_global and r.gen_reached is not None]
    escape_rate = len(escaped) / seeds
    mean_gens = (
        float(np.mean([r.gen_reached for r in escaped])) if escaped else None
    )
    # 1 世代 = pop 個体評価。serial は逐次、mesh は W peer に分散 (per-eval overhead 付)。
    per_gen_serial = pop * eval_ms
    per_gen_mesh = math.ceil(pop / max(1, parallel_width)) * (eval_ms + mesh_overhead_ms)
    return ComboAResult(
        parallel_width=parallel_width,
        escape_rate=escape_rate,
        mean_gens_to_escape=mean_gens,
        per_gen_serial_ms=per_gen_serial,
        per_gen_mesh_ms=per_gen_mesh,
        walltime_speedup=per_gen_serial / per_gen_mesh,
    )


# ---------------------------------------------------------------------------
# Combo-C: Antifragile × 予測検証ゲート (panic burst を前段で filter)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComboCResult:
    mean_panic_gens: float
    n_gen: int
    panic_invalid_rate: float
    normal_invalid_rate: float
    combined_cost_saving: float       # antifragile run 全体での verifier コスト削減
    panic_only_saving: float          # panic 区間だけの削減 (参考)
    baseline_only_saving: float       # 通常区間だけの削減 (参考)


def combo_c(
    *,
    seeds: int = 20,
    ops_per_gen: int = 20,
    panic_invalid_rate: float = 0.9,
    normal_invalid_rate: float = 0.3,
) -> ComboCResult:
    """antifragile run の panic / normal 区間に予測ゲートを適用した総コスト削減."""
    results = [run_ga(use_antifragile=True, seed=s) for s in range(seeds)]
    mean_panic = float(np.mean([r.panic_gens for r in results]))
    n_gen = results[0].n_gen
    mean_normal = max(0.0, n_gen - mean_panic)

    panic_ops = max(1, int(round(mean_panic * ops_per_gen)))
    normal_ops = max(1, int(round(mean_normal * ops_per_gen)))

    g_panic = simulate(GateModel(invalid_rate=panic_invalid_rate, n_candidates=panic_ops), seed=0)
    g_normal = simulate(GateModel(invalid_rate=normal_invalid_rate, n_candidates=normal_ops), seed=0)

    total_baseline = g_panic.baseline_cost_ms + g_normal.baseline_cost_ms
    total_gated = g_panic.gated_cost_ms + g_normal.gated_cost_ms
    return ComboCResult(
        mean_panic_gens=mean_panic,
        n_gen=n_gen,
        panic_invalid_rate=panic_invalid_rate,
        normal_invalid_rate=normal_invalid_rate,
        combined_cost_saving=1.0 - total_gated / total_baseline,
        panic_only_saving=g_panic.cost_saving,
        baseline_only_saving=g_normal.cost_saving,
    )


def _ensure_utf8_stdout() -> None:
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass


def main() -> None:
    _ensure_utf8_stdout()
    print("# 組み合わせ PoC (llive 側)\n")
    print("## Combo-A: Antifragile × Speculative Mesh (並行投機で panic 高速化)\n")
    print("| 並行度 W | 脱出率 | 平均脱出世代 | wall-clock speedup |")
    print("|---|---|---|---|")
    for w in (1, 2, 4, 8):
        r = combo_a(parallel_width=w)
        g = f"{r.mean_gens_to_escape:.1f}" if r.mean_gens_to_escape else "n/a"
        print(f"| {w} | {r.escape_rate:.0%} | {g} | {r.walltime_speedup:.2f}x |")
    print("\n## Combo-C: Antifragile × 予測検証ゲート (panic burst を filter)\n")
    c = combo_c()
    print(f"- 平均 panic 世代: {c.mean_panic_gens:.1f} / {c.n_gen}")
    print(f"- panic 区間のみの削減: {c.panic_only_saving:.0%} (invalid {c.panic_invalid_rate:.0%})")
    print(f"- 通常区間のみの削減: {c.baseline_only_saving:.0%} (invalid {c.normal_invalid_rate:.0%})")
    print(f"- **run 全体の verifier コスト削減: {c.combined_cost_saving:.0%}**")


if __name__ == "__main__":
    main()
