# SPDX-License-Identifier: Apache-2.0
"""COG-MESH-10 Mesh5W1H + Granularity Hierarchy.

requirements_v0.8_cognitive_mesh.md §3 COG-MESH-10 の最小実装。
ユーザ「思考が 5W1H メッシュ状に繋がる」「単語 / 句 / 文節 / 文 / 段 / 主題」
(user_cognitive_mesh_model §12, 追記 22:55) を Annotation Channel
namespace と内部表現に明示する。

含むもの:
- Mesh5W1HNode (Who / What / When / Where / Why / How) 列挙
- Annotation Channel namespace 定数 (mesh.who, ..., mesh.how)
- Granularity (word/phrase/clause/sentence/paragraph/topic) 列挙
- Mesh5W1HGraph — ノード間 edge を保持する軽量グラフ
- annotate_5w1h() / granularity_of() — naive ベースの分類関数
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Optional


# ---------------------------------------------------------------------------
# 列挙
# ---------------------------------------------------------------------------


class Mesh5W1HNode(str, Enum):
    """5W1H メッシュのノード."""

    WHO = "who"
    WHAT = "what"
    WHEN = "when"
    WHERE = "where"
    WHY = "why"
    HOW = "how"


class Granularity(str, Enum):
    """言語化粒度階層 (低 → 高)."""

    WORD = "word"
    PHRASE = "phrase"
    CLAUSE = "clause"
    SENTENCE = "sentence"
    PARAGRAPH = "paragraph"
    TOPIC = "topic"


GRANULARITY_ORDER: tuple[Granularity, ...] = (
    Granularity.WORD,
    Granularity.PHRASE,
    Granularity.CLAUSE,
    Granularity.SENTENCE,
    Granularity.PARAGRAPH,
    Granularity.TOPIC,
)


# ---------------------------------------------------------------------------
# Annotation Channel namespace 定数
# ---------------------------------------------------------------------------


def channel_name(node: Mesh5W1HNode) -> str:
    """Annotation Channel namespace を返す (例: ``mesh.who``)."""
    return f"mesh.{node.value}"


# 全 namespace の一覧 (mesh.who / mesh.what / ... / mesh.how)
ALL_CHANNELS: tuple[str, ...] = tuple(channel_name(n) for n in Mesh5W1HNode)


# ---------------------------------------------------------------------------
# Mesh5W1HGraph
# ---------------------------------------------------------------------------


@dataclass
class Mesh5W1HEdge:
    src: Mesh5W1HNode
    dst: Mesh5W1HNode
    weight: float = 1.0


@dataclass
class Mesh5W1HGraph:
    """5W1H メッシュの軽量グラフ.

    各ノードは互いに edge を持つ。同一 src→dst の重複 edge は重みを合算する。
    """

    _edges: dict[tuple[Mesh5W1HNode, Mesh5W1HNode], float] = field(default_factory=dict)

    def link(self, src: Mesh5W1HNode, dst: Mesh5W1HNode, weight: float = 1.0) -> None:
        if src == dst:
            raise ValueError("self-loops are not allowed")
        key = (src, dst)
        self._edges[key] = self._edges.get(key, 0.0) + weight

    def weight(self, src: Mesh5W1HNode, dst: Mesh5W1HNode) -> float:
        return self._edges.get((src, dst), 0.0)

    def neighbors(self, src: Mesh5W1HNode) -> list[Mesh5W1HNode]:
        return [dst for (s, dst) in self._edges.keys() if s == src]

    def edges(self) -> list[Mesh5W1HEdge]:
        return [Mesh5W1HEdge(src=s, dst=d, weight=w) for (s, d), w in self._edges.items()]

    def __len__(self) -> int:
        return len(self._edges)


# ---------------------------------------------------------------------------
# naive ベース分類関数
# ---------------------------------------------------------------------------


_WHO_KEYWORDS = ("who", "誰", "I ", "私", "you", "あなた", "they", "彼", "彼女")
_WHAT_KEYWORDS = ("what", "何", "それ", "this", "that")
_WHEN_KEYWORDS = ("when", "いつ", "today", "今日", "tomorrow", "明日", "yesterday")
_WHERE_KEYWORDS = ("where", "どこ", "here", "ここ", "there", "そこ", "at ", "in ")
_WHY_KEYWORDS = ("why", "なぜ", "because", "ので", "から")
_HOW_KEYWORDS = ("how", "どう", "どのよう", "by ", "via", "using", "経由")

_NODE_KEYWORD_MAP: dict[Mesh5W1HNode, tuple[str, ...]] = {
    Mesh5W1HNode.WHO: _WHO_KEYWORDS,
    Mesh5W1HNode.WHAT: _WHAT_KEYWORDS,
    Mesh5W1HNode.WHEN: _WHEN_KEYWORDS,
    Mesh5W1HNode.WHERE: _WHERE_KEYWORDS,
    Mesh5W1HNode.WHY: _WHY_KEYWORDS,
    Mesh5W1HNode.HOW: _HOW_KEYWORDS,
}


def annotate_5w1h(text: str) -> dict[Mesh5W1HNode, list[str]]:
    """テキスト中で 5W1H に該当するキーワードを抽出 (naive)."""
    found: dict[Mesh5W1HNode, list[str]] = {n: [] for n in Mesh5W1HNode}
    lower = text.lower()
    for node, keywords in _NODE_KEYWORD_MAP.items():
        for kw in keywords:
            if kw.lower() in lower:
                found[node].append(kw)
    return found


def granularity_of(token: str) -> Granularity:
    """トークン文字列から粒度階層を推定 (naive、長さベース)."""
    n = len(token.strip())
    if n == 0:
        return Granularity.WORD
    if n < 8:
        return Granularity.WORD
    if n < 20:
        return Granularity.PHRASE
    if n < 40:
        return Granularity.CLAUSE
    if n < 100:
        return Granularity.SENTENCE
    if n < 400:
        return Granularity.PARAGRAPH
    return Granularity.TOPIC


def is_finer(a: Granularity, b: Granularity) -> bool:
    """a が b より細かいか."""
    return GRANULARITY_ORDER.index(a) < GRANULARITY_ORDER.index(b)
