# SPDX-License-Identifier: Apache-2.0
"""COG-MESH-02 拡張 — embedding ベース semantic similarity.

requirements_v0.8_cognitive_mesh.md §3 COG-MESH-02 で予告した
「token match → embedding semantic similarity」への昇格を実装する adapter。

設計:
- ``MemoryEncoder`` (sentence-transformers / hash fallback) を再利用。
- ``__call__(a, b) -> float`` で cosine 類似度 (0..1 clipped) を返す。
- ``TitleRecallPlanner(similarity_fn=...)`` に注入できる callable interface。
- numpy 必須だが MemoryEncoder 既存依存と同じ (新規依存ゼロ)。

設計上の選択:
- 戻り値は cosine sim を ``[0, 1]`` に clip。負方向は意味が無いため (LLM
  の自然文埋め込みでは負類似はノイズ寄り)。
- ``encoder.encode([a, b])`` で 1 回呼ぶ (1 系統 2 ベクトル)。
- 例外時は 0.0 を返す (fail-closed)。token match との max を取る upstream
  で実質フォールバックが効く。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from llive.memory.encoder import MemoryEncoder


@dataclass
class EmbeddingSimilarityFn:
    """MemoryEncoder を使う cosine similarity callable.

    Args:
        encoder: text → vector を返す MemoryEncoder.
    """

    encoder: MemoryEncoder

    def __call__(self, a: str, b: str) -> float:
        try:
            arr = self.encoder.encode([a, b])
        except Exception:  # noqa: BLE001 — fail-closed
            return 0.0
        if arr.shape[0] != 2:
            return 0.0
        v1 = np.asarray(arr[0], dtype=np.float32)
        v2 = np.asarray(arr[1], dtype=np.float32)
        n1 = float(np.linalg.norm(v1))
        n2 = float(np.linalg.norm(v2))
        if n1 == 0.0 or n2 == 0.0:
            return 0.0
        sim = float(np.dot(v1, v2) / (n1 * n2))
        # clip to [0, 1]; 負方向 sim は本ドメインで無意味
        if sim < 0.0:
            return 0.0
        if sim > 1.0:
            return 1.0
        return sim


__all__ = ["EmbeddingSimilarityFn"]
