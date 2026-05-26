#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Regenerate SUMMARY.md from a sweep run's all_summaries.json (no re-run needed).

poc_openended_sweep.py が書く ``all_summaries.json`` を読み、最新の markdown
レンダラで ``SUMMARY.md`` を再生成する。旧 run (bspread フィールド無し) も
``.get(..., 0)`` で後方互換に扱う。

    py -3.11 scripts/poc_openended_render_summary.py out/poc_openended_sweep_2026_05_26
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 同ディレクトリの sweep スクリプトから markdown writer を再利用
sys.path.insert(0, str(Path(__file__).resolve().parent))
from poc_openended_sweep import _write_summary_md  # noqa: E402


class _Args:
    """_write_summary_md が参照する属性だけを持つ薄い shim."""

    def __init__(self, summaries: list[dict]):
        cfgs = [s.get("config", {}) for s in summaries]
        self.seed = cfgs[0].get("seed", 0) if cfgs else 0
        self.gens = max((c.get("gens", 0) for c in cfgs), default=0)
        self.pop = max((c.get("pop", 0) for c in cfgs), default=0)
        self.factors = cfgs[0].get("factors", 0) if cfgs else 0
        self.sat_noise = cfgs[0].get("sat_noise", 0) if cfgs else 0
        # latent は構成ごとに異なりうるので最大値を代表に
        self.latent = max((c.get("latent", 0) for c in cfgs), default=0)
        self.n_archetypes = cfgs[0].get("n_archetypes", 0) if cfgs else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="regenerate SUMMARY.md from all_summaries.json")
    ap.add_argument("out_dir", type=str)
    args = ap.parse_args()
    out = Path(args.out_dir)
    summaries = json.loads((out / "all_summaries.json").read_text(encoding="utf-8"))
    _write_summary_md(out, summaries, _Args(summaries))
    print(f"regenerated {out / 'SUMMARY.md'} from {len(summaries)} summaries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
