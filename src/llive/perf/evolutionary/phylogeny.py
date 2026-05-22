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

    # -- animated SVG render ----------------------------------------------

    def to_animated_svg(
        self,
        viewbox_width: int = 800,
        viewbox_height: int = 240,
        max_generations: int = 10,
        layout: str = "left_to_right",
    ) -> str:
        """PhyTree を animated SVG (SMIL, no JS) 文字列として返す.

        Qiita hero bar フォーマット (800x240) に揃えた hero 風 SVG.

        - generation 別に column / row 配置 (DAG なので depth = generation).
          ``layout='left_to_right'`` で世代を横軸 (X), ``layout='top_down'`` で
          世代を縦軸 (Y) に並べる.
        - node = 円 (radius 6-8), edge = curved cubic Bezier line.
        - 新規 node は fade-in animation (SMIL ``<animate>``) — 世代順に
          stagger された begin offset.
        - pinned node は 色強調 + 二重円 (outer stroke + filled inner circle).
        - extinct (= node が tree から消えたが edge には残っている) node は
          ghost (薄い色 + dashed stroke).
        - 親 → 子 のエッジは順次描画 (stagger, stroke-dashoffset animation).
        - background gradient, palette は ``#5dd1ff`` / ``#7ee787`` /
          ``#ffd166`` / ``#ef476f`` を世代深度に応じて使い分け.

        Parameters
        ----------
        viewbox_width, viewbox_height : int
            SVG viewBox サイズ. 普及 PR では 800x240 を統一推奨.
        max_generations : int
            描画対象の最大世代数. これを超える世代は省略 (上限 clamp).
        layout : str
            ``"left_to_right"`` (default) or ``"top_down"``.

        Returns
        -------
        str
            完結した SVG 文字列 (``<svg ...>...</svg>``).

        Notes
        -----
        SMIL animation のみ. JavaScript は使わない. ``aria-label`` / ``<title>``
        / ``<desc>`` を含むので screen reader にも対応.
        """
        if layout not in ("left_to_right", "top_down"):
            raise ValueError(
                f"unknown layout {layout!r}, expected 'left_to_right' or 'top_down'"
            )
        if max_generations < 1:
            raise ValueError(f"max_generations must be >= 1, got {max_generations}")

        # Empty tree: 背景 + 中央 placeholder text を返す
        if not self.nodes:
            return self._render_empty_svg(viewbox_width, viewbox_height)

        # 世代別に node を分類
        gen_to_nodes: dict[int, list[str]] = {}
        for nid, node in self.nodes.items():
            gen = min(node.individual.birth_generation, max_generations - 1)
            gen_to_nodes.setdefault(gen, []).append(nid)
        # 安定順 (ID sort) のため
        for gen in gen_to_nodes:
            gen_to_nodes[gen].sort()
        generations = sorted(gen_to_nodes)

        # 配置パラメータ
        margin_x = 60
        margin_y = 60
        if layout == "left_to_right":
            usable_w = viewbox_width - 2 * margin_x
            usable_h = viewbox_height - 2 * margin_y
            n_gen_slots = max(1, len(generations))
            col_step = usable_w / max(1, n_gen_slots - 1) if n_gen_slots > 1 else 0
        else:  # top_down
            usable_w = viewbox_width - 2 * margin_x
            usable_h = viewbox_height - 2 * margin_y
            n_gen_slots = max(1, len(generations))
            row_step = usable_h / max(1, n_gen_slots - 1) if n_gen_slots > 1 else 0

        # node ID → (cx, cy) 座標
        positions: dict[str, tuple[float, float]] = {}
        gen_to_index: dict[int, int] = {g: i for i, g in enumerate(generations)}
        for gen, nids in gen_to_nodes.items():
            gi = gen_to_index[gen]
            n_in_gen = len(nids)
            if layout == "left_to_right":
                cx = margin_x + gi * col_step if n_gen_slots > 1 else viewbox_width / 2
                if n_in_gen == 1:
                    cy_list = [viewbox_height / 2]
                else:
                    step = usable_h / max(1, n_in_gen - 1)
                    cy_list = [margin_y + j * step for j in range(n_in_gen)]
                for nid, cy in zip(nids, cy_list, strict=True):
                    positions[nid] = (cx, cy)
            else:  # top_down
                cy = margin_y + gi * row_step if n_gen_slots > 1 else viewbox_height / 2
                if n_in_gen == 1:
                    cx_list = [viewbox_width / 2]
                else:
                    step = usable_w / max(1, n_in_gen - 1)
                    cx_list = [margin_x + j * step for j in range(n_in_gen)]
                for nid, cx in zip(nids, cx_list, strict=True):
                    positions[nid] = (cx, cy)

        # color palette (世代深度に応じて)
        palette = ("#ef476f", "#ffd166", "#7ee787", "#5dd1ff")
        n_palette = len(palette)

        # animation 1 cycle (秒)
        total_dur = max(6.0, len(generations) * 1.2)

        # SVG 構築 ---------------------------------------------------------
        parts: list[str] = []
        parts.append(
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {viewbox_width} {viewbox_height}" '
            f'role="img" aria-label="PhyTree phylogenetic DAG across generations">'
        )
        n_nodes = len(self.nodes)
        n_edges = len(self.edges)
        n_pinned = len(self.pinned & set(self.nodes))
        parts.append(
            f"<title>llive PhyTree — {n_nodes} individuals across "
            f"{len(generations)} generations ({n_pinned} pinned)</title>"
        )
        parts.append(
            "<desc>Phylogenetic DAG: nodes are content-addressable individuals, "
            "edges are crossover/mutation/clone operations. SMIL fade-in per "
            "generation. Pinned nodes have double-circle accent; extinct ancestors "
            "appear as ghost ring. No JavaScript.</desc>"
        )

        # defs: background gradient
        parts.append("<defs>")
        parts.append(
            '<linearGradient id="phytree_bg" x1="0" y1="0" x2="1" y2="1">'
            '<stop offset="0%" stop-color="#0e1426"/>'
            '<stop offset="100%" stop-color="#0a0f17"/>'
            "</linearGradient>"
        )
        parts.append("</defs>")

        # background
        parts.append(
            f'<rect width="{viewbox_width}" height="{viewbox_height}" '
            f'fill="url(#phytree_bg)"/>'
        )

        # title text (hero bar 風)
        parts.append(
            f'<text x="{viewbox_width / 2}" y="28" text-anchor="middle" '
            f'fill="#e6edf3" font-family="ui-sans-serif,system-ui,sans-serif" '
            f'font-size="16" font-weight="700">'
            f"llive PhyTree — {n_nodes} individuals × {len(generations)} generations"
            "</text>"
        )

        # generation axis labels (left_to_right / top_down で位置を変える)
        for gen in generations:
            gi = gen_to_index[gen]
            if layout == "left_to_right":
                x = (
                    margin_x + gi * col_step
                    if n_gen_slots > 1
                    else viewbox_width / 2
                )
                y = viewbox_height - 12
                parts.append(
                    f'<text x="{x}" y="{y}" text-anchor="middle" '
                    f'fill="#94a3b8" font-family="ui-sans-serif,system-ui,sans-serif" '
                    f'font-size="10">gen {gen}</text>'
                )
            else:
                x = 30
                y = (
                    margin_y + gi * row_step
                    if n_gen_slots > 1
                    else viewbox_height / 2
                )
                parts.append(
                    f'<text x="{x}" y="{y + 3}" text-anchor="middle" '
                    f'fill="#94a3b8" font-family="ui-sans-serif,system-ui,sans-serif" '
                    f'font-size="10">gen {gen}</text>'
                )

        # edges (extinct parent も含む) — 親が pos に居なければ ghost を生成
        ghost_positions: dict[str, tuple[float, float]] = {}
        ghost_counter = 0
        for edge_idx, edge in enumerate(self.edges):
            # 子は必ず描画対象
            if edge.child_id not in positions:
                continue
            cx_child, cy_child = positions[edge.child_id]
            if edge.parent_id in positions:
                cx_parent, cy_parent = positions[edge.parent_id]
                is_ghost = False
            else:
                # extinct ancestor — 子の生成方向にずらして配置
                if edge.parent_id not in ghost_positions:
                    if layout == "left_to_right":
                        gx = max(20, cx_child - col_step if n_gen_slots > 1 else cx_child - 80)
                        gy = cy_child + (ghost_counter % 3 - 1) * 18
                    else:
                        gx = cx_child + (ghost_counter % 3 - 1) * 18
                        gy = max(20, cy_child - row_step if n_gen_slots > 1 else cy_child - 60)
                    ghost_positions[edge.parent_id] = (gx, gy)
                    ghost_counter += 1
                cx_parent, cy_parent = ghost_positions[edge.parent_id]
                is_ghost = True

            # cubic Bezier (control points)
            if layout == "left_to_right":
                cp1x = cx_parent + (cx_child - cx_parent) * 0.5
                cp1y = cy_parent
                cp2x = cx_parent + (cx_child - cx_parent) * 0.5
                cp2y = cy_child
            else:
                cp1x = cx_parent
                cp1y = cy_parent + (cy_child - cy_parent) * 0.5
                cp2x = cx_child
                cp2y = cy_parent + (cy_child - cy_parent) * 0.5
            d = (
                f"M {cx_parent:.1f},{cy_parent:.1f} "
                f"C {cp1x:.1f},{cp1y:.1f} {cp2x:.1f},{cp2y:.1f} "
                f"{cx_child:.1f},{cy_child:.1f}"
            )
            stroke = "#4b5563" if is_ghost else "#64748b"
            dash = ' stroke-dasharray="3 3"' if is_ghost else ""
            # 子 node が居る世代の index で stagger
            child_gen = self.nodes[edge.child_id].individual.birth_generation
            child_gi = gen_to_index.get(min(child_gen, max_generations - 1), 0)
            begin = (child_gi / max(1, len(generations))) * total_dur
            parts.append(
                f'<path d="{d}" fill="none" stroke="{stroke}" '
                f'stroke-width="1.4"{dash} opacity="0" class="phytree-edge"'
                f' data-op="{edge.op}">'
                f'<animate attributeName="opacity" values="0;0.8" '
                f'begin="{begin:.2f}s" dur="0.6s" fill="freeze" '
                f'repeatCount="1"/>'
                "</path>"
            )

        # ghost ancestor circles (extinct)
        for gid, (gx, gy) in ghost_positions.items():
            parts.append(
                f'<circle cx="{gx:.1f}" cy="{gy:.1f}" r="5" '
                f'fill="none" stroke="#475569" stroke-width="1" '
                f'stroke-dasharray="2 2" opacity="0.5" class="phytree-ghost"/>'
            )
            parts.append(
                f'<text x="{gx:.1f}" y="{gy + 18:.1f}" text-anchor="middle" '
                f'fill="#64748b" font-family="ui-sans-serif,system-ui,sans-serif" '
                f'font-size="8" opacity="0.6">extinct</text>'
            )

        # nodes (円)
        for nid, (cx, cy) in positions.items():
            ind = self.nodes[nid].individual
            gen = min(ind.birth_generation, max_generations - 1)
            gi = gen_to_index[gen]
            color = palette[gi % n_palette]
            is_pinned = nid in self.pinned
            radius = 8 if is_pinned else 6
            begin = (gi / max(1, len(generations))) * total_dur

            # node group
            short = nid[:8]
            classes = "phytree-node" + (" pinned" if is_pinned else "")
            parts.append(
                f'<g class="{classes}" data-id="{short}" '
                f'data-gen="{ind.birth_generation}">'
            )
            # pinned: 二重円 (outer ring)
            if is_pinned:
                parts.append(
                    f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius + 3}" '
                    f'fill="none" stroke="{color}" stroke-width="1.2" '
                    f'opacity="0" class="phytree-pin-ring">'
                    f'<animate attributeName="opacity" values="0;0.9" '
                    f'begin="{begin:.2f}s" dur="0.8s" fill="freeze" '
                    f'repeatCount="1"/>'
                    f'<animate attributeName="r" values="{radius + 3};{radius + 5};{radius + 3}" '
                    f'begin="{begin + 0.8:.2f}s" dur="2.4s" '
                    f'repeatCount="indefinite"/>'
                    "</circle>"
                )
            # main node
            parts.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius}" '
                f'fill="{color}" stroke="#0a0f17" stroke-width="1.5" '
                f'opacity="0">'
                f'<animate attributeName="opacity" values="0;1" '
                f'begin="{begin:.2f}s" dur="0.6s" fill="freeze" '
                f'repeatCount="1"/>'
                "</circle>"
            )
            # label (short ID)
            parts.append(
                f'<text x="{cx:.1f}" y="{cy + radius + 12:.1f}" '
                f'text-anchor="middle" fill="#cbd5e1" '
                f'font-family="ui-monospace,monospace" font-size="8" '
                f'opacity="0">'
                f"{short}"
                f'<animate attributeName="opacity" values="0;0.8" '
                f'begin="{begin + 0.3:.2f}s" dur="0.6s" fill="freeze" '
                f'repeatCount="1"/>'
                "</text>"
            )
            parts.append("</g>")

        # legend (右下)
        legend_x = viewbox_width - 130
        legend_y = viewbox_height - 70
        parts.append(
            f'<g transform="translate({legend_x} {legend_y})" '
            f'font-family="ui-sans-serif,system-ui,sans-serif" font-size="9" '
            f'fill="#94a3b8">'
        )
        parts.append(
            '<text x="0" y="0" font-weight="600" fill="#e6edf3">legend</text>'
        )
        for i, (label, color) in enumerate(
            zip(("seed", "early", "mid", "elite"), palette, strict=True)
        ):
            parts.append(
                f'<circle cx="6" cy="{12 + i * 12}" r="4" fill="{color}"/>'
                f'<text x="16" y="{15 + i * 12}">{label}</text>'
            )
        parts.append("</g>")

        # footer subtle text
        parts.append(
            f'<text x="{viewbox_width / 2}" y="{viewbox_height - 28}" '
            f'text-anchor="middle" fill="#64748b" '
            f'font-family="ui-sans-serif,system-ui,sans-serif" font-size="9">'
            f"{n_edges} edges · {n_pinned} pinned · content-addressable DAG"
            "</text>"
        )

        parts.append("</svg>")
        return "".join(parts)

    @staticmethod
    def _render_empty_svg(viewbox_width: int, viewbox_height: int) -> str:
        """Empty PhyTree 用の placeholder SVG."""
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {viewbox_width} {viewbox_height}" '
            f'role="img" aria-label="Empty PhyTree placeholder">'
            "<title>llive PhyTree — empty</title>"
            "<desc>Phylogenetic DAG with no individuals yet. "
            "Add via PhyTree.add_individual() to populate.</desc>"
            "<defs>"
            '<linearGradient id="phytree_bg_empty" x1="0" y1="0" x2="1" y2="1">'
            '<stop offset="0%" stop-color="#0e1426"/>'
            '<stop offset="100%" stop-color="#0a0f17"/>'
            "</linearGradient>"
            "</defs>"
            f'<rect width="{viewbox_width}" height="{viewbox_height}" '
            f'fill="url(#phytree_bg_empty)"/>'
            f'<text x="{viewbox_width / 2}" y="{viewbox_height / 2 - 4}" '
            f'text-anchor="middle" fill="#94a3b8" '
            f'font-family="ui-sans-serif,system-ui,sans-serif" font-size="13" '
            f'font-weight="600">PhyTree is empty</text>'
            f'<text x="{viewbox_width / 2}" y="{viewbox_height / 2 + 16}" '
            f'text-anchor="middle" fill="#64748b" '
            f'font-family="ui-sans-serif,system-ui,sans-serif" font-size="10">'
            "add individuals to see the phylogenetic DAG</text>"
            "</svg>"
        )


__all__ = [
    "KNOWN_OPS",
    "Op",
    "PhyEdge",
    "PhyNode",
    "PhyTree",
    "compute_individual_id",
]
