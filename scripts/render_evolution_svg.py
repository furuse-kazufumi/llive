# SPDX-License-Identifier: Apache-2.0
"""進化 fitness 時系列を animated SVG (SMIL) に描く CLI.

``run_persona_evolution`` / ``demo_persona_evolution.py`` が出す
``metrics.jsonl`` を読んで, 世代軸 fitness 折れ線 (best/mean) +
diversity_l2 帯の animated SVG を生成する。

fitness は **proxy** (LLM 評価ではない, honest disclosure)。
``--no-proxy-note`` で proxy 注記を外せるが, 現状の llive fitness は proxy の
ため通常は付けたまま使う。

使い方
------

```
py -3.11 scripts/render_evolution_svg.py \\
    --metrics out/persona_evo_1000/metrics.jsonl \\
    --out out/persona_evo_1000/evolution.svg
```

founder を注記する (どの種から始めたかの honest disclosure):

```
py -3.11 scripts/render_evolution_svg.py \\
    --metrics out/persona_evo_1000/metrics.jsonl \\
    --out out/persona_evo_1000/evolution.svg \\
    --founders furuse-kazufumi friston millidge isomura-takuya
```
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from llive.perf.evolutionary.svg_render import render_evolution_svg


def _ensure_utf8_stdout() -> None:
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main() -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--metrics",
        type=Path,
        required=True,
        help="metrics.jsonl のパス (PopulationStats を毎世代 1 行ダンプしたもの)。",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="出力 SVG パス。省略時は stdout に出力。",
    )
    parser.add_argument(
        "--title",
        type=str,
        default="llive persona evolution — fitness over generations",
        help="SVG タイトル。",
    )
    parser.add_argument(
        "--founders",
        nargs="+",
        default=None,
        help="founder persona ID 列 (honest disclosure: どの種から始めたか)。",
    )
    parser.add_argument(
        "--max-points",
        type=int,
        default=200,
        dest="max_points",
        help="ダウンサンプリング後の最大点数 (default 200)。",
    )
    parser.add_argument(
        "--loop-seconds",
        type=float,
        default=18.0,
        dest="loop_seconds",
        help="アニメーション 1 周の秒数 (default 18)。",
    )
    parser.add_argument(
        "--no-proxy-note",
        action="store_false",
        dest="proxy",
        help="proxy fitness 注記を付けない (非推奨: 現状 fitness は proxy)。",
    )
    args = parser.parse_args()

    if not args.metrics.exists():
        print(f"[error] metrics file not found: {args.metrics}", file=sys.stderr)
        return 2

    svg = render_evolution_svg(
        args.metrics,
        out_path=args.out,
        title=args.title,
        founders=tuple(args.founders) if args.founders else None,
        max_points=args.max_points,
        proxy=args.proxy,
        loop_seconds=args.loop_seconds,
    )

    if args.out is None:
        sys.stdout.write(svg)
        sys.stdout.write("\n")
    else:
        print(f"[ok] wrote {len(svg)} bytes to {args.out}")
        if args.proxy:
            print(
                "[honest disclosure] fitness は PROXY です (LLM 評価ではない)。"
                "SVG の title / caption / desc / footer に注記済み。"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
