# SPDX-License-Identifier: Apache-2.0
"""run_recursive_inference — 個体内 self-refine cycle 実行 helper (llive v0.F EV-19).

:mod:`recursion_depth` で定義された :class:`RecursionDepthGene` を **実行する側** の
最小 helper. 1 個体が 1 つの層境界 (sensory→episodic 等) 内で
``gene.per_layer[layer]`` 回 self-loop で refine する.

設計方針:

- ``inference_fn`` は ``callable(input) -> output`` の純粋 wrapper. LLM backend や
  推論 stack を直接呼ばず, **任意 callable** を受け取れる skeleton にする
  (テストでは ``lambda x: x`` や ``lambda x: x + " refined"`` が使える).
- 各 iteration で SHA-256 ハッシュを取り, 前 iteration との差分を ``[0,1]`` に
  正規化した ``delta`` として返す. ``delta < gene.early_stop_threshold`` で停止.
- ``max_total_recursion`` クリップは呼び出し側 (層を跨ぐ orchestrator) で
  管理する想定だが, この helper でも安全のため 1 層内のループ数を
  ``min(per_layer[layer], gene.max_total_recursion)`` でクリップする.

形式化:

```
for t in range(min(per_layer[layer], max_total_recursion)):
    output_t = inference_fn(output_{t-1})
    delta_t  = hamming(hash(output_t), hash(output_{t-1})) / 256
    record trace
    if delta_t < early_stop_threshold and t >= 1:
        break
```

Status (2026-05-22 着地): skeleton. 純粋 callable 経由の動作確認のみ. LLM backend
統合 (Self-Refine prompt 自動生成 / Reflexion retrieval 等) は次フェーズ.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from llive.perf.evolutionary.recursion_depth import (
    NUM_LAYER_BOUNDARIES,
    RecursionDepthGene,
    RefineStrategy,
)

# ---------------------------------------------------------------------------
# RecursionTrace
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecursionTrace:
    """1 推論 iteration の trace. early-stop 判定 / 可視化 / lineage 用.

    Attributes:
        iteration: 0-indexed iteration number (初回 = 0).
        input_hash: 入力 (前 iteration の output) の SHA-256 hex digest.
        output_hash: 今回 output の SHA-256 hex digest.
        delta: hash 間の Hamming distance を 256 bit で正規化した [0,1] 値.
            ``early_stop_threshold`` 未満で停止判定される.
        refine_applied: この iteration で適用された refine 戦略.
        elapsed_ms: inference_fn 実行時間 (ms).
    """

    iteration: int
    input_hash: str
    output_hash: str
    delta: float
    refine_applied: RefineStrategy
    elapsed_ms: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hash_of(value: Any) -> str:
    """値を SHA-256 hex digest 化. bytes / str / repr() fallback."""
    if isinstance(value, bytes):
        data = value
    elif isinstance(value, str):
        data = value.encode("utf-8")
    else:
        # 任意 object → repr() で文字列化 (skeleton). 実 LLM 用には別途
        # canonical serializer を入れる予定.
        data = repr(value).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _hamming_delta(hash_a: str, hash_b: str) -> float:
    """2 つの hex digest 間の Hamming distance を [0,1] 正規化.

    SHA-256 hex は 64 文字 / 256 bit. bit 単位で XOR し popcount すれば
    Hamming distance が出る. 同一なら 0.0, 完全逆相関なら ~0.5 (確率的に
    期待される距離 = 半分の bit が異なる).
    """
    if hash_a == hash_b:
        return 0.0
    int_a = int(hash_a, 16)
    int_b = int(hash_b, 16)
    xor = int_a ^ int_b
    bit_count = xor.bit_count()
    return bit_count / 256.0


# ---------------------------------------------------------------------------
# run_recursive_inference
# ---------------------------------------------------------------------------


def run_recursive_inference(
    initial_input: Any,
    inference_fn: Callable[[Any], Any],
    gene: RecursionDepthGene,
    layer: int,
    rng: np.random.Generator | None = None,
) -> tuple[Any, list[RecursionTrace]]:
    """1 個体が 1 層内で recursion_depth 回 self-loop で refine する skeleton.

    Args:
        initial_input: 初期入力. inference_fn(initial_input) で 1 回目が走る.
        inference_fn: ``callable(input) -> output``. LLM や任意の推論 stack を
            wrap した callable. skeleton では純粋関数で OK.
        gene: 再帰回数を保持する RecursionDepthGene.
        layer: 0/1/2. ``gene.per_layer[layer]`` 回ループする.
        rng: (未使用 skeleton) 将来 refine_strategy 分岐の確率的選択用.

    Returns:
        ``(最終 output, list of RecursionTrace)``.

    Raises:
        ValueError: ``layer`` が範囲外.
    """
    if not 0 <= layer < NUM_LAYER_BOUNDARIES:
        raise ValueError(
            f"layer={layer} out of range [0, {NUM_LAYER_BOUNDARIES})"
        )

    # 安全のため per_layer[layer] と max_total_recursion で min を取る.
    target_depth = min(gene.per_layer[layer], gene.max_total_recursion)

    traces: list[RecursionTrace] = []
    current: Any = initial_input
    current_hash = _hash_of(current)

    for t in range(target_depth):
        start = time.perf_counter()
        next_output = inference_fn(current)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        next_hash = _hash_of(next_output)
        delta = _hamming_delta(current_hash, next_hash)

        traces.append(
            RecursionTrace(
                iteration=t,
                input_hash=current_hash,
                output_hash=next_hash,
                delta=delta,
                refine_applied=gene.refine_strategy,
                elapsed_ms=elapsed_ms,
            )
        )

        current = next_output
        current_hash = next_hash

        # early-stop: 差分が閾値未満で停止 (ただし最低 1 回は回す)
        # t >= 1 とすることで「初回 inference の有意な変化」を必ず観測する.
        # → identity fn なら t=0 で delta=0 だが「最低 1 回回した」状態で停止.
        if delta < gene.early_stop_threshold and t >= 0:
            break

    return current, traces


__all__ = [
    "RecursionTrace",
    "run_recursive_inference",
]
