# SPDX-License-Identifier: Apache-2.0
"""GraphRAG in-memory store — hybrid embedding + graph-proximity retrieval.

This is the skeleton implementation (numpy-only, no networkx / no
neo4j-driver) targeted at the *long-term* layer of llive's 4-layer
memory model. The store keeps:

* ``_nodes``     : ``dict[str, Node]``
* ``_out``       : ``dict[str, list[Edge]]``  (forward adjacency)
* ``_in``        : ``dict[str, list[Edge]]``  (reverse adjacency for
  cheap undirected traversal during retrieval)

The :meth:`query` method computes a *hybrid score* per candidate node:

    score = (1 - alpha) * embedding_cosine + alpha * graph_proximity

where ``graph_proximity`` is a hop-decayed sum over neighbours of seed
nodes whose embedding is closest to the query (see
``_graph_proximity``). The default ``alpha`` is ``0.4``.

Embedding ranking requires a pre-computed query embedding (set via the
``query_embedding`` argument). If ``query`` is called with text only and
no encoder is wired in (skeleton behaviour), ranking falls back to a
graph-only traversal seeded by the first lexical-match nodes.

Future swap candidates
----------------------
The adjacency-list backend is deliberately replaceable. ``networkx``
gives richer algorithms (centrality, shortest path) but stays in-process
and single-threaded. ``kùzu`` (already used by
``llive.memory.structural``) supports Cypher and on-disk persistence.
``neo4j`` adds enterprise features but requires a server. See
``design.md`` for the trade-off table.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

import numpy as np

from llive.memory.graph_rag.edge import Edge
from llive.memory.graph_rag.node import Node


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


class GraphRAGStore:
    """In-memory GraphRAG store with hybrid retrieval.

    Parameters
    ----------
    alpha:
        Mixing weight for graph proximity vs embedding cosine.
        ``score = (1 - alpha) * cosine + alpha * proximity``.
        Default ``0.4``.
    hop_decay:
        Per-hop decay factor for ``graph_proximity`` (default ``0.5``).
        Hop 1 contributes ``hop_decay``, hop 2 ``hop_decay**2``, etc.
    """

    def __init__(self, alpha: float = 0.4, hop_decay: float = 0.5) -> None:
        if not 0.0 <= alpha <= 1.0:
            raise ValueError(f"alpha must be in [0, 1], got {alpha}")
        if not 0.0 < hop_decay <= 1.0:
            raise ValueError(f"hop_decay must be in (0, 1], got {hop_decay}")
        self.alpha = float(alpha)
        self.hop_decay = float(hop_decay)
        self._nodes: dict[str, Node] = {}
        self._out: dict[str, list[Edge]] = defaultdict(list)
        self._in: dict[str, list[Edge]] = defaultdict(list)

    # -- mutation -----------------------------------------------------------

    def add_node(self, node: Node) -> None:
        """Insert or replace a node by id."""
        self._nodes[node.id] = node

    def add_edge(self, edge: Edge) -> None:
        """Insert an edge. Both endpoints must already be added as nodes."""
        if edge.src not in self._nodes:
            raise KeyError(f"src node not found: {edge.src}")
        if edge.dst not in self._nodes:
            raise KeyError(f"dst node not found: {edge.dst}")
        self._out[edge.src].append(edge)
        self._in[edge.dst].append(edge)

    # -- read ---------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._nodes)

    def get_node(self, node_id: str) -> Node | None:
        return self._nodes.get(node_id)

    def neighbors(
        self,
        node_id: str,
        hops: int = 1,
        relation_filter: str | set[str] | None = None,
    ) -> list[Node]:
        """Return distinct nodes reachable within ``hops`` (undirected).

        ``relation_filter`` constrains which edges count: a single string
        or a set of relation labels.
        """
        if node_id not in self._nodes:
            return []
        if hops < 1:
            return []
        if isinstance(relation_filter, str):
            allow: set[str] | None = {relation_filter}
        else:
            allow = set(relation_filter) if relation_filter else None

        seen: set[str] = {node_id}
        frontier: deque[tuple[str, int]] = deque([(node_id, 0)])
        out: list[Node] = []
        while frontier:
            cur, depth = frontier.popleft()
            if depth >= hops:
                continue
            for edge in self._out.get(cur, []) + self._in.get(cur, []):
                other = edge.dst if edge.src == cur else edge.src
                if other in seen:
                    continue
                if allow is not None and edge.relation not in allow:
                    continue
                seen.add(other)
                node = self._nodes.get(other)
                if node is not None:
                    out.append(node)
                frontier.append((other, depth + 1))
        return out

    # -- retrieval ----------------------------------------------------------

    def query(
        self,
        text: str,
        k: int = 5,
        max_hops: int = 2,
        query_embedding: np.ndarray | None = None,
    ) -> list[tuple[Node, float]]:
        """Hybrid retrieval: top-``k`` nodes by ``score``.

        ``text`` is currently only used for lexical seed selection when
        ``query_embedding`` is not supplied (skeleton behaviour — a real
        deployment will wire in a sentence encoder, see
        :class:`llive.memory.encoder.MemoryEncoder`).

        Returns a list of ``(Node, score)`` pairs sorted by score
        descending. Empty when the store has no nodes.
        """
        if not self._nodes:
            return []
        if k <= 0:
            return []

        # 1. embedding similarity (cosine).
        cosines: dict[str, float] = {}
        if query_embedding is not None:
            q = np.asarray(query_embedding, dtype=np.float32).reshape(-1)
            for nid, node in self._nodes.items():
                if node.embedding is not None:
                    cosines[nid] = _cosine(q, np.asarray(node.embedding, dtype=np.float32).reshape(-1))
                else:
                    cosines[nid] = 0.0
        else:
            # lexical fallback: nodes whose payload contains the text.
            txt = (text or "").lower().strip()
            for nid, node in self._nodes.items():
                blob = " ".join(str(v) for v in node.payload.values()).lower()
                cosines[nid] = 1.0 if txt and txt in blob else 0.0

        # 2. graph proximity from top embedding seeds.
        proximity = self._graph_proximity(cosines, max_hops=max_hops)

        # 3. combine.
        scored: list[tuple[Node, float]] = []
        for nid, node in self._nodes.items():
            score = (1.0 - self.alpha) * cosines.get(nid, 0.0) + self.alpha * proximity.get(nid, 0.0)
            scored.append((node, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]

    def _graph_proximity(self, seeds: dict[str, float], max_hops: int) -> dict[str, float]:
        """Hop-decayed proximity score accumulated from each seed.

        Each node contributes its own ``seeds[node]`` to itself, then
        spreads ``seeds[node] * hop_decay ** d`` to neighbours at hop
        distance ``d`` (1 <= d <= max_hops). Multiple paths sum.
        """
        result: dict[str, float] = defaultdict(float)
        if max_hops < 0:
            return result
        for sid, weight in seeds.items():
            if weight <= 0.0 or sid not in self._nodes:
                continue
            # BFS from seed up to max_hops.
            result[sid] += weight
            if max_hops == 0:
                continue
            seen: set[str] = {sid}
            frontier: deque[tuple[str, int]] = deque([(sid, 0)])
            while frontier:
                cur, depth = frontier.popleft()
                if depth >= max_hops:
                    continue
                for edge in self._out.get(cur, []) + self._in.get(cur, []):
                    other = edge.dst if edge.src == cur else edge.src
                    if other in seen:
                        continue
                    seen.add(other)
                    contribution = weight * (self.hop_decay ** (depth + 1)) * max(edge.weight, 0.0)
                    result[other] += contribution
                    frontier.append((other, depth + 1))
        return result

    # -- serialization ------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        edges: list[dict[str, Any]] = []
        for adj in self._out.values():
            edges.extend(e.to_dict() for e in adj)
        return {
            "alpha": self.alpha,
            "hop_decay": self.hop_decay,
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "edges": edges,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GraphRAGStore:
        store = cls(
            alpha=float(d.get("alpha", 0.4)),
            hop_decay=float(d.get("hop_decay", 0.5)),
        )
        for nd in d.get("nodes", []):
            store.add_node(Node.from_dict(nd))
        for ed in d.get("edges", []):
            store.add_edge(Edge.from_dict(ed))
        return store
