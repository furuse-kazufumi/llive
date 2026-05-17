# SPDX-License-Identifier: Apache-2.0
"""CREAT-FX — Creative Thinking Layer (v0.9).

人間の創造プロセス (拡散 → 構造化 → 収束) を llive 思考層に追加する。
v0.9 minimal prototype (2026-05-17):

* CREAT-01 :class:`KJNode` / :class:`KJBoard` / :class:`KJExtractor` — KJ法
  (発散 → 親和図クラスタリング → 命名)
"""

from __future__ import annotations

from llive.creat.kj import (
    AffinityCluster,
    IdeaGenerator,
    KJBoard,
    KJExtractor,
    KJNode,
)

__all__ = [
    "AffinityCluster",
    "IdeaGenerator",
    "KJBoard",
    "KJExtractor",
    "KJNode",
]
