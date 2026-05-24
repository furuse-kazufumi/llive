# SPDX-License-Identifier: Apache-2.0
"""Antifragile Mutation 定量比較 PoC — 局所最適からの脱出を測る.

[[project_idea_antifragile_mutation]] の honest disclosure は「自己破壊で次の安定へ、が
本当に効くかは未検証」だった。本 PoC はそれを **定量比較** する: 騙し (deceptive)
multimodal landscape 上で、**panic mode あり (antifragile) / なし (baseline)** の GA を
回し、**局所最適からの脱出率**・到達 best fitness・コスト (panic 世代数) を比較する。

設計 (FullSense 規約: 要件→PoC→フィジビリティ):

* 実 :class:`~llive.evolution.antifragile.AntifragileController` を駆動 (panic 判定・
  探索増幅は本物)。GA 本体は numpy の最小実装 (進化 driver の保留バグ
  [[project_llive_evolution_next_session]] を回避し controller の効果だけを測る)。
* landscape: 広く浅い**局所最適** (x≈-2, 高さ 0.85) と、狭く高い**大域最適** (x≈3,
  高さ 1.0) を 5 単位離して配置。小 sigma の baseline は谷を越えられず局所最適に捕まる。
* surprise = 「改善が止まったか」(停滞→高 surprise→panic→sigma 一時増幅)。
  clock は世代カウンタを注入 (cooldown を「世代」単位にする)。

    py -3.11 -m llive.evolution.antifragile_bench
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from llive.evolution.antifragile import AntifragileConfig, AntifragileController

# landscape 定数
_LOCAL_X = -2.0     # 局所最適の中心 (広く浅い)
_LOCAL_H = 0.85
_LOCAL_W = 1.2      # 広い basin
_GLOBAL_X = 3.0     # 大域最適の中心 (狭く高い)
_GLOBAL_H = 1.0
_GLOBAL_W = 0.30    # 狭い basin
_BOUND = 5.0
_GLOBAL_FIT_THRESHOLD = 0.95  # これ以上で「大域最適に到達」とみなす


def deceptive_fitness(x: np.ndarray) -> np.ndarray:
    """2 山の騙し landscape. 局所最適 (広・低) と大域最適 (狭・高)."""
    local = _LOCAL_H * np.exp(-((x - _LOCAL_X) ** 2) / (2 * _LOCAL_W**2))
    glob = _GLOBAL_H * np.exp(-((x - _GLOBAL_X) ** 2) / (2 * _GLOBAL_W**2))
    return np.maximum(local, glob)


@dataclass(frozen=True)
class GaResult:
    use_antifragile: bool
    seed: int
    best_fitness: float
    best_x: float
    reached_global: bool
    gen_reached: int | None
    panic_gens: int
    n_gen: int


def run_ga(
    *,
    use_antifragile: bool,
    seed: int,
    n_gen: int = 60,
    pop: int = 30,
    base_sigma: float = 0.30,
    exploration_multiplier: float = 8.0,
    cooldown_gens: float = 5.0,
) -> GaResult:
    """局所 basin 起点の最小 GA を回す. antifragile なら停滞時に sigma を増幅."""
    rng = np.random.default_rng(seed)
    # 全個体を局所最適 basin の近傍に初期化 (baseline が捕まる設定)
    x = np.clip(rng.normal(_LOCAL_X, 0.3, size=pop), -_BOUND, _BOUND)
    fit = deceptive_fitness(x)
    best_i = int(np.argmax(fit))
    best_f = float(fit[best_i])
    best_x = float(x[best_i])

    gen_state = {"gen": 0}
    ctrl: AntifragileController | None = None
    if use_antifragile:
        ctrl = AntifragileController(
            AntifragileConfig(
                enabled=True,
                cold_threshold=0.8,
                cooldown_s=cooldown_gens,        # 「世代」を時間単位に見立てる
                exploration_multiplier=exploration_multiplier,
                recovery_ratio=0.5,
            ),
            clock=lambda: float(gen_state["gen"]),
        )

    panic_gens = 0
    gen_reached: int | None = None
    prev_best = best_f
    for g in range(1, n_gen + 1):
        gen_state["gen"] = g
        sigma = base_sigma
        if ctrl is not None:
            improved = best_f > prev_best + 1e-6
            # 停滞 (改善なし) を高 surprise として供給 → 閾値超で panic
            ctrl.observe_surprise(0.0 if improved else 1.0)
            if ctrl.is_panic:
                sigma = base_sigma * ctrl.mutation_rate_multiplier
                panic_gens += 1
        prev_best = best_f

        # 選択: 上位半分の truncation
        order = np.argsort(fit)[::-1]
        survivors = x[order[: max(1, pop // 2)]]
        # 交配 + gaussian 変異
        parents = rng.choice(survivors, size=pop)
        x = np.clip(parents + rng.normal(0.0, sigma, size=pop), -_BOUND, _BOUND)
        fit = deceptive_fitness(x)

        # elitism: best-ever を保持 (panic 探索で失わない)
        gi = int(np.argmax(fit))
        if float(fit[gi]) > best_f:
            best_f = float(fit[gi])
            best_x = float(x[gi])
        x[0] = best_x
        fit[0] = best_f

        if gen_reached is None and best_f > _GLOBAL_FIT_THRESHOLD:
            gen_reached = g

    return GaResult(
        use_antifragile=use_antifragile,
        seed=seed,
        best_fitness=best_f,
        best_x=best_x,
        reached_global=best_f > _GLOBAL_FIT_THRESHOLD,
        gen_reached=gen_reached,
        panic_gens=panic_gens,
        n_gen=n_gen,
    )


@dataclass(frozen=True)
class CompareResult:
    n_seeds: int
    baseline_escape_rate: float
    antifragile_escape_rate: float
    baseline_mean_best: float
    antifragile_mean_best: float
    antifragile_mean_panic_gens: float


def compare(*, n_seeds: int = 30, **kw) -> CompareResult:
    base = [run_ga(use_antifragile=False, seed=s, **kw) for s in range(n_seeds)]
    anti = [run_ga(use_antifragile=True, seed=s, **kw) for s in range(n_seeds)]
    return CompareResult(
        n_seeds=n_seeds,
        baseline_escape_rate=sum(r.reached_global for r in base) / n_seeds,
        antifragile_escape_rate=sum(r.reached_global for r in anti) / n_seeds,
        baseline_mean_best=float(np.mean([r.best_fitness for r in base])),
        antifragile_mean_best=float(np.mean([r.best_fitness for r in anti])),
        antifragile_mean_panic_gens=float(np.mean([r.panic_gens for r in anti])),
    )


def _ensure_utf8_stdout() -> None:
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass


def main() -> None:
    _ensure_utf8_stdout()
    r = compare(n_seeds=30)
    print("# Antifragile Mutation — 定量比較 PoC (局所最適からの脱出)\n")
    print(f"landscape: 局所最適 x={_LOCAL_X} (h={_LOCAL_H}) / 大域最適 x={_GLOBAL_X} (h={_GLOBAL_H})")
    print(f"seeds={r.n_seeds}\n")
    print("| 指標 | baseline (panic なし) | antifragile (panic あり) |")
    print("|---|---|---|")
    print(f"| 大域最適 脱出率 | {r.baseline_escape_rate:.0%} | {r.antifragile_escape_rate:.0%} |")
    print(f"| 平均 best fitness | {r.baseline_mean_best:.3f} | {r.antifragile_mean_best:.3f} |")
    print(f"| 平均 panic 世代数 (cost) | – | {r.antifragile_mean_panic_gens:.1f} |")


if __name__ == "__main__":
    main()
