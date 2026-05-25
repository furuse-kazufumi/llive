#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Evolution-run lineage views (P2): founder-persona dominance + champion bloodline.

Reads a persona-evolution run dir and produces two complementary lineage views,
both self-contained (no external deps, pure stdlib):

1. **persona dominance stream** (``persona_dominance.svg``): a stacked-area SMIL
   animation showing, per generation, which *founder persona lineage* the
   surviving winners descend from. Reveals "von_neumann's bloodline takes over"
   style takeovers at a glance.

2. **champion lineage** (``champion_lineage.mmd``): the final best individual's
   bloodline traced back to its founder (first-parent chain). A *compact*,
   actually-renderable Mermaid graph — unlike the full ``lineage.mmd`` (227 KB,
   thousands of nodes) which no renderer handles legibly. Render with
   ``mmdc`` / raptor ``/diagram``.

Founder tracing uses the full child->parent edge map parsed from ``lineage.mmd``
(which includes non-winner "ghost" parents), so winners whose parents never won
are still resolved to a founder.

HONEST DISCLOSURE: the proxy/real-LLM label from ``run_manifest.json`` is baked
into the SVG. A proxy run's clean takeover stream shows the *mechanism* works,
not that evolution found anything meaningful (feedback_benchmark_honest_disclosure).
Visualization plan: fullsense/docs/research/evolution_visualization_plan_2026_05_25.md.

    py -3.11 scripts/evolution_lineage_viz.py out/evo_run_2026_05_25
    py -3.11 scripts/evolution_lineage_viz.py <run_dir> --window 9
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ---- node-id token extraction -------------------------------------------------
# lineage.mmd node ids look like  g<gen>_<token>  or  gh<gen>_<token>
#   token = "founder_<persona_underscored>"  or a 12-char hex individual id
_NODE_PREFIX = re.compile(r"^gh?\d+_(.+)$")
_EDGE = re.compile(r"^\s*(\S+)\s*-->\s*(\S+)\s*$")
_NODE_DEF = re.compile(r'^\s*(\S+?)\["(.*?)"\]\s*$')
_SCORE = re.compile(r"score=([0-9.]+)")
_GEN = re.compile(r"gen\s+(\d+)")


def _token(node_id: str) -> str:
    """Strip the g<gen>_/gh<gen>_ prefix → canonical individual token."""
    m = _NODE_PREFIX.match(node_id)
    return m.group(1) if m else node_id


def _winner_token(individual_id: str) -> str:
    """Normalise a winners.jsonl id to the same token space as lineage nodes.

    ``founder:von-neumann`` -> ``founder_von_neumann`` ; hex ids pass through.
    """
    if individual_id.startswith("founder:"):
        return "founder_" + individual_id[len("founder:"):].replace("-", "_")
    return individual_id


def _persona_of(token: str) -> str | None:
    """Founder token -> persona display name, else None (not a founder)."""
    if token.startswith("founder_"):
        return token[len("founder_"):]
    return None


def parse_lineage(run_dir: Path) -> tuple[dict[str, list[str]], dict[str, dict]]:
    """Return (child_token -> [parent_token,...], token -> {gen, score, short})."""
    children: dict[str, list[str]] = {}
    nodes: dict[str, dict] = {}
    path = run_dir / "lineage.mmd"
    if not path.exists():
        raise FileNotFoundError(f"no lineage.mmd in {run_dir}")
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
            tok = _token(nm.group(1))
            label = nm.group(2)
            sm, gm = _SCORE.search(label), _GEN.search(label)
            nodes[tok] = {
                "gen": int(gm.group(1)) if gm else None,
                "score": float(sm.group(1)) if sm else None,
                "short": tok[:8] if not tok.startswith("founder_") else tok,
            }
    return children, nodes


def founder_of(token: str, children: dict[str, list[str]], memo: dict[str, str | None]) -> str | None:
    """Trace a token to its founder persona via first-parent chain (memoised)."""
    if token in memo:
        return memo[token]
    persona = _persona_of(token)
    if persona is not None:
        memo[token] = persona
        return persona
    memo[token] = None  # guard against cycles (none expected in a gen tree)
    parents = children.get(token)
    result: str | None = None
    if parents:
        for p in parents:  # prefer first parent that resolves to a founder
            r = founder_of(p, children, memo)
            if r is not None:
                result = r
                break
    memo[token] = result
    return result


def load_winners(run_dir: Path) -> list[dict]:
    rows = []
    path = run_dir / "winners.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"no winners.jsonl in {run_dir}")
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def load_manifest(run_dir: Path) -> dict:
    p = run_dir / "run_manifest.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def honest_label(manifest: dict, n_gens: int) -> tuple[str, bool]:
    cfg = manifest.get("config", manifest)
    is_proxy = str(cfg.get("fitness", "proxy")) != "llm"
    seed = cfg.get("seed", "?")
    pop = cfg.get("population", "?")
    tag = "PROXY fitness — NOT real LLM eval" if is_proxy else "real on-prem LLM fitness"
    return f"{tag}  ·  winner-lineage share  ·  gens={n_gens}  pop={pop}  seed={seed}", is_proxy


# ---- per-generation founder shares -------------------------------------------
def founder_shares(
    winners: list[dict], children: dict[str, list[str]], founders: list[str]
) -> tuple[list[int], dict[str, list[float]], int]:
    """generations, {persona -> [share per gen]}, unresolved_count."""
    memo: dict[str, str | None] = {}
    by_gen: dict[int, list[str | None]] = {}
    unresolved = 0
    for w in winners:
        g = int(w["generation"])
        f = founder_of(_winner_token(w["individual_id"]), children, memo)
        if f is None:
            unresolved += 1
        by_gen.setdefault(g, []).append(f)
    gens = sorted(by_gen)
    shares: dict[str, list[float]] = {p: [] for p in founders}
    for g in gens:
        members = by_gen[g]
        n = len(members) or 1
        for p in founders:
            shares[p].append(members.count(p) / n)
    return gens, shares, unresolved


def smooth(series: list[float], window: int) -> list[float]:
    if window <= 1:
        return series[:]
    out = []
    half = window // 2
    for i in range(len(series)):
        lo, hi = max(0, i - half), min(len(series), i + half + 1)
        seg = series[lo:hi]
        out.append(sum(seg) / len(seg))
    return out


# distinct, color-blind-ish palette for up to ~12 founders
_PALETTE = [
    "#60a5fa", "#f472b6", "#34d399", "#fbbf24", "#a78bfa", "#fb7185",
    "#22d3ee", "#a3e635", "#f59e0b", "#c084fc", "#2dd4bf", "#f87171",
]


def render_dominance_svg(
    gens: list[int], shares: dict[str, list[float]], label: str, is_proxy: bool, window: int
) -> str:
    W, H = 920, 520
    ML, MR, MT, MB = 70, 150, 80, 56
    x0, x1 = ML, W - MR
    y0, y1 = MT, H - MB
    gmax = max(gens) if gens else 1

    def sx(g: float) -> float:
        return x0 + (x1 - x0) * (g / (gmax or 1))

    def sy(v: float) -> float:  # v in [0,1] cumulative share
        return y1 - (y1 - y0) * v

    founders = [p for p in shares]
    sm = {p: smooth(shares[p], window) for p in founders}

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
                 f'share of winners by founder bloodline (rolling window={window})</text>')

    # gridlines 0/.25/.5/.75/1
    for v in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = sy(v)
        parts.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="#1f2937" stroke-width="1"/>')
        parts.append(f'<text x="{x0-8}" y="{y+4:.1f}" fill="#6b7280" font-size="10" text-anchor="end">{int(v*100)}%</text>')

    # reveal clip (SMIL): rect grows left->right to "play" the run
    parts.append(
        f'<clipPath id="revealdom"><rect x="{x0}" y="0" width="0" height="{H}">'
        f'<animate attributeName="width" from="0" to="{x1-x0:.0f}" dur="3.4s" fill="freeze"/>'
        f'</rect></clipPath>'
    )

    # stacked areas (cumulative)
    parts.append('<g clip-path="url(#revealdom)">')
    cum_prev = [0.0] * len(gens)
    for i, p in enumerate(founders):
        cum_cur = [cum_prev[j] + sm[p][j] for j in range(len(gens))]
        top = " ".join(f"{sx(g):.1f},{sy(cum_cur[j]):.1f}" for j, g in enumerate(gens))
        bot = " ".join(f"{sx(g):.1f},{sy(cum_prev[j]):.1f}" for j, g in reversed(list(enumerate(gens))))
        col = _PALETTE[i % len(_PALETTE)]
        parts.append(f'<polygon points="{top} {bot}" fill="{col}" fill-opacity="0.82"/>')
        cum_prev = cum_cur
    parts.append('</g>')

    # x ticks
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        g = round(gmax * frac)
        parts.append(f'<text x="{sx(g):.1f}" y="{y1+18:.1f}" fill="#6b7280" font-size="10" text-anchor="middle">{g}</text>')
    parts.append(f'<text x="{(x0+x1)/2:.0f}" y="{y1+40:.0f}" fill="#9ca3af" font-size="12" text-anchor="middle">generation</text>')

    # legend (final-share sorted)
    final = {p: (sm[p][-1] if sm[p] else 0.0) for p in founders}
    order = sorted(founders, key=lambda p: final[p], reverse=True)
    lx, ly = x1 + 16, MT
    for k, p in enumerate(order):
        col = _PALETTE[founders.index(p) % len(_PALETTE)]
        yy = ly + k * 20
        parts.append(f'<rect x="{lx}" y="{yy-9}" width="12" height="12" fill="{col}" fill-opacity="0.82"/>')
        parts.append(f'<text x="{lx+18}" y="{yy+1}" fill="#cbd5e1" font-size="11">{p} {final[p]*100:.0f}%</text>')

    parts.append('</svg>')
    return "\n".join(parts)


def champion_lineage_mmd(
    winners: list[dict], children: dict[str, list[str]], nodes: dict[str, dict]
) -> str:
    """Trace the final-gen rank-0 winner's first-parent bloodline to founder."""
    if not winners:
        return "graph TD\n    empty[\"no winners\"]\n"
    last_gen = max(int(w["generation"]) for w in winners)
    champ = min(
        (w for w in winners if int(w["generation"]) == last_gen),
        key=lambda w: w.get("rank", 0),
    )
    chain: list[str] = []
    tok = _winner_token(champ["individual_id"])
    seen = set()
    while tok and tok not in seen:
        seen.add(tok)
        chain.append(tok)
        if _persona_of(tok) is not None:
            break
        parents = children.get(tok) or []
        tok = parents[0] if parents else None
    chain.reverse()  # founder → ... → champion

    lines = ["%% champion bloodline (final best individual → founder)", "graph TD"]

    def node_def(t: str) -> tuple[str, str]:
        meta = nodes.get(t, {})
        gen = meta.get("gen")
        score = meta.get("score")
        nid = re.sub(r"[^A-Za-z0-9_]", "_", t)
        persona = _persona_of(t)
        if persona is not None:
            lbl = f"founder<br/>{persona}" + (f"<br/>score={score:.3f}" if score is not None else "")
        else:
            sc = f"<br/>score={score:.3f}" if score is not None else ""
            gtxt = f"gen {gen} " if gen is not None else ""
            lbl = f"{gtxt}{t[:8]}{sc}"
        return nid, lbl

    for t in chain:
        nid, lbl = node_def(t)
        lines.append(f'    {nid}["{lbl}"]')
    for a, b in zip(chain, chain[1:]):
        na = re.sub(r"[^A-Za-z0-9_]", "_", a)
        nb = re.sub(r"[^A-Za-z0-9_]", "_", b)
        lines.append(f"    {na} --> {nb}")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="evolution lineage views (P2)")
    ap.add_argument("run_dir", help="run output dir (with lineage.mmd + winners.jsonl)")
    ap.add_argument("--window", type=int, default=9, help="rolling window for dominance smoothing")
    ap.add_argument("--out-svg", default=None, help="dominance SVG path (default: <run_dir>/persona_dominance.svg)")
    ap.add_argument("--out-mmd", default=None, help="champion lineage path (default: <run_dir>/champion_lineage.mmd)")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    children, nodes = parse_lineage(run_dir)
    winners = load_winners(run_dir)
    manifest = load_manifest(run_dir)
    founders = list(manifest.get("personas") or manifest.get("founder_ids") or [])
    founders = [f.replace("-", "_") for f in founders]  # match persona token space

    gens, shares, unresolved = founder_shares(winners, children, founders)
    label, is_proxy = honest_label(manifest, len(gens))

    svg = render_dominance_svg(gens, shares, label, is_proxy, args.window)
    out_svg = Path(args.out_svg) if args.out_svg else run_dir / "persona_dominance.svg"
    out_svg.write_text(svg, encoding="utf-8")

    mmd = champion_lineage_mmd(winners, children, nodes)
    out_mmd = Path(args.out_mmd) if args.out_mmd else run_dir / "champion_lineage.mmd"
    out_mmd.write_text(mmd, encoding="utf-8")

    print(f"wrote {out_svg}  ({len(svg)} bytes)")
    print(f"wrote {out_mmd}  ({len(mmd)} bytes)")
    final = {p: (shares[p][-1] if shares[p] else 0.0) for p in founders}
    top = sorted(final.items(), key=lambda kv: kv[1], reverse=True)[:3]
    print("final winner-lineage share:", ", ".join(f"{p}={v*100:.0f}%" for p, v in top))
    if unresolved:
        print(f"warning: {unresolved} winner(s) could not be traced to a founder", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
