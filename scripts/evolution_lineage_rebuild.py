#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Evolution-run lineage **rebuild** — resolve parent chains across all artifacts.

問題 (observability gap, 2026-05-26)
------------------------------------
lldarwin の系統可視化が「全部 ``?``」に化ける。原因は parent_ids の参照先が同一
snapshot ファイル内に居ないため:

* ``snapshot_gen_*.json`` は **5 世代ごと** に **全 24 個体** を保存するが、parent_ids
  は直前世代 (snapshot 非対象) の個体を指すことが多い。
* ``winners.jsonl`` は **全世代** を記録するが **上位 3 個体のみ** (parent も top-3 だけ)。

どちらか一方だけでは founder まで辿れない。本スクリプトは **両ソースを統合**して
既知個体の宇宙 (universe) を最大化し、解決可能な親リンクを最大限つなぎ、辿れない
リンクは ``?`` ではなく ``(lost@genN)`` (記録欠落) として明示する (honest disclosure)。

復元できるもの / できないもの
-----------------------------
* **解決可能**: winners と snapshot に居る個体同士のリンク。founder へ到達する系統。
* **欠落**: gen 1-4 等 (snapshot 非対象 & top-3 外) の中間個体。これは元データに
  存在しない — 捏造せず ``lost`` として残す。founder 帰属は ``founder_lineage.jsonl``
  (各世代の root-founder 分布を正確に記録) を **補完真値** として併用する。

island (島) 情報
----------------
個体 record に island/deme フィールドがあれば island 別に色分けできる形で返す
(``--by island``)。無ければ founder 別 (``--by founder``, 既定)。

使い方::

    py -3.11 scripts/evolution_lineage_rebuild.py out/lldarwin_12h_realpressure_2026_05_26
    py -3.11 scripts/evolution_lineage_rebuild.py <run_dir> --json out.json --mmd out.mmd
    py -3.11 scripts/evolution_lineage_rebuild.py <run_dir> --by island
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


def _ensure_utf8_stdout() -> None:
    """Force stdout to UTF-8 (Windows cp932 mojibake guard).

    See memory ``feedback_cli_utf8_stdout_pattern``.
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):  # pragma: no cover
        pass


# island/deme をどのフィールドから読むか (record に存在すれば使う)。
_ISLAND_KEYS = ("island", "island_id", "deme", "deme_id", "subpopulation")


@dataclass
class IndividualNode:
    """復元された 1 個体ノード."""

    individual_id: str
    parent_ids: list[str] = field(default_factory=list)
    birth_generation: int | None = None
    island: str | None = None
    #: この個体が観測された世代 (winners/snapshot で見えた世代の集合; 昇順)。
    seen_generations: list[int] = field(default_factory=list)
    #: snapshot から読めた最新 score (なければ None)。
    score: float | None = None

    @property
    def is_founder(self) -> bool:
        return self.individual_id.startswith("founder:")


# --------------------------------------------------------------------------
# loaders
# --------------------------------------------------------------------------
def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _read_island(record: dict) -> str | None:
    for k in _ISLAND_KEYS:
        if k in record and record[k] is not None:
            return str(record[k])
    return None


def build_universe(run_dir: Path) -> dict[str, IndividualNode]:
    """winners.jsonl + snapshot_gen_*.json を統合し、既知個体の宇宙を構築する.

    両ソースに共通する個体は **snapshot 側を優先** (genome/score/island を持つため)。
    seen_generations は両ソースの和集合。
    """
    nodes: dict[str, IndividualNode] = {}

    def _ensure(iid: str) -> IndividualNode:
        node = nodes.get(iid)
        if node is None:
            node = IndividualNode(individual_id=iid)
            nodes[iid] = node
        return node

    # 1) winners.jsonl (全世代, top-3): parent_ids + seen-generation を最大網羅。
    for r in _read_jsonl(run_dir / "winners.jsonl"):
        iid = r.get("individual_id")
        if not iid:
            continue
        node = _ensure(iid)
        gen = r.get("generation")
        if isinstance(gen, int) and gen not in node.seen_generations:
            node.seen_generations.append(gen)
        if not node.parent_ids and r.get("parent_ids"):
            node.parent_ids = list(r["parent_ids"])
        if node.score is None and isinstance(r.get("score"), (int, float)):
            node.score = float(r["score"])
        island = _read_island(r)
        if island and node.island is None:
            node.island = island

    # 2) snapshots (5 世代ごと, 全 24): genome/score/birth/island を補完 (優先)。
    for sf in sorted(glob.glob(str(run_dir / "snapshot_gen_*.json"))):
        try:
            data = json.loads(Path(sf).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        gen = data.get("generation")
        for ind in data.get("individuals", []):
            iid = ind.get("individual_id")
            if not iid:
                continue
            node = _ensure(iid)
            if isinstance(gen, int) and gen not in node.seen_generations:
                node.seen_generations.append(gen)
            # snapshot の parent_ids を優先 (より権威的)。
            if ind.get("parent_ids"):
                node.parent_ids = list(ind["parent_ids"])
            if ind.get("birth_generation") is not None:
                node.birth_generation = ind["birth_generation"]
            island = _read_island(ind)
            if island:
                node.island = island
            fit = ind.get("fitness") or {}
            if isinstance(fit.get("score"), (int, float)):
                node.score = float(fit["score"])

    for node in nodes.values():
        node.seen_generations.sort()
        # birth_generation 未知なら、観測最小世代を保険として使う。
        if node.birth_generation is None and node.seen_generations:
            node.birth_generation = node.seen_generations[0]
    return nodes


def load_founder_dominance(run_dir: Path) -> list[dict]:
    """founder_lineage.jsonl: 各世代の root-founder 分布 (正確な補完真値)."""
    return _read_jsonl(run_dir / "founder_lineage.jsonl")


# --------------------------------------------------------------------------
# lineage resolution
# --------------------------------------------------------------------------
LOST = object()  # sentinel: 記録欠落 (founder でも生存個体でもない)


def trace_to_founder(
    iid: str, nodes: dict[str, IndividualNode], *, max_hops: int = 4096
) -> tuple[list[str], str]:
    """``iid`` から **第一親** を辿り、founder か記録欠落 (lost) まで遡る.

    Returns
    -------
    (chain, terminal)
        ``chain`` は新しい→古い順 (``iid`` が先頭)。``terminal`` は
        ``"founder:<id>"`` / ``"lost@gen<N>"`` / ``"cycle"`` のいずれか。

    親が universe に居なければ ``lost`` として打ち切る (``?`` ではない)。
    """
    chain: list[str] = []
    seen: set[str] = set()
    cur: str | None = iid
    hops = 0
    while cur is not None and hops < max_hops:
        if cur in seen:
            return chain, "cycle"
        seen.add(cur)
        chain.append(cur)
        node = nodes.get(cur)
        if node is None:
            # この id 自体が宇宙に居ない → 直前で打ち切り済み (起こりにくい)。
            return chain, "lost@gen?"
        if node.is_founder:
            return chain, node.individual_id
        if not node.parent_ids:
            # 親無し & founder でない = gen0 random seed (founder_lineage では (random))。
            gen = node.birth_generation if node.birth_generation is not None else "?"
            return chain, f"origin@gen{gen}" if gen == 0 else f"lost@gen{gen}"
        # 第一親を採用 (crossover の主系統)。
        parent = node.parent_ids[0]
        if parent not in nodes:
            gen = node.birth_generation if node.birth_generation is not None else "?"
            return chain, f"lost@gen{gen}"
        cur = parent
        hops += 1
    return chain, "lost@gen?"


def attribute_founders(
    nodes: dict[str, IndividualNode],
) -> dict[str, str]:
    """各個体を root-founder (または lost/origin) に帰属させる.

    第一親チェーンで辿れた終端を採用。辿れない場合は終端ラベル (lost@..) を返す。
    """
    result: dict[str, str] = {}
    for iid in nodes:
        _, terminal = trace_to_founder(iid, nodes)
        result[iid] = terminal
    return result


@dataclass
class RebuildStats:
    total_individuals: int
    founders: list[str]
    resolved_to_founder: int
    resolved_to_origin: int
    lost: int
    parent_refs: int
    parent_refs_resolvable: int
    islands: list[str]

    def as_dict(self) -> dict:
        return {
            "total_individuals": self.total_individuals,
            "founders": self.founders,
            "resolved_to_founder": self.resolved_to_founder,
            "resolved_to_origin": self.resolved_to_origin,
            "lost": self.lost,
            "parent_refs": self.parent_refs,
            "parent_refs_resolvable": self.parent_refs_resolvable,
            "parent_resolution_rate": (
                round(self.parent_refs_resolvable / self.parent_refs, 3)
                if self.parent_refs
                else None
            ),
            "islands": self.islands,
        }


def compute_stats(
    nodes: dict[str, IndividualNode], attribution: dict[str, str]
) -> RebuildStats:
    founders = sorted(n.individual_id for n in nodes.values() if n.is_founder)
    resolved_f = sum(1 for v in attribution.values() if v.startswith("founder:"))
    resolved_o = sum(1 for v in attribution.values() if v.startswith("origin@"))
    lost = sum(
        1 for v in attribution.values() if v.startswith("lost") or v == "cycle"
    )
    refs = 0
    refs_ok = 0
    for n in nodes.values():
        for p in n.parent_ids:
            refs += 1
            if p in nodes:
                refs_ok += 1
    islands = sorted({n.island for n in nodes.values() if n.island})
    return RebuildStats(
        total_individuals=len(nodes),
        founders=founders,
        resolved_to_founder=resolved_f,
        resolved_to_origin=resolved_o,
        lost=lost,
        parent_refs=refs,
        parent_refs_resolvable=refs_ok,
        islands=islands,
    )


# --------------------------------------------------------------------------
# output: JSON + Mermaid (champion bloodline, fully resolved)
# --------------------------------------------------------------------------
def champion_id(nodes: dict[str, IndividualNode], run_dir: Path) -> str | None:
    """最終世代の最良個体 (rank 0) を winners.jsonl から特定."""
    winners = _read_jsonl(run_dir / "winners.jsonl")
    if not winners:
        # snapshot fallback: 最大世代の最良 score。
        best = None
        for n in nodes.values():
            if n.seen_generations and n.score is not None:
                if best is None or (max(n.seen_generations), n.score) > (
                    max(best.seen_generations), best.score or -1
                ):
                    best = n
        return best.individual_id if best else None
    last_gen = max(int(w["generation"]) for w in winners)
    champs = [w for w in winners if int(w["generation"]) == last_gen]
    champ = min(champs, key=lambda w: w.get("rank", 0))
    return champ["individual_id"]


def _nid(token: str) -> str:
    return "n_" + re.sub(r"[^A-Za-z0-9_]", "_", token)


def champion_bloodline_mmd(
    nodes: dict[str, IndividualNode], run_dir: Path, depth: int
) -> str:
    cid = champion_id(nodes, run_dir)
    if cid is None:
        return 'graph TD\n    empty["no individuals recorded"]\n'
    chain, terminal = trace_to_founder(cid, nodes)
    chain_old_to_new = list(reversed(chain))  # founder/lost → champion
    truncated = len(chain_old_to_new) > depth
    shown = chain_old_to_new[-depth:] if truncated else chain_old_to_new

    lines = [
        "%% champion bloodline (REBUILT: winners.jsonl + snapshots merged)",
        f"%% champion={cid[:12]}  terminal={terminal}  "
        f"resolved_depth={len(chain_old_to_new)} hops"
        + (f" (showing last {len(shown)})" if truncated else ""),
        "graph TD",
    ]
    # 終端ラベル (founder / lost / origin) を先頭ノードとして明示。
    term_node = _nid(terminal)
    if terminal.startswith("founder:"):
        term_lbl = "founder<br/>" + terminal[len("founder:"):]
    elif terminal.startswith("origin@"):
        term_lbl = "random seed<br/>" + terminal
    else:
        term_lbl = "lost record<br/>" + terminal
    lines.append(f'    {term_node}["{term_lbl}"]')
    if truncated:
        lines.append(f'    earlier["… {len(chain_old_to_new) - len(shown)} earlier hops …"]')

    prev = term_node if not truncated else "earlier"
    for tok in shown:
        node = nodes.get(tok)
        gen = node.birth_generation if node else None
        score = node.score if node else None
        sc = f"<br/>score={score:.3f}" if score is not None else ""
        gtxt = f"gen {gen} " if gen is not None else ""
        if node and node.is_founder:
            lbl = "founder<br/>" + tok[len("founder:"):]
        else:
            lbl = f"{gtxt}{tok[:8]}{sc}"
        lines.append(f'    {_nid(tok)}["{lbl}"]')
    # edges: terminal -> ... -> champion
    seq = ([term_node] if not truncated else ["earlier"]) + [_nid(t) for t in shown]
    for a, b in zip(seq, seq[1:]):
        lines.append(f"    {a} --> {b}")
    return "\n".join(lines) + "\n"


def build_rebuild_payload(run_dir: Path, *, by: str) -> dict:
    nodes = build_universe(run_dir)
    attribution = attribute_founders(nodes)
    stats = compute_stats(nodes, attribution)
    dominance = load_founder_dominance(run_dir)

    # by island/founder の grouping (個体 → group key)。
    grouping: dict[str, str] = {}
    for iid, node in nodes.items():
        if by == "island" and node.island:
            grouping[iid] = node.island
        else:
            grouping[iid] = attribution[iid]

    individuals = []
    for iid in sorted(nodes):
        node = nodes[iid]
        individuals.append(
            {
                "individual_id": iid,
                "parent_ids": node.parent_ids,
                "birth_generation": node.birth_generation,
                "seen_generations": node.seen_generations,
                "island": node.island,
                "score": node.score,
                "root": attribution[iid],
                "group": grouping[iid],
                "is_founder": node.is_founder,
            }
        )
    return {
        "schema": "lineage_rebuild/v1",
        "run_dir": str(run_dir),
        "grouping_by": by,
        "stats": stats.as_dict(),
        "founder_dominance_available": bool(dominance),
        "individuals": individuals,
    }


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    ap = argparse.ArgumentParser(
        prog="evolution_lineage_rebuild",
        description="rebuild lineage by merging winners.jsonl + snapshots",
    )
    ap.add_argument(
        "run_dir",
        nargs="?",
        default="out/lldarwin_12h_realpressure_2026_05_26",
        help="run output dir (既定: 12h real-pressure run)",
    )
    ap.add_argument("--by", choices=("founder", "island"), default="founder",
                    help="grouping 軸 (island 情報が無ければ founder にフォールバック)")
    ap.add_argument("--json", type=Path, default=None,
                    help="復元結果 JSON 出力先 (既定: <run_dir>/lineage_rebuild.json)")
    ap.add_argument("--mmd", type=Path, default=None,
                    help="champion bloodline Mermaid 出力先 (既定: <run_dir>/champion_lineage_rebuilt.mmd)")
    ap.add_argument("--champ-depth", type=int, default=40,
                    help="champion bloodline の最大ホップ数")
    ap.add_argument("--quiet", action="store_true", help="サマリ標準出力を抑制")
    args = ap.parse_args(argv)

    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        print(f"[ERROR] run dir not found: {run_dir}", file=sys.stderr)
        return 2

    payload = build_rebuild_payload(run_dir, by=args.by)
    nodes = build_universe(run_dir)

    out_json = args.json or run_dir / "lineage_rebuild.json"
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    mmd = champion_bloodline_mmd(nodes, run_dir, args.champ_depth)
    out_mmd = args.mmd or run_dir / "champion_lineage_rebuilt.mmd"
    out_mmd.write_text(mmd, encoding="utf-8")

    if not args.quiet:
        s = payload["stats"]
        print(f"== lineage rebuild: {run_dir} ==")
        print(f"  individuals (winners ∪ snapshots): {s['total_individuals']}")
        print(f"  founders: {len(s['founders'])} -> {', '.join(f[len('founder:'):] for f in s['founders'])}")
        print(f"  parent refs: {s['parent_refs_resolvable']}/{s['parent_refs']} resolvable "
              f"(rate={s['parent_resolution_rate']})")
        print(f"  attribution: founder={s['resolved_to_founder']}  "
              f"origin(random-seed)={s['resolved_to_origin']}  lost(record gap)={s['lost']}")
        if s["islands"]:
            print(f"  islands: {', '.join(s['islands'])}")
        else:
            print("  islands: none recorded -> grouped by founder")
        cid = champion_id(nodes, run_dir)
        if cid:
            chain, terminal = trace_to_founder(cid, nodes)
            print(f"  champion {cid[:12]} -> {terminal}  ({len(chain)} hops resolved, no '?')")
        print(f"  wrote {out_json}")
        print(f"  wrote {out_mmd}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
