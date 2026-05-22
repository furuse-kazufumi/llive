# SPDX-License-Identifier: Apache-2.0
"""PhyTree — content-addressable phylogenetic memory (llive v0.I EV-26).

llive v0.C の [[lineage.py]] が世代ごとの上位 N 体のスナップ (winners.jsonl)
を Mermaid 描画する **可視化レイヤ** であったのに対し, 本モジュールは
**全 lineage を git-like content-addressable DAG に保存** する **記憶レイヤ**.

アフターマン (Dixon 1981) の 5000 万年化石記録の AI 版を目指す:

- Individual ID = SHA-256(genome.to_dict() の JSON sort_keys=True bytes)
  同じ genome は必ず同じ ID (git の blob と同じ content-addressable 性質)
- Edge: parent_ID → child_ID, op (crossover / mutation / clone) + metadata
- DAG 構造 (個体は複数 parent を持ちうる, ∵ crossover)
- ``pin(id)`` で絶滅対象外として固定
- ``restore_extinct(id)`` で絶滅した個体を取り出す
- ``prune(alive_ids, keep_pinned=True)`` で alive でも pinned でもない node 削除
- ``to_dict() / from_dict()`` で JSON serialize
- ``to_mermaid()`` で Mermaid timeline 描画

形式化 (詳細は `docs/requirements_v0.I_meta_evolution_and_cross_substrate.md`
§4.2):

```
Storage:
  Individual ID = SHA-256(genome.serialize())
  Edge: parent_ID -> child_ID (with op: crossover / mutation / clone)
  PhyTree = DAG (not tree, due to crossover multiple parents)

Operations:
  pin(individual_id) -> pinned (絶滅対象外)
  restore_extinct(individual_id) -> Individual (load from PhyTree)
  prune(alive_ids) -> deletes nodes only if not pinned AND not alive
```

References:

- Dixon, D. (1981). *After Man: A Zoology of the Future.* St. Martin's Press.
- Lehman, J., & Stanley, K. O. (2011). *Abandoning Objectives: Evolution
  through the Search for Novelty Alone.* Evolutionary Computation 19(2).
- llive `docs/requirements_v0.I_meta_evolution_and_cross_substrate.md` §4.

Status (2026-05-22 着地): skeleton. インメモリ DAG + Individual ID
(SHA-256) + pin / restore_extinct / prune / Mermaid 描画 のみ.
実 EvolutionLoop 統合 + 永続化 (loose object on disk) は次フェーズ
(EV-27 以降).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

from llive.perf.evolutionary.individual import Individual

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

Op = Literal["crossover", "mutation", "clone", "seed"]
"""Edge の操作種別. ``seed`` は親なし (initial population).
"""

KNOWN_OPS: tuple[str, ...] = ("crossover", "mutation", "clone", "seed")


# ---------------------------------------------------------------------------
# Content-addressable ID
# ---------------------------------------------------------------------------


def compute_individual_id(individual: Individual) -> str:
    """Individual ID = SHA-256(genome.to_dict() の JSON sort_keys=True bytes).

    同じ genome → 同じ ID (content-addressable). individual.individual_id
    フィールドの uuid とは無関係であることに注意 (uuid は instance 固有,
    こちらは genome 固有).
    """
    genome_dict = individual.genome.to_dict()
    payload = json.dumps(genome_dict, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# Edge / Node
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PhyEdge:
    """親 → 子の遺伝操作記録. immutable.

    ``parent_id`` is the SHA-256 content ID of the parent genome.
    ``op`` is one of :data:`KNOWN_OPS`.
    ``metadata`` is arbitrary str→str (世代番号, mutation rate, etc).
    """

    parent_id: str
    child_id: str
    op: str
    metadata: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.op not in KNOWN_OPS:
            raise ValueError(f"unknown op {self.op!r}, expected one of {KNOWN_OPS}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_id": self.parent_id,
            "child_id": self.child_id,
            "op": self.op,
            "metadata": list(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PhyEdge:
        return cls(
            parent_id=str(data["parent_id"]),
            child_id=str(data["child_id"]),
            op=str(data["op"]),
            metadata=tuple(tuple(item) for item in data.get("metadata", [])),
        )


@dataclass(frozen=True)
class PhyNode:
    """1 個体 node — Individual snapshot + content ID.

    ``individual`` は記録された時点の Individual (genome + fitness 履歴).
    immutable のため, 同じ ID の再記録は no-op.
    """

    individual_id: str
    individual: Individual

    def to_dict(self) -> dict[str, Any]:
        return {
            "individual_id": self.individual_id,
            "individual": self.individual.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PhyNode:
        return cls(
            individual_id=str(data["individual_id"]),
            individual=Individual.from_dict(data["individual"]),
        )


# ---------------------------------------------------------------------------
# PhyTree (DAG)
# ---------------------------------------------------------------------------


@dataclass
class PhyTree:
    """Phylogenetic memory DAG.

    インメモリの dict ベース実装. node は content-addressable な ID で
    重複排除される. edge は (parent_id, child_id, op) の 3-tuple で
    重複排除される.

    永続化は次フェーズで loose object (git-like) として実装予定.
    """

    nodes: dict[str, PhyNode] = field(default_factory=dict)
    """content-addressable node 辞書. key = SHA-256 ID."""

    edges: list[PhyEdge] = field(default_factory=list)
    """親 → 子の遺伝操作記録. 同じ (parent, child, op) は dedup される."""

    pinned: set[str] = field(default_factory=set)
    """絶滅対象外として固定された node ID."""

    # -- core API ----------------------------------------------------------

    def add_individual(
        self,
        individual: Individual,
        parents: Iterable[Individual | str] = (),
        op: str = "seed",
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Individual を追加して content ID (SHA-256) を返す.

        Parameters
        ----------
        individual : Individual
            記録対象の個体.
        parents : Iterable[Individual | str]
            親 個体 もしくは 親 content-ID の iterable. crossover 時は 2 つ以上.
            mutation / clone は 1 つ. seed (initial) は空.
        op : str
            ``crossover`` / ``mutation`` / ``clone`` / ``seed`` のいずれか.
        metadata : dict[str, str] | None
            追加メタ情報 (世代番号, mutation rate, etc).

        Returns
        -------
        str
            記録された node の content-addressable ID.
        """
        if op not in KNOWN_OPS:
            raise ValueError(f"unknown op {op!r}, expected one of {KNOWN_OPS}")

        child_id = compute_individual_id(individual)

        # node 追加 (重複は no-op = 既存のまま保持 = content-addressable 性質)
        if child_id not in self.nodes:
            self.nodes[child_id] = PhyNode(individual_id=child_id, individual=individual)

        # parent 解決 + edge 追加
        meta_tuple: tuple[tuple[str, str], ...] = (
            tuple(sorted(metadata.items())) if metadata else ()
        )
        seen_edges: set[tuple[str, str, str, tuple[tuple[str, str], ...]]] = {
            (e.parent_id, e.child_id, e.op, e.metadata) for e in self.edges
        }
        for parent in parents:
            parent_id = (
                parent if isinstance(parent, str) else compute_individual_id(parent)
            )
            edge_key = (parent_id, child_id, op, meta_tuple)
            if edge_key in seen_edges:
                continue
            self.edges.append(
                PhyEdge(
                    parent_id=parent_id,
                    child_id=child_id,
                    op=op,
                    metadata=meta_tuple,
                )
            )
            seen_edges.add(edge_key)

        return child_id

    def get_individual(self, individual_id: str) -> Individual | None:
        """ID から Individual を取り出す. 無ければ None.

        絶滅 (prune 済) でも pinned ならここに残っているので restore_extinct
        がそのまま使える.
        """
        node = self.nodes.get(individual_id)
        return None if node is None else node.individual

    # -- ancestry queries --------------------------------------------------

    def get_parents(self, individual_id: str) -> list[str]:
        """直接の親 ID list."""
        return [e.parent_id for e in self.edges if e.child_id == individual_id]

    def get_children(self, individual_id: str) -> list[str]:
        """直接の子 ID list."""
        return [e.child_id for e in self.edges if e.parent_id == individual_id]

    def get_ancestors(
        self, individual_id: str, depth: int | None = None
    ) -> set[str]:
        """先祖 ID set (自分自身は含めない).

        ``depth=None`` で全先祖, ``depth=N`` で N hop までの先祖.
        """
        if depth is not None and depth < 0:
            raise ValueError(f"depth must be >= 0, got {depth}")
        ancestors: set[str] = set()
        frontier: list[tuple[str, int]] = [(individual_id, 0)]
        visited: set[str] = {individual_id}
        while frontier:
            current, d = frontier.pop()
            if depth is not None and d >= depth:
                continue
            for parent_id in self.get_parents(current):
                if parent_id in visited:
                    continue
                visited.add(parent_id)
                ancestors.add(parent_id)
                frontier.append((parent_id, d + 1))
        return ancestors

    def get_descendants(
        self, individual_id: str, depth: int | None = None
    ) -> set[str]:
        """子孫 ID set (自分自身は含めない).

        ``depth=None`` で全子孫, ``depth=N`` で N hop までの子孫.
        """
        if depth is not None and depth < 0:
            raise ValueError(f"depth must be >= 0, got {depth}")
        descendants: set[str] = set()
        frontier: list[tuple[str, int]] = [(individual_id, 0)]
        visited: set[str] = {individual_id}
        while frontier:
            current, d = frontier.pop()
            if depth is not None and d >= depth:
                continue
            for child_id in self.get_children(current):
                if child_id in visited:
                    continue
                visited.add(child_id)
                descendants.add(child_id)
                frontier.append((child_id, d + 1))
        return descendants

    # -- pinning / extinction ---------------------------------------------

    def pin(self, individual_id: str) -> None:
        """``individual_id`` を絶滅対象外として固定."""
        if individual_id not in self.nodes:
            raise KeyError(f"individual_id {individual_id!r} not in tree")
        self.pinned.add(individual_id)

    def unpin(self, individual_id: str) -> None:
        """pin を解除 (存在しなくても no-op)."""
        self.pinned.discard(individual_id)

    def restore_extinct(self, individual_id: str) -> Individual:
        """絶滅した個体を取り出す (lazy load).

        現在のインメモリ実装では :meth:`get_individual` と等価. 永続化
        実装後は loose object からの load を行う想定. node が存在しない
        場合は :class:`KeyError`.
        """
        node = self.nodes.get(individual_id)
        if node is None:
            raise KeyError(f"individual_id {individual_id!r} not in tree (truly extinct)")
        return node.individual

    def prune(
        self,
        alive_ids: Iterable[str],
        *,
        keep_pinned: bool = True,
    ) -> set[str]:
        """alive でも pinned でもない node を削除.

        Parameters
        ----------
        alive_ids : Iterable[str]
            現存する個体の ID set. これらは削除しない.
        keep_pinned : bool
            True (default) なら :attr:`pinned` の node も削除しない.

        Returns
        -------
        set[str]
            削除された node の ID set.
        """
        alive = set(alive_ids)
        keep = set(alive)
        if keep_pinned:
            keep |= self.pinned

        to_delete = set(self.nodes) - keep
        for nid in to_delete:
            del self.nodes[nid]
        # edge は両端の node が両方残っているもののみ残す
        self.edges = [
            e for e in self.edges if e.parent_id in self.nodes and e.child_id in self.nodes
        ]
        # 削除済 node の pin も解除
        self.pinned -= to_delete
        return to_delete

    # -- serialize ---------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
            "pinned": sorted(self.pinned),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PhyTree:
        tree = cls()
        for node_data in data.get("nodes", []):
            node = PhyNode.from_dict(node_data)
            tree.nodes[node.individual_id] = node
        for edge_data in data.get("edges", []):
            tree.edges.append(PhyEdge.from_dict(edge_data))
        tree.pinned = set(data.get("pinned", []))
        return tree

    # -- Mermaid render ----------------------------------------------------

    def to_mermaid(
        self,
        *,
        title: str | None = None,
        id_prefix_len: int = 8,
    ) -> str:
        """Mermaid graph TD (timeline) 形式で系統樹を描画.

        node 表示は ``individual_id[:id_prefix_len]`` で短縮. pinned node は
        ``classDef pinned fill:#fc9,stroke:#963`` でハイライト.
        Edge label に op を載せる.

        Empty tree の場合は ``empty[No individuals]`` placeholder を出力.
        """
        lines: list[str] = []
        if title:
            lines.append(f"%% {title}")
        lines.append("graph TD")

        if not self.nodes:
            lines.append("    empty[No individuals]")
            return "\n".join(lines)

        for nid in sorted(self.nodes):
            short = nid[:id_prefix_len]
            label = f"{short}<br/>gen {self.nodes[nid].individual.birth_generation}"
            lines.append(f'    n_{short}["{label}"]')

        for edge in self.edges:
            parent_short = edge.parent_id[:id_prefix_len]
            child_short = edge.child_id[:id_prefix_len]
            # 親 node が tree に居ない場合 (extinct で prune 済) は ghost node
            if edge.parent_id not in self.nodes:
                lines.append(f'    ghost_{parent_short}(["{parent_short} (extinct)"])')
                lines.append(
                    f"    ghost_{parent_short} -->|{edge.op}| n_{child_short}"
                )
            else:
                lines.append(
                    f"    n_{parent_short} -->|{edge.op}| n_{child_short}"
                )

        if self.pinned:
            for pid in sorted(self.pinned):
                if pid in self.nodes:
                    short = pid[:id_prefix_len]
                    lines.append(f"    class n_{short} pinned")
            lines.append("    classDef pinned fill:#fc9,stroke:#963,stroke-width:2px")

        return "\n".join(lines)


__all__ = [
    "KNOWN_OPS",
    "Op",
    "PhyEdge",
    "PhyNode",
    "PhyTree",
    "compute_individual_id",
]
