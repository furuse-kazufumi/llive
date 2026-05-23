# SPDX-License-Identifier: Apache-2.0
"""Persona 世代交代 turnkey demo (smoke).

ユーザー要望 (2026-05-23): ペルソナ founder からの世代交代を 1 コマンドで回す。
roster は段階的に定期追加 (ID を足すだけ。歴史人物も混在可)。

本 demo は :func:`run_persona_evolution` を呼んで out/ に履歴 (winners.jsonl /
lineage.mmd) を出すだけの薄いラッパ。fitness は **proxy** (LLM を呼ばない,
honest disclosure)。実 fitness + 現状 LLM 比較は次層 (stub)。

使い方
------

研究方法論ペルソナ 4 名 (default) を founder にして 15 世代:

```
py -3.11 scripts/demo_persona_evolution.py --out out/persona_evo
```

歴史人物も混ぜる (roster をパラメータ化 = ID を足すだけ):

```
py -3.11 scripts/demo_persona_evolution.py \\
    --personas furuse-kazufumi friston millidge isomura-takuya oka-kiyoshi feynman \\
    --pop 16 --gens 20 --out out/persona_evo_mixed
```

系統樹を見る:

```
type out\\persona_evo\\lineage.mmd
```
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from llive.perf.evolutionary.persona import RESEARCH_METHODOLOGY_PERSONA_IDS
from llive.perf.evolutionary.persona_evolution import run_persona_evolution


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
        "--personas",
        nargs="+",
        default=list(RESEARCH_METHODOLOGY_PERSONA_IDS),
        help="founder にする persona id 列 (PERSONA_ONTOLOGY のキー)。",
    )
    parser.add_argument("--pop", type=int, default=12, dest="population_size")
    parser.add_argument("--gens", type=int, default=15, dest="generations")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--out", type=Path, default=Path("out/persona_evo"), dest="out_dir"
    )
    args = parser.parse_args()

    result = run_persona_evolution(
        persona_ids=args.personas,
        population_size=args.population_size,
        generations=args.generations,
        seed=args.seed,
        out_dir=args.out_dir,
        log_progress=True,
    )

    summary = {
        "founders": list(result.founder_ids),
        "used_proxy_fitness": result.used_proxy_fitness,
        "best_score": result.evolution_result.best_score,
        "best_individual_id": result.evolution_result.best_individual.individual_id,
        "stopped_reason": result.evolution_result.stopped_reason,
        "final_generation": result.evolution_result.final_population.generation,
        "winners_path": str(result.winners_path) if result.winners_path else None,
        "lineage_path": str(result.lineage_path) if result.lineage_path else None,
    }
    print("---")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if result.used_proxy_fitness:
        print(
            "\n[honest disclosure] fitness は PROXY です (LLM 評価ではない)。"
            "実 fitness + 現状 LLM 比較は compare_against_llm_baselines (stub)。"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
