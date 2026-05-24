# SPDX-License-Identifier: Apache-2.0
"""persona 世代交代 長期運用ランナー (100→1000 世代研究用, 2026-05-23 環境整備).

ユーザー要望:
    「ずっと世代交代を続けられるように環境整備」「100 世代でかなりの完成度」
    「出来れば 1000 世代まで研究したい」。

:func:`run_persona_evolution` を **早期停止なし (patience 無効化) + generation ログ
永続化 + checkpoint/resume** で回す薄いラッパ。

honest disclosure
-----------------
fitness は **proxy** (LLM を呼ばない決定論的 heuristic)。proxy は数十世代で収束する
ため、それ以降の世代は「収束後のドリフト」を見るもので、意味ある改善は実 LLM fitness
配線後に現れる。1000 世代を回せること自体は環境整備の達成だが、研究的価値は実 fitness
が前提 (compare_against_llm_baselines / lleval 連携)。

使い方:
    py -3.11 scripts/run_persona_evolution_long.py --generations 100 --out out/persona_evo
    py -3.11 scripts/run_persona_evolution_long.py --generations 1000 --population 32 --resume

``--resume`` 指定時は ``out_dir`` の最新 snapshot から再開する (ずっと回せる)。
出力: ``out_dir/generations.jsonl`` (世代ごと best/mean/std/diversity = SVG 時系列材料),
``winners.jsonl`` (世代ごと top3), ``lineage.mmd`` (系統樹), ``snapshot_gen_*.json``。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

# UTF-8 stdout (Windows cp932 対策, feedback_cli_utf8_stdout_pattern)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from llive.perf.evolutionary import persona_extended as _persona_extended  # noqa: E402,F401  (import 副作用で拡張ペルソナを PERSONA_ONTOLOGY に登録)
from llive.perf.evolutionary.fitness_llm import (  # noqa: E402
    LlmFitnessConfig,
    llm_fitness_factory,
    on_prem_backend_factory,
)
from llive.perf.evolutionary.persona import (  # noqa: E402
    PERSONA_ONTOLOGY,
    RESEARCH_METHODOLOGY_PERSONA_IDS,
)
from llive.benchmark.runtime_metadata import collect_runtime_metadata  # noqa: E402
from llive.perf.evolutionary.llive_variant import (  # noqa: E402
    LIVE_VARIANT_GENOME_BOUNDS,
    LIVE_VARIANT_GENOME_LABELS,
)
from llive.perf.evolutionary.persona_evolution import run_persona_evolution  # noqa: E402

# 既定 roster = 研究方法論ペルソナ 4 名 + 多様性のため歴史人物 4 名。
# 「段階的に定期追加」= この list に ID を足すだけ。
DEFAULT_ROSTER: tuple[str, ...] = (
    *RESEARCH_METHODOLOGY_PERSONA_IDS,
    "oka-kiyoshi",
    "grothendieck",
    "von-neumann",
    "feynman",
)


def _git_commit() -> str:
    """llive repo の HEAD commit (トレーサビリティ用、取得不可なら 'unknown')."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(Path(__file__).resolve().parents[1]),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def _write_run_manifest(out_dir: Path, args: argparse.Namespace) -> None:
    """run の条件 (commit/設定/genome/環境) を run_manifest.json に記録する.

    「進化 run はデータ取りの貴重な実験」— 後々の改良で「どの commit のどの設定・どの genome
    構造で取ったデータか」を追えるようにする。**run 前に書く**ので失敗しても条件は必ず残る。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": "run_manifest/v1",
        "timestamp": datetime.now(UTC).isoformat(),
        "llive_commit": _git_commit(),
        "fitness": args.fitness,
        "personas": list(args.personas),
        "population": args.population,
        "generations": args.generations,
        "seed": args.seed,
        "resume": bool(args.resume),
        "inject": list(args.inject) if args.inject else [],
        "genome": {
            "dim": len(LIVE_VARIANT_GENOME_LABELS),
            "labels": list(LIVE_VARIANT_GENOME_LABELS),
            "bounds_lower": list(LIVE_VARIANT_GENOME_BOUNDS.lower),
            "bounds_upper": list(LIVE_VARIANT_GENOME_BOUNDS.upper),
        },
        "operators": "default: TournamentSelection / BlendCrossover / Gaussian+Reset / Elitism",
        "runtime": collect_runtime_metadata(),
    }
    (out_dir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )


def _write_run_summary(
    out_dir: Path,
    *,
    status: str,
    res=None,
    error: Exception | None = None,
    traceback_str: str | None = None,
) -> None:
    """run の結果 (成功/失敗とも) を run_summary.json に記録する.

    「失敗してもいいが結果が残らないと意味がない」— 成功時は best/収束/elapsed の主要指標、
    失敗時は status=failed + error を残す。個体別の詳細 breakdown は snapshot_gen_*.json に
    残るので、改良時 (backend 収束 / 淘汰理由の解析) はそちらを使う。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict = {
        "schema": "run_summary/v1",
        "status": status,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if res is not None:
        er = res.evolution_result
        summary.update(
            {
                "final_generation": er.final_population.generation,
                "best_score": float(er.best_score),
                "stopped_reason": er.stopped_reason,
                "elapsed_seconds": float(er.elapsed_seconds),
                "used_proxy_fitness": res.used_proxy_fitness,
                "founder_ids": list(res.founder_ids),
                "injected_persona_ids": list(res.injected_persona_ids),
            }
        )
    if error is not None:
        summary["error"] = repr(error)
    (out_dir / "run_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="persona 世代交代 長期ランナー")
    ap.add_argument("--generations", type=int, default=100)
    ap.add_argument("--population", type=int, default=24)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=Path("out/persona_evo"))
    ap.add_argument(
        "--personas",
        nargs="*",
        default=list(DEFAULT_ROSTER),
        help="founder にする persona id 列 (省略時 既定 roster)",
    )
    ap.add_argument("--checkpoint-every", type=int, default=25)
    ap.add_argument(
        "--resume",
        action="store_true",
        help="out_dir の最新 snapshot から再開 (ずっと回せる)",
    )
    ap.add_argument(
        "--inject",
        nargs="*",
        default=None,
        help="resume 時に走行中の集団へ追加投入する persona id (immigration, 段階的追加)",
    )
    ap.add_argument(
        "--patience",
        type=int,
        default=None,
        help="早期停止 patience。既定 None → generations+1 (= 無効化, 完走)",
    )
    ap.add_argument(
        "--fitness",
        choices=["proxy", "llm"],
        default="proxy",
        help="proxy=決定論 heuristic (既定, LLM 呼ばない) / llm=実 LLM fitness (on-prem fail-closed)",
    )
    args = ap.parse_args()

    unknown = [p for p in args.personas if p not in PERSONA_ONTOLOGY]
    if args.inject:
        unknown += [p for p in args.inject if p not in PERSONA_ONTOLOGY]
    if unknown:
        print(f"[ERROR] unknown persona ids: {unknown}", file=sys.stderr)
        return 2

    # patience 既定 = 無効化 (指定世代を完走させる)。proxy は早く収束するため必須。
    patience = args.patience if args.patience is not None else args.generations + 1
    resume_from = args.out if args.resume else None

    # fitness 選択: llm は on-prem fail-closed backend factory (measurement purity)。
    # cloud backend を選んだ個体は実体化で拒否され fitness=0 で淘汰される
    # (backend_id は B1 修正で label 解決済 = position 誤読なし)。
    fitness_fn = None
    if args.fitness == "llm":
        fitness_fn = llm_fitness_factory(
            LlmFitnessConfig(backend_factory=on_prem_backend_factory())
        )

    print(
        f"[run] personas={len(args.personas)} pop={args.population} "
        f"generations={args.generations} patience={patience} fitness={args.fitness} "
        f"resume={'yes' if args.resume else 'no'} out={args.out}"
    )

    # トレーサビリティ: 条件を run 前に記録 (失敗しても「どう走らせたか」は必ず残る)。
    _write_run_manifest(args.out, args)

    try:
        res = run_persona_evolution(
            args.personas,
            fitness_fn=fitness_fn,
            population_size=args.population,
            generations=args.generations,
            seed=args.seed,
            out_dir=args.out,
            inject_persona_ids=args.inject,
            patience=patience,
            diversity_floor=0.0,  # 多様性枯渇でも止めない (長期研究)
            checkpoint_every=args.checkpoint_every,
            resume_from=resume_from,
            persist_generation_log=True,  # generations.jsonl + snapshot (SVG材料 + resume)
            log_progress=True,
        )
    except Exception as exc:  # noqa: BLE001 - 失敗も実験結果として残す
        # 「失敗してもいいが結果が残らないと意味がない」: 失敗理由を run_summary に記録。
        _write_run_summary(args.out, status="failed", error=exc)
        print(f"[FAILED] {exc!r}", file=sys.stderr)
        print("  → 条件は run_manifest.json、失敗理由は run_summary.json に記録済", file=sys.stderr)
        return 1

    _write_run_summary(args.out, status="completed", res=res)
    if res.injected_persona_ids:
        print(f"[immigration] injected mid-run: {list(res.injected_persona_ids)}")
    er = res.evolution_result
    label = "proxy fitness, NOT real LLM eval" if res.used_proxy_fitness else "real LLM fitness"
    print(f"---- result (honest: {label}) ----")
    print(f"final_generation = {er.final_population.generation}")
    print(f"best_score       = {er.best_score:.6f}")
    print(f"stopped_reason   = {er.stopped_reason}")
    print(f"elapsed_seconds  = {er.elapsed_seconds:.2f}")
    print(f"manifest         = {args.out / 'run_manifest.json'}")
    print(f"summary          = {args.out / 'run_summary.json'}")
    print(f"winners          = {res.winners_path}")
    print(f"lineage          = {res.lineage_path}")
    print(f"generations.jsonl= {args.out / 'generations.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
