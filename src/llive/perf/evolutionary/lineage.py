# SPDX-License-Identifier: Apache-2.0
"""系統樹 (lineage) — 世代を跨いだ親子関係の Mermaid 描画 (llive v0.C LV-10).

`Individual.parent_ids` と `birth_generation` を辿って Mermaid graph 形式に
変換する. ``winners.jsonl`` (世代ごと上位 N 体の serialize) を読んで Mermaid
にする helper も提供.

公開 API:

* :func:`render_lineage_mermaid` — Population history → Mermaid graph string
* :func:`write_winners_jsonl` — 世代ごとの上位 N 体を JSONL に追記
* :func:`load_winners_jsonl` — JSONL を読んで [Winner] に復元
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from llive.perf.evolutionary.population import Population


@dataclass
class Winner:
    """世代ごとの 1 個体スナップ (winners.jsonl の 1 行)."""

    generation: int
    individual_id: str
    parent_ids: tuple[str, ...]
    score: float
    rank: int = 0  # 当該世代の何位か (0 = best)

    def to_dict(self) -> dict:
        return {
            "generation": int(self.generation),
            "individual_id": self.individual_id,
            "parent_ids": list(self.parent_ids),
            "score": float(self.score),
            "rank": int(self.rank),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Winner:
        return cls(
            generation=int(data["generation"]),
            individual_id=str(data["individual_id"]),
            parent_ids=tuple(data.get("parent_ids", [])),
            score=float(data["score"]),
            rank=int(data.get("rank", 0)),
        )


# ---------------------------------------------------------------------------
# winners.jsonl I/O
# ---------------------------------------------------------------------------


def write_winners_jsonl(
    path: Path | str,
    population: Population,
    top_n: int = 3,
) -> int:
    """``population`` の上位 ``top_n`` 体を ``path`` に append.

    1 世代 1 回呼ぶ. Returns 書き込んだ行数.
    """
    sorted_inds = population.sorted_by_score_desc()[:top_n]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for rank, ind in enumerate(sorted_inds):
            winner = Winner(
                generation=population.generation,
                individual_id=ind.individual_id,
                parent_ids=ind.parent_ids,
                score=ind.score,
                rank=rank,
            )
            fh.write(json.dumps(winner.to_dict(), ensure_ascii=False) + "\n")
    return len(sorted_inds)


def load_winners_jsonl(path: Path | str) -> list[Winner]:
    """winners.jsonl を全件読んで Winner の list を返す."""
    path = Path(path)
    if not path.exists():
        return []
    winners: list[Winner] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        winners.append(Winner.from_dict(json.loads(line)))
    return winners


# ---------------------------------------------------------------------------
# Mermaid render
# ---------------------------------------------------------------------------


def render_lineage_mermaid(
    winners: Iterable[Winner],
    *,
    highlight_top_rank: int = 0,
    title: str | None = None,
) -> str:
    """winners (世代ごと上位 N 体) を Mermaid graph TD で描画.

    Parameters
    ----------
    winners : Iterable[Winner]
        ``load_winners_jsonl`` で読んだもの.
    highlight_top_rank : int
        各世代 rank<=highlight_top_rank の個体に classDef ``winner`` を付与.
        default 0 = rank 0 (世代 best) のみ強調.
    title : str | None
        Mermaid の前に %% コメントで挿入.
    """
    lines: list[str] = []
    if title:
        lines.append(f"%% {title}")
    lines.append("graph TD")

    winners_list = list(winners)
    if not winners_list:
        lines.append("    empty[No winners recorded]")
        return "\n".join(lines)

    # node 定義
    node_ids: set[str] = set()
    for w in winners_list:
        nid = _node_id(w.generation, w.individual_id)
        if nid in node_ids:
            continue
        node_ids.add(nid)
        label = f"gen {w.generation} #{w.rank}<br/>{w.individual_id[:8]}<br/>score={w.score:.3f}"
        lines.append(f"    {nid}[\"{label}\"]")

    # edge (親 → 子). 同 id が複数世代に出る (elitism 持ち越し) ため、id ごとに
    # 世代リストを持ち、子より前の世代で最も近いものを親とする (B-RES-2)。
    # 単純な {id: winner} dict だと最後の世代で上書きされ自己ループ/誤親になる。
    by_id_gens: dict[str, list[Winner]] = defaultdict(list)
    for w in winners_list:
        by_id_gens[w.individual_id].append(w)

    def _resolve_parent(parent_id: str, child_generation: int) -> Winner | None:
        cands = [
            pw
            for pw in by_id_gens.get(parent_id, [])
            if pw.generation < child_generation
        ]
        return max(cands, key=lambda pw: pw.generation) if cands else None

    edges_emitted: set[tuple[str, str]] = set()
    for w in winners_list:
        child_nid = _node_id(w.generation, w.individual_id)
        for parent_id in w.parent_ids:
            parent_w = _resolve_parent(parent_id, w.generation)
            if parent_w is None:
                # 親が winners に居ない場合は generation - 1 の架空 node に
                ghost_nid = _ghost_node_id(w.generation - 1, parent_id)
                edge = (ghost_nid, child_nid)
                if edge in edges_emitted:
                    continue
                lines.append(f"    {ghost_nid}([\"gen {w.generation - 1}<br/>{parent_id[:8]}\"])")
                lines.append(f"    {ghost_nid} --> {child_nid}")
                edges_emitted.add(edge)
            else:
                parent_nid = _node_id(parent_w.generation, parent_w.individual_id)
                edge = (parent_nid, child_nid)
                if edge in edges_emitted:
                    continue
                lines.append(f"    {parent_nid} --> {child_nid}")
                edges_emitted.add(edge)

    # 強調
    for w in winners_list:
        if w.rank <= highlight_top_rank:
            nid = _node_id(w.generation, w.individual_id)
            lines.append(f"    class {nid} winner")
    lines.append("    classDef winner fill:#9f9,stroke:#363,stroke-width:2px")

    return "\n".join(lines)


def write_lineage_mermaid_file(
    path: Path | str,
    winners: Iterable[Winner],
    *,
    highlight_top_rank: int = 0,
    title: str | None = None,
) -> None:
    """render_lineage_mermaid の結果を ``path`` に書く (.mmd 拡張子推奨)."""
    md = render_lineage_mermaid(winners, highlight_top_rank=highlight_top_rank, title=title)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(md, encoding="utf-8")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _sanitize_id(individual_id: str) -> str:
    """Mermaid node id 用に英数字/_ のみへ変換 (コロン・ハイフン等が構文を壊すため).

    ``[:10]`` 切り詰めはせず full id を sanitize し、prefix 共通時の衝突を避ける (B-RES-1).
    """
    return re.sub(r"[^A-Za-z0-9_]", "_", individual_id)


def _node_id(generation: int, individual_id: str) -> str:
    # Mermaid node id は alpha-num 開始必須. sanitize で安全化.
    return f"g{generation}_{_sanitize_id(individual_id)}"


def _ghost_node_id(generation: int, individual_id: str) -> str:
    return f"gh{generation}_{_sanitize_id(individual_id)}"


__all__ = [
    "Winner",
    "load_winners_jsonl",
    "render_lineage_mermaid",
    "write_lineage_mermaid_file",
    "write_winners_jsonl",
]
