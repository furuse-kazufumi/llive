# SPDX-License-Identifier: Apache-2.0
"""Synaptic strategy selector — Hebbian-style adaptive variant choice.

llive の hot path には「同じ抽象操作を 2 通り以上の実装で書ける」場所が
多数ある (例: TRIZ matrix lookup を linear vs dict vs perfect hash で書く,
Bayesian surprise を pure-Python vs numpy vectorized で書く, etc.).

本モジュールは **複数候補 (StrategyVariant) に重みを持たせ, 使うほど
良い候補の重みが強化される** Hebbian-style な選択器を提供する.

設計のコア:

- 各 variant に **synaptic weight** (浮動小数, 正値) を持たせる.
- 呼び出すたびに ε-greedy + weighted-softmax で 1 つを選択する.
- 実行後の **measured latency** で重みを更新:
  - その回の latency が平均より速ければ → 重みを **強化** (LTP, long-term
    potentiation 的).
  - 遅ければ → **減衰** (LTD).
- 一定回数後, 最良候補の重みが支配的になり, ε-greedy の greedy 経路で
  「自動的に」選ばれるようになる.
- `converge()` は推論時に最高重みを 1 つ取り出す (確率なし).

このアプローチは:

- **TRIZ FR-23〜27 (self-evolution)** と整合 — 「設計判断自体を RL 化する」.
- **Approval Bus** とは独立 — 重み変化は in-memory で許容可能な変動
  (副作用は計測のみ, 観察可能).
- **bounded modification (§E2)** に準拠 — 重みは `[min_weight, max_weight]`
  の envelope に拘束.
- Python 純実装. Rust 移植は将来 `perf/rust_ext/` 候補.

スレッド安全: ``_lock`` (threading.RLock) で重み更新と選択を直列化.
"""
from __future__ import annotations

import math
import random
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")

__all__ = [
    "StrategyVariant",
    "SelectionRecord",
    "SynapticSelector",
    "UCBSynapticSelector",
]


@dataclass
class StrategyVariant(Generic[T]):
    """One executable strategy candidate with a synaptic weight.

    Attributes:
        name: 識別子 (log / 観察用).
        impl: 実体. 任意のシグネチャ. caller が `variant.impl(*args, **kw)`
            のように呼ぶ.
        weight: synaptic weight. 大きいほど選ばれやすい. 初期 1.0.
        n_calls: これまでの呼び出し回数 (観察用).
        avg_latency_ms: 直近の平均 latency (EWMA, ms). 重み更新の基準値.
            未計測の間は 0.0.
        last_latency_ms: 直近 1 回の latency (ms). debug 用.
    """

    name: str
    impl: T
    weight: float = 1.0
    n_calls: int = 0
    avg_latency_ms: float = 0.0
    last_latency_ms: float = 0.0


@dataclass(frozen=True)
class SelectionRecord:
    """1 回の選択 + 計測結果の monitoring record."""

    variant_name: str
    latency_ms: float
    weight_before: float
    weight_after: float
    timestamp_s: float


@dataclass
class SynapticSelector(Generic[T]):
    """Hebbian-style weighted selector for strategy variants.

    Args:
        variants: 候補 variant 群. **空でないこと**. 名前重複は禁止.
        learning_rate: 重み更新の係数. 0 < lr <= 1. 大きいと収束が速いが
            unstable. デフォルト 0.05.
        exploration_rate: ε-greedy の ε. [0, 1]. 0 で純 greedy. デフォルト 0.10.
        min_weight: 重みの下限. 完全消滅を防ぐ (再選択の余地を残す).
            デフォルト 0.01.
        max_weight: 重みの上限. 一極集中の暴走を防ぐ. デフォルト 100.0.
        ewma_alpha: avg_latency_ms の EWMA 係数. 0 < α <= 1. デフォルト 0.30.
        rng: 乱数源 (test 用に固定可能). デフォルト `random.Random()`.

    Hebbian 更新ルール (latency 短いほど報酬正):

        reward = (mean_latency - measured) / mean_latency       # [-,+]
        weight_new = weight_old * (1 + learning_rate * reward)
        weight_new = clip(weight_new, min_weight, max_weight)

    `mean_latency` は本選択器が観測した全 variant の avg_latency_ms 平均.
    1 回でも計測した variant が存在しない場合は no-op (重み変化なし).
    """

    variants: list[StrategyVariant[T]]
    learning_rate: float = 0.05
    exploration_rate: float = 0.10
    min_weight: float = 0.01
    max_weight: float = 100.0
    ewma_alpha: float = 0.30
    rng: random.Random = field(default_factory=random.Random)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _history: list[SelectionRecord] = field(default_factory=list, repr=False)
    _history_cap: int = 1024

    def __post_init__(self) -> None:
        if not self.variants:
            raise ValueError("SynapticSelector requires at least one variant")
        names = [v.name for v in self.variants]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate variant names: {names}")
        if not (0.0 < self.learning_rate <= 1.0):
            raise ValueError("learning_rate must be in (0, 1]")
        if not (0.0 <= self.exploration_rate <= 1.0):
            raise ValueError("exploration_rate must be in [0, 1]")
        if not (0.0 < self.ewma_alpha <= 1.0):
            raise ValueError("ewma_alpha must be in (0, 1]")
        if not (0.0 < self.min_weight < self.max_weight):
            raise ValueError("require 0 < min_weight < max_weight")
        for v in self.variants:
            v.weight = max(self.min_weight, min(self.max_weight, v.weight))

    # ------------------------------------------------------------------ choose

    def choose(self) -> StrategyVariant[T]:
        """ε-greedy + weighted-softmax で 1 variant を選択して返す."""
        with self._lock:
            if self.rng.random() < self.exploration_rate:
                # exploration: 一様ランダム
                return self.rng.choice(self.variants)
            weights = [v.weight for v in self.variants]
            return self._weighted_choice(weights)

    def converge(self) -> StrategyVariant[T]:
        """重み最大の variant を 1 つ返す (推論時 = greedy)."""
        with self._lock:
            return max(self.variants, key=lambda v: v.weight)

    def _weighted_choice(self, weights: Sequence[float]) -> StrategyVariant[T]:
        # softmax で正規化してから choices に渡す.
        # 重みが極端に偏った場合の overflow 防止に最大値を引いておく.
        max_w = max(weights)
        exps = [math.exp(w - max_w) for w in weights]
        total = sum(exps)
        probs = [e / total for e in exps]
        return self.rng.choices(self.variants, weights=probs, k=1)[0]

    # ------------------------------------------------------------------ update

    def record_result(self, variant: StrategyVariant[T], latency_ms: float) -> SelectionRecord:
        """Variant の latency を受け取り重みを Hebbian 更新する.

        Returns:
            この回の選択 + 重み変化の SelectionRecord.
        """
        if latency_ms < 0.0:
            raise ValueError("latency_ms must be >= 0.0")
        with self._lock:
            weight_before = variant.weight
            # EWMA で avg_latency_ms を更新
            if variant.n_calls == 0:
                variant.avg_latency_ms = latency_ms
            else:
                variant.avg_latency_ms = (
                    self.ewma_alpha * latency_ms
                    + (1.0 - self.ewma_alpha) * variant.avg_latency_ms
                )
            variant.last_latency_ms = latency_ms
            variant.n_calls += 1

            # 全 variant の avg_latency_ms 平均 (>0 のものだけ集計)
            actives = [v.avg_latency_ms for v in self.variants if v.n_calls > 0]
            if not actives:
                weight_after = variant.weight
            else:
                mean = sum(actives) / len(actives)
                if mean <= 0.0:
                    weight_after = variant.weight
                else:
                    reward = (mean - latency_ms) / mean
                    new_w = variant.weight * (1.0 + self.learning_rate * reward)
                    variant.weight = max(self.min_weight, min(self.max_weight, new_w))
                    weight_after = variant.weight

            record = SelectionRecord(
                variant_name=variant.name,
                latency_ms=latency_ms,
                weight_before=weight_before,
                weight_after=weight_after,
                timestamp_s=time.time(),
            )
            self._history.append(record)
            if len(self._history) > self._history_cap:
                # 古いものから削除 (FIFO)
                del self._history[: len(self._history) - self._history_cap]
            return record

    # ------------------------------------------------------------------ call

    def call(self, *args, **kwargs):
        """1 サイクル: choose → impl 呼び出し → record_result を 1 行で.

        impl が `Callable[..., R]` を満たすことを caller 側で保証する.
        """
        variant = self.choose()
        impl = variant.impl
        if not callable(impl):
            raise TypeError(f"variant {variant.name!r} impl is not callable")
        t0 = time.perf_counter()
        try:
            result = impl(*args, **kwargs)
        finally:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self.record_result(variant, elapsed_ms)
        return result

    # ------------------------------------------------------------------ inspect

    def snapshot(self) -> list[dict]:
        """現在の variant 状態を JSON 化可能な dict 列で返す (観察用)."""
        with self._lock:
            return [
                {
                    "name": v.name,
                    "weight": v.weight,
                    "n_calls": v.n_calls,
                    "avg_latency_ms": v.avg_latency_ms,
                    "last_latency_ms": v.last_latency_ms,
                }
                for v in self.variants
            ]

    def history(self) -> list[SelectionRecord]:
        """選択履歴 (最新 `_history_cap` 件)."""
        with self._lock:
            return list(self._history)
