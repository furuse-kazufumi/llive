# SPDX-License-Identifier: Apache-2.0
"""CREAT-01 — KJ法ノード生成 + 親和図クラスタリング (minimal prototype).

人間の創造プロセス「拡散 → 構造化 → 収束」の **拡散層** を担う。
LLM 呼び出しは Strategy 注入点で差し替え可能 — 初期実装は deterministic な
mock generator (語彙パーミュテーション) + Jaccard ベース親和図。

設計:

* :class:`KJNode` — 1 件のアイデア (id, text, tags, source)
* :class:`KJBoard` — ノード集合 + 親和クラスタ
* :class:`AffinityCluster` — 共通 tag / token を持つノード群 + 命名 (label)
* :class:`IdeaGenerator` (Protocol) — Brief から KJNode tuple を生成
* :class:`KJExtractor` — Brief → IdeaGenerator → KJBoard、ledger 連動

ledger event: ``kj_board_constructed``
trace_graph evidence_chain: ``kind="kj_node"`` (board の各 node が個別 entry)
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterable, Protocol, Sequence

if TYPE_CHECKING:
    from llive.brief.ledger import BriefLedger
    from llive.brief.types import Brief


_TOKEN_RE = re.compile(r"[A-Za-z0-9_ぁ-ゟ゠-ヿ一-鿿]+", re.UNICODE)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KJNode:
    """1 件の発散アイデア (KJ 法のカード)."""

    node_id: str
    text: str
    tags: tuple[str, ...] = ()
    source: str = "deterministic"

    def to_payload(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "text": self.text,
            "tags": list(self.tags),
            "source": self.source,
        }

    def tokens(self) -> set[str]:
        return {t.lower() for t in _TOKEN_RE.findall(self.text)}


@dataclass(frozen=True)
class AffinityCluster:
    """親和図 — 共通テーマで括られたノード群 + ラベル."""

    label: str
    node_ids: tuple[str, ...]
    shared_terms: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        return {
            "label": self.label,
            "node_ids": list(self.node_ids),
            "shared_terms": list(self.shared_terms),
        }


@dataclass(frozen=True)
class KJBoard:
    """KJ 法ノード集合 + 親和図."""

    brief_id: str
    nodes: tuple[KJNode, ...]
    clusters: tuple[AffinityCluster, ...] = ()

    def to_payload(self) -> dict[str, object]:
        return {
            "brief_id": self.brief_id,
            "nodes": [n.to_payload() for n in self.nodes],
            "clusters": [c.to_payload() for c in self.clusters],
        }


# ---------------------------------------------------------------------------
# Idea generators (Strategy)
# ---------------------------------------------------------------------------


class IdeaGenerator(Protocol):
    """A pluggable idea generator. LLM lens version slots in here."""

    def generate(self, brief: "Brief", *, max_ideas: int) -> tuple[KJNode, ...]:  # pragma: no cover
        ...


_PROMPT_PREFIXES: tuple[str, ...] = (
    "視点A — 構造分解",
    "視点B — 反例探索",
    "視点C — 類比導入",
    "視点D — 制約緩和",
    "視点E — 制約強化",
    "視点F — 比喩化",
    "視点G — 双対化",
    "視点H — 単位検算",
)


@dataclass(frozen=True)
class DeterministicIdeaGenerator:
    """Mock generator — 視点プレフィックス × brief.goal の組合せでアイデア化."""

    def generate(self, brief: "Brief", *, max_ideas: int) -> tuple[KJNode, ...]:
        out: list[KJNode] = []
        goal = brief.goal
        tags_base = tuple(t.lower() for t in _TOKEN_RE.findall(goal))[:4]
        # constraints から tag を補完
        for c in brief.constraints[:3]:
            tags_base += tuple(t.lower() for t in _TOKEN_RE.findall(c))[:2]
        for i, prefix in enumerate(_PROMPT_PREFIXES[:max_ideas]):
            text = f"{prefix}: {goal}"
            # 各視点でタグの組合せを変える (deterministic)
            tags = tags_base[i % max(1, len(tags_base)) :] + (prefix.split(" ")[0],)
            out.append(KJNode(
                node_id=f"kj-{brief.brief_id}-{i:02d}",
                text=text,
                tags=tags,
                source="deterministic",
            ))
        return tuple(out)


# ---------------------------------------------------------------------------
# Extractor / clusterer
# ---------------------------------------------------------------------------


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _affinity_cluster(nodes: Sequence[KJNode], *, threshold: float = 0.3) -> tuple[AffinityCluster, ...]:
    """単純な凝集型クラスタリング — Jaccard >= threshold で union-find."""
    if not nodes:
        return ()
    parent = {n.node_id: n.node_id for n in nodes}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    nodes_list = list(nodes)
    for i, a in enumerate(nodes_list):
        for b in nodes_list[i + 1 :]:
            sim = _jaccard(a.tokens(), b.tokens())
            if sim >= threshold:
                union(a.node_id, b.node_id)

    groups: dict[str, list[KJNode]] = {}
    for n in nodes_list:
        groups.setdefault(find(n.node_id), []).append(n)
    clusters: list[AffinityCluster] = []
    for root, members in groups.items():
        shared = members[0].tokens()
        for m in members[1:]:
            shared &= m.tokens()
        # label は最初のノードの prefix (視点) + 最頻 tag
        first = members[0]
        label_prefix = first.text.split(":", 1)[0] if ":" in first.text else first.text[:20]
        label = f"{label_prefix} (×{len(members)})"
        clusters.append(AffinityCluster(
            label=label,
            node_ids=tuple(m.node_id for m in members),
            shared_terms=tuple(sorted(shared))[:5],
        ))
    # 大きいクラスタを先頭に
    clusters.sort(key=lambda c: -len(c.node_ids))
    return tuple(clusters)


class KJExtractor:
    """Brief → KJBoard (発散ノード集合 + 親和図).

    LLM 駆動の generator に差し替えるときは ``generator=`` に
    :class:`IdeaGenerator` 実装を渡すだけで良い。
    """

    def __init__(
        self,
        *,
        generator: IdeaGenerator | None = None,
        max_ideas: int = 6,
        cluster_threshold: float = 0.3,
        ledger: "BriefLedger | None" = None,
    ) -> None:
        self._generator: IdeaGenerator = generator or DeterministicIdeaGenerator()
        self._max_ideas = max_ideas
        self._cluster_threshold = cluster_threshold
        self._ledger = ledger

    def bind_ledger(self, ledger: "BriefLedger | None") -> None:
        self._ledger = ledger

    def extract(self, brief: "Brief") -> KJBoard:
        nodes = self._generator.generate(brief, max_ideas=self._max_ideas)
        clusters = _affinity_cluster(nodes, threshold=self._cluster_threshold)
        board = KJBoard(brief_id=brief.brief_id, nodes=nodes, clusters=clusters)
        if self._ledger is not None:
            self._ledger.append("kj_board_constructed", board.to_payload())
        return board


__all__ = [
    "AffinityCluster",
    "DeterministicIdeaGenerator",
    "IdeaGenerator",
    "KJBoard",
    "KJExtractor",
    "KJNode",
]
