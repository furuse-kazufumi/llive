#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Evolution-run lineage views (P2): founder-persona dominance + champion bloodline.

Reads a persona-evolution run dir and produces two complementary lineage views,
both self-contained (no external deps, pure stdlib):

1. **persona dominance stream** (``persona_dominance.svg``): a stacked-area SMIL
   animation showing, per generation, what fraction of the *full population*
   descends from each founder persona (vs. the ``(random)`` gen-0 padding).
   Reveals takeovers/extinctions at a glance — e.g. "all founder lineages die
   out and the random-seeded bloodline dominates by gen N".

   Data source: ``founder_lineage.jsonl`` (emitted by ``run_persona_evolution``),
   which records each generation's exact full-population root-founder distribution.
   This is exact provenance — unlike post-hoc tracing through ``lineage.mmd``,
   which dead-ends because winners.jsonl only keeps the top-3 per generation.

2. **champion bloodline** (``champion_lineage.mmd``): the final best individual's
   first-parent chain, capped to the most recent ``--champ-depth`` hops so it is
   *actually renderable* (the full ``lineage.mmd`` is thousands of nodes). Render
   with ``mmdc`` / raptor ``/diagram``.

HONEST DISCLOSURE: the proxy/real-LLM label from ``run_manifest.json`` is baked
into the SVG. A proxy run's takeover stream shows the *mechanism* works, not that
evolution found anything meaningful (feedback_benchmark_honest_disclosure). The
``(random)`` bucket is shown explicitly so a founder-extinction is never hidden.
Visualization plan: fullsense/docs/research/evolution_visualization_plan_2026_05_25.md.

    py -3.11 scripts/evolution_lineage_viz.py out/evo_run_2026_05_25
    py -3.11 scripts/evolution_lineage_viz.py <run_dir> --window 9 --champ-depth 24
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

RANDOM_BUCKET = "(random)"

# ---- node-id token extraction (champion bloodline only) -----------------------
_NODE_PREFIX = re.compile(r"^gh?\d+_(.+)$")
_EDGE = re.compile(r"^\s*(\S+)\s*-->\s*(\S+)\s*$")
_NODE_DEF = re.compile(r'^\s*(\S+?)\["(.*?)"\]\s*$')
_SCORE = re.compile(r"score=([0-9.]+)")
_GEN = re.compile(r"gen\s+(\d+)")


def _token(node_id: str) -> str:
    m = _NODE_PREFIX.match(node_id)
    return m.group(1) if m else node_id


def _winner_token(individual_id: str) -> str:
    if individual_id.startswith("founder:"):
        return "founder_" + individual_id[len("founder:"):].replace("-", "_")
    return individual_id


# ---- loaders ------------------------------------------------------------------
def load_founder_lineage(run_dir: Path) -> list[dict]:
    path = run_dir / "founder_lineage.jsonl"
    if not path.exists():
        raise FileNotFoundError(
            f"no founder_lineage.jsonl in {run_dir} — re-run the evolution "
            "(run_persona_evolution now emits it for the dominance stream)."
        )
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    rows.sort(key=lambda r: r.get("generation", 0))
    return rows


def load_manifest(run_dir: Path) -> dict:
    p = run_dir / "run_manifest.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def honest_label(manifest: dict, n_gens: int, pop: int) -> tuple[str, bool]:
    cfg = manifest.get("config", manifest)
    is_proxy = str(cfg.get("fitness", "proxy")) != "llm"
    seed = cfg.get("seed", "?")
    tag = "PROXY fitness — NOT real LLM eval" if is_proxy else "real on-prem LLM fitness"
    return f"{tag}  ·  full-population bloodline share  ·  gens={n_gens}  pop={pop}  seed={seed}", is_proxy


def shares_from_lineage(rows: list[dict], founders: list[str]) -> tuple[list[int], dict[str, list[float]]]:
    """generations, {origin -> [share per gen]}. Origins = founders + (random)."""
    origins = [f for f in founders] + [RANDOM_BUCKET]
    # include any unexpected origins that appear in data
    for r in rows:
        for k in r.get("founder_counts", {}):
            if k not in origins:
                origins.append(k)
    gens = [int(r["generation"]) for r in rows]
    shares: dict[str, list[float]] = {o: [] for o in origins}
    for r in rows:
        counts = r.get("founder_counts", {})
        total = sum(counts.values()) or 1
        for o in origins:
            shares[o].append(counts.get(o, 0) / total)
    return gens, shares


def smooth(series: list[float], window: int) -> list[float]:
    if window <= 1:
        return series[:]
    out, half = [], window // 2
    for i in range(len(series)):
        seg = series[max(0, i - half):min(len(series), i + half + 1)]
        out.append(sum(seg) / len(seg))
    return out


# distinct palette for founders; (random) gets a muted gray so extinction reads clearly
_PALETTE = [
    "#60a5fa", "#f472b6", "#34d399", "#fbbf24", "#a78bfa", "#fb7185",
    "#22d3ee", "#a3e635", "#f59e0b", "#c084fc", "#2dd4bf", "#f87171",
]
_RANDOM_COLOR = "#475569"


def _color(origin: str, founders: list[str]) -> str:
    if origin == RANDOM_BUCKET:
        return _RANDOM_COLOR
    try:
        return _PALETTE[founders.index(origin) % len(_PALETTE)]
    except ValueError:
        return "#94a3b8"


def render_dominance_svg(
    gens: list[int], shares: dict[str, list[float]], founders: list[str],
    label: str, is_proxy: bool, window: int,
) -> str:
    W, H = 940, 540
    ML, MR, MT, MB = 70, 170, 84, 56
    x0, x1 = ML, W - MR
    y0, y1 = MT, H - MB
    gmax = max(gens) if gens else 1

    def sx(g: float) -> float:
        return x0 + (x1 - x0) * (g / (gmax or 1))

    def sy(v: float) -> float:
        return y1 - (y1 - y0) * v

    # stack order: founders first (bottom), (random) on top so its takeover is visible
    origins = [o for o in shares if o != RANDOM_BUCKET] + (
        [RANDOM_BUCKET] if RANDOM_BUCKET in shares else []
    )
    sm = {o: smooth(shares[o], window) for o in origins}

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="ui-sans-serif,Segoe UI,sans-serif">'
    )
    parts.append(f'<rect width="{W}" height="{H}" fill="#0b1020"/>')
    accent = "#c2410c" if is_proxy else "#15803d"
    parts.append(f'<text x="{ML}" y="32" fill="#e5e7eb" font-size="20" font-weight="700">'
                 f'llive persona evolution — founder-lineage dominance</text>')
    parts.append(f'<text x="{ML}" y="52" fill="{accent}" font-size="13" font-weight="600">{label}</text>')
    parts.append(f'<text x="{ML}" y="{MT-10}" fill="#9ca3af" font-size="12">'
                 f'share of population by root-founder bloodline  ·  rolling window={window}</text>')

    for v in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = sy(v)
        parts.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="#1f2937" stroke-width="1"/>')
        parts.append(f'<text x="{x0-8}" y="{y+4:.1f}" fill="#6b7280" font-size="10" text-anchor="end">{int(v*100)}%</text>')

    parts.append(
        # 静的フォールバック: authored width=full で SMIL 非実行環境でも見える
        # (animation as enhancement, [[feedback_animated_svg_static_fallback]])。
        f'<clipPath id="revealdom"><rect x="{x0}" y="0" width="{x1-x0:.0f}" height="{H}">'
        f'<animate attributeName="width" from="0" to="{x1-x0:.0f}" dur="3.4s" fill="freeze"/>'
        f'</rect></clipPath>'
    )

    parts.append('<g clip-path="url(#revealdom)">')
    cum_prev = [0.0] * len(gens)
    for o in origins:
        cum_cur = [cum_prev[j] + sm[o][j] for j in range(len(gens))]
        top = " ".join(f"{sx(g):.1f},{sy(cum_cur[j]):.1f}" for j, g in enumerate(gens))
        bot = " ".join(f"{sx(g):.1f},{sy(cum_prev[j]):.1f}" for j, g in reversed(list(enumerate(gens))))
        parts.append(f'<polygon points="{top} {bot}" fill="{_color(o, founders)}" fill-opacity="0.85"/>')
        cum_prev = cum_cur
    parts.append('</g>')

    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        g = round(gmax * frac)
        parts.append(f'<text x="{sx(g):.1f}" y="{y1+18:.1f}" fill="#6b7280" font-size="10" text-anchor="middle">{g}</text>')
    parts.append(f'<text x="{(x0+x1)/2:.0f}" y="{y1+40:.0f}" fill="#9ca3af" font-size="12" text-anchor="middle">generation</text>')

    # legend sorted by final share
    final = {o: (sm[o][-1] if sm[o] else 0.0) for o in origins}
    order = sorted(origins, key=lambda o: final[o], reverse=True)
    lx, ly = x1 + 16, MT
    for k, o in enumerate(order):
        yy = ly + k * 19
        parts.append(f'<rect x="{lx}" y="{yy-9}" width="12" height="12" fill="{_color(o, founders)}" fill-opacity="0.85"/>')
        name = o if len(o) <= 16 else o[:15] + "…"
        parts.append(f'<text x="{lx+18}" y="{yy+1}" fill="#cbd5e1" font-size="11">{name} {final[o]*100:.0f}%</text>')

    parts.append('</svg>')
    return "\n".join(parts)


# ---- champion bloodline (compact, renderable) --------------------------------
def parse_lineage(run_dir: Path) -> tuple[dict[str, list[str]], dict[str, dict]]:
    children: dict[str, list[str]] = {}
    nodes: dict[str, dict] = {}
    path = run_dir / "lineage.mmd"
    if not path.exists():
        return children, nodes
    for raw in path.read_text(encoding="utf-8").splitlines():
        em = _EDGE.match(raw)
        if em:
            p_tok, c_tok = _token(em.group(1)), _token(em.group(2))
            children.setdefault(c_tok, [])
            if p_tok not in children[c_tok]:
                children[c_tok].append(p_tok)
            continue
        nm = _NODE_DEF.match(raw)
        if nm:
            tok, label = _token(nm.group(1)), nm.group(2)
            sm, gm = _SCORE.search(label), _GEN.search(label)
            nodes[tok] = {
                "gen": int(gm.group(1)) if gm else None,
                "score": float(sm.group(1)) if sm else None,
            }
    return children, nodes


def load_winners(run_dir: Path) -> list[dict]:
    rows = []
    path = run_dir / "winners.jsonl"
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def champion_bloodline_mmd(run_dir: Path, depth: int) -> str:
    children, nodes = parse_lineage(run_dir)
    winners = load_winners(run_dir)
    if not winners:
        return "graph TD\n    empty[\"no winners recorded\"]\n"
    last_gen = max(int(w["generation"]) for w in winners)
    champ = min((w for w in winners if int(w["generation"]) == last_gen),
                key=lambda w: w.get("rank", 0))

    chain: list[str] = []
    tok, seen = _winner_token(champ["individual_id"]), set()
    while tok and tok not in seen:
        seen.add(tok)
        chain.append(tok)
        if tok.startswith("founder_"):
            break
        parents = children.get(tok) or []
        tok = parents[0] if parents else None
    total_depth = len(chain)
    chain.reverse()  # oldest → champion
    truncated = total_depth > depth
    shown = chain[-depth:] if truncated else chain

    lines = [
        f"%% champion bloodline (final best individual → first-parent chain)",
        f"%% total recorded depth={total_depth} hops; showing last {len(shown)}"
        + (" (truncated)" if truncated else ""),
        "graph TD",
    ]

    def nid(t: str) -> str:
        return re.sub(r"[^A-Za-z0-9_]", "_", t)

    if truncated:
        lines.append(f'    earlier["… {total_depth - len(shown)} earlier generations …"]')
        lines.append(f"    earlier --> {nid(shown[0])}")
    for t in shown:
        meta = nodes.get(t, {})
        gen, score = meta.get("gen"), meta.get("score")
        if t.startswith("founder_"):
            lbl = "founder<br/>" + t[len("founder_"):]
        else:
            sc = f"<br/>score={score:.3f}" if score is not None else ""
            gtxt = f"gen {gen} " if gen is not None else ""
            lbl = f"{gtxt}{t[:8]}{sc}"
        lines.append(f'    {nid(t)}["{lbl}"]')
    for a, b in zip(shown, shown[1:]):
        lines.append(f"    {nid(a)} --> {nid(b)}")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="evolution lineage views (P2)")
    ap.add_argument("run_dir", help="run output dir (with founder_lineage.jsonl)")
    ap.add_argument("--window", type=int, default=9, help="rolling window for dominance smoothing")
    ap.add_argument("--champ-depth", type=int, default=24, help="max hops shown in champion bloodline")
    ap.add_argument("--out-svg", default=None)
    ap.add_argument("--out-mmd", default=None)
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    rows = load_founder_lineage(run_dir)
    manifest = load_manifest(run_dir)
    founders = [str(f) for f in (manifest.get("personas") or manifest.get("founder_ids") or [])]
    pop = rows[0]["n_individuals"] if rows else "?"

    gens, shares = shares_from_lineage(rows, founders)
    label, is_proxy = honest_label(manifest, len(gens), pop)
    svg = render_dominance_svg(gens, shares, founders, label, is_proxy, args.window)
    out_svg = Path(args.out_svg) if args.out_svg else run_dir / "persona_dominance.svg"
    out_svg.write_text(svg, encoding="utf-8")

    mmd = champion_bloodline_mmd(run_dir, args.champ_depth)
    out_mmd = Path(args.out_mmd) if args.out_mmd else run_dir / "champion_lineage.mmd"
    out_mmd.write_text(mmd, encoding="utf-8")

    print(f"wrote {out_svg}  ({len(svg)} bytes)")
    print(f"wrote {out_mmd}  ({len(mmd)} bytes)")
    # honest readout of the final-generation origin mix
    final_counts = rows[-1]["founder_counts"] if rows else {}
    tot = sum(final_counts.values()) or 1
    top = sorted(final_counts.items(), key=lambda kv: kv[1], reverse=True)[:4]
    print(f"final gen ({gens[-1] if gens else '?'}) origin mix: "
          + ", ".join(f"{k}={v/tot*100:.0f}%" for k, v in top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
