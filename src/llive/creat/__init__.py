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
from llive.creat.mindmap import (
    BranchExpander,
    MindMapBuilder,
    MindMapNode,
    MindMapTree,
)
from llive.creat.structurize import (
    RequirementCategory,
    RequirementDraft,
    StructureSynthesizer,
)
from llive.creat.synectics import (
    Analogy,
    AnalogyKind,
    AnalogySource,
    SynecticsEngine,
    SynecticsReport,
)

__all__ = [
    "AffinityCluster",
    "Analogy",
    "AnalogyKind",
    "AnalogySource",
    "BranchExpander",
    "IdeaGenerator",
    "KJBoard",
    "KJExtractor",
    "KJNode",
    "MindMapBuilder",
    "MindMapNode",
    "MindMapTree",
    "RequirementCategory",
    "RequirementDraft",
    "StructureSynthesizer",
    "SynecticsEngine",
    "SynecticsReport",
]
