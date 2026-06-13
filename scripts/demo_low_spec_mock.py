# SPDX-License-Identifier: Apache-2.0
"""low_spec bench を mock backend で実走する demo (v0.B Phase 4 PoC).

非 transformer 5 案の HTTP backend は MockBackend に解決される (default).
実 llama-server を立ち上げなくても **bench の経路**を全件確認できる.

Usage::

    py -3.11 scripts/demo_low_spec_mock.py --sizes xs s --backends mock
    py -3.11 scripts/demo_low_spec_mock.py --sizes xs --backends mock mock --json out.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from llive.benchmark.low_spec import run_matrix, to_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backends",
        nargs="+",
        default=["mock"],
        help="backend 名 (mock のみ credential 不要). 実 backend は env 設定後に同 script で実行.",
    )
    parser.add_argument(
        "--sizes",
        nargs="+",
        default=["xs", "s"],
        help="xs/s は CPU 安全, m 以上は opt-in",
    )
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--allow-cloud", action="store_true")
    parser.add_argument("--json", type=Path, default=None, help="JSON 出力先")
    args = parser.parse_args()

    results = run_matrix(
        backend_names=args.backends,
        sizes=args.sizes,
        max_tokens=args.max_tokens,
        allow_cloud=args.allow_cloud,
    )

    # tabular summary を stdout に
    print(
        f"{'backend':<12} {'size':<4} {'lat_s':<8} {'tok/s':<8} "
        f"{'rss_MB':<8} {'meets_lat':<10} {'finish':<10}"
    )
    for r in results:
        rss = "n/a" if r.peak_rss_mb is None else f"{r.peak_rss_mb:.0f}"
        toks = "n/a" if r.tokens_per_second is None else f"{r.tokens_per_second:.1f}"
        print(
            f"{r.backend:<12} {r.size:<4} {r.latency_s:<8.4f} {toks:<8} "
            f"{rss:<8} {str(r.meets_latency_target):<10} {r.finish_reason:<10}"
        )
        for note in r.notes:
            print(f"  ! {note}")

    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(to_json(results), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nJSON written to: {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
