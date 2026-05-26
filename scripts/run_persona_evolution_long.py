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
    # 多層ゲノム (Genome3D) で走る:
    py -3.11 scripts/run_persona_evolution_long.py --genome3d --generations 100 --out out/persona_evo_3d
    py -3.11 scripts/run_persona_evolution_long.py --genome3d --crossover-mode cross --generations 1000 --resume
    # 実 LLM fitness を ollama 固定で走る (ollama 起動が前提):
    py -3.11 scripts/run_persona_evolution_long.py --fitness llm --backend ollama --generations 100 --out out/persona_evo_llm

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

# UTF-8 stdout/stderr (Windows cp932 対策, feedback_cli_utf8_stdout_pattern)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

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
from llive.perf.evolutionary.lldarwin import MultiPressureSelector  # noqa: E402

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
        "eval_timeout_seconds": (
            args.eval_timeout if (args.fitness == "llm" and args.eval_timeout and args.eval_timeout > 0) else None
        ),
        "fixed_backend": (args.backend if args.fitness == "llm" else None),
        "personas": list(args.personas),
        "population": args.population,
        "generations": args.generations,
        "seed": args.seed,
        "resume": bool(args.resume),
        "inject": list(args.inject) if args.inject else [],
        "max_stall_generations": (args.max_stall if args.max_stall and args.max_stall > 0 else None),
    }
    # diverse-founder-prompts は genome3d 経路のみ有効だが、後付けの追跡性のため
    # フラグ値は常に manifest top-level に additive で残す (既存キーは不変)。
    manifest["diverse_founder_prompts"] = bool(args.diverse_founder_prompts)
    if args.genome3d:
        manifest["genome"] = {
            "kind": "Genome3D",
            "chromosomes": ["c_impl", "c_prompt", "c_meta", "c_factors(10x4)"],
            "crossover_mode": args.crossover_mode,
            "mutation_step": args.mutation_step,
            "diverse_founder_prompts": bool(args.diverse_founder_prompts),
        }
        manifest["operators"] = (
            f"genome3d: TournamentSelection / Genome3DCrossover({args.crossover_mode}) / "
            f"Genome3DMutation(step={args.mutation_step}) / Elitism"
        )
    else:
        manifest["genome"] = {
            "kind": "Genome",
            "dim": len(LIVE_VARIANT_GENOME_LABELS),
            "labels": list(LIVE_VARIANT_GENOME_LABELS),
            "bounds_lower": list(LIVE_VARIANT_GENOME_BOUNDS.lower),
            "bounds_upper": list(LIVE_VARIANT_GENOME_BOUNDS.upper),
        }
        manifest["operators"] = (
            "default: TournamentSelection / BlendCrossover / Gaussian+Reset / Elitism"
        )
    manifest["runtime"] = collect_runtime_metadata()
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
    if traceback_str:
        summary["traceback"] = traceback_str
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
        choices=["proxy", "rich-proxy", "pressure-proxy", "real-pressure", "llm"],
        default="proxy",
        help="proxy=旧 layer-平均10次元 heuristic (baseline) / "
        "rich-proxy=全40次元 c_factors + persona 多峰 + 染色体コヒーレンス (決定論, LLM 呼ばない) / "
        "pressure-proxy=LLM 苦手軸 proxy pressure (typo/polysemy/multistep/calibration/context, "
        "Stage2 mechanism feasibility, 決定論) / "
        "real-pressure=Stage2 後半: 実 on-prem LLM 苦手軸評価 (個体 c_prompt→system prompt, "
        "固定 LLM を実タスクで採点, temp=0+cache) / "
        "llm=実 LLM fitness (on-prem fail-closed)",
    )
    ap.add_argument(
        "--ollama-model",
        type=str,
        default="llama3.2:latest",
        help="--fitness real-pressure で使う固定 on-prem ollama モデル (既定 llama3.2:latest)。",
    )
    ap.add_argument(
        "--max-wallclock-seconds",
        type=float,
        default=None,
        help="実時間予算 (秒)。超過で safely 停止 (snapshot 済なので --resume で継続可)。"
        "12h 連続ランは 43200。既定 None=無制限。",
    )
    ap.add_argument(
        "--eval-timeout",
        type=float,
        default=120.0,
        help="--fitness llm 時の 1 個体評価の hang guard 秒数 (無応答 backend を打ち切り淘汰)。"
        "0 で無効。既定 120。proxy では無視。",
    )
    ap.add_argument(
        "--backend",
        choices=["mock", "ollama", "mamba", "rwkv", "jamba"],
        default=None,
        help="--fitness llm 時に全個体をこの on-prem backend に固定する (genome の backend_id を無視)。"
        "実 ollama run は `--backend ollama`。既定 None=genome の backend_id で選択。cloud は不可。",
    )
    # ---- Genome3D (多層ゲノム) モード ----
    ap.add_argument(
        "--genome3d",
        action="store_true",
        help="多層ゲノム Genome3D で走る (founder/padding/operator を Genome3D 化)。"
        "既定は flat 19-dim Genome。",
    )
    ap.add_argument(
        "--crossover-mode",
        choices=["intra", "cross"],
        default="intra",
        help="genome3d 時の crossover (intra=層内 / cross=層間)。既定 intra。",
    )
    ap.add_argument(
        "--mutation-step",
        type=float,
        default=0.1,
        help="genome3d 時の mutation neighborhood step_size。既定 0.1。",
    )
    ap.add_argument(
        "--diverse-founder-prompts",
        action="store_true",
        help="genome3d 時に各 founder の c_prompt を affinity 由来に多様化する (opt-in)。"
        "全 founder が同一 PromptChromosome.default から始まる初期探索分散の低さ "
        "(12h ランで best が gen35 で天井 1.0 張り付き) を是正。既定 OFF (後方互換)。",
    )
    # ---- 安全弁 (長時間 run で「全個体同一→空回り」を止める) ----
    ap.add_argument(
        "--max-stall",
        type=int,
        default=25,
        help="全個体が同一に収束した状態が連続でこの世代数続いたら停止 (空回り防止)。"
        "0 で無効。既定 25。patience/diversity_floor を無効化した長期 run でも効く。",
    )
    ap.add_argument(
        "--selection",
        choices=["default", "lldarwin"],
        default="default",
        help="選択圧。default=Tournament(既定) / lldarwin=複数選択圧の多目的淘汰 "
        "(ε-lexicase, rich-proxy の breakdown を pressure として独立評価し monoculture を回避)。",
    )
    ap.add_argument(
        "--novelty",
        action="store_true",
        help="lldarwin に novelty pressure を加える (k-NN 探索圧で空きニッチを埋め戻す, "
        "Stage1)。--selection lldarwin と併用。default は OFF (criteria 除外のみ)。",
    )
    ap.add_argument(
        "--lineage-reservoir",
        action="store_true",
        help="lldarwin Stage1.5: lineage-niched 中立貯蔵庫。絶滅した founder 系統を毎世代 "
        "貯蔵庫 elite で再投入し系統絶滅を防ぐ (PoC で全8系統生存・fixation 0.31 実証)。",
    )
    ap.add_argument(
        "--reinject-interval",
        type=int,
        default=1,
        help="貯蔵庫の再投入を行う世代間隔 (1=毎世代)。大きいほど行動多様性を保ちやすいが "
        "系統が長期欠落するリスク (系統保持 vs 行動多様性のトレードオフ knob)。",
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
    if args.fitness == "rich-proxy":
        # 多峰 proxy: 全40次元 + persona archetype。fitness_fn 非 None だが proxy なので
        # is_proxy=True を明示し honest disclosure (used_proxy_fitness) を保つ。
        from llive.perf.evolutionary.fitness_rich import make_rich_proxy_fitness

        fitness_fn = make_rich_proxy_fitness(args.personas)
    elif args.fitness == "pressure-proxy":
        # LLM 苦手軸 proxy pressure (Stage2 mechanism feasibility, 決定論・LLM 呼ばない)。
        from llive.perf.evolutionary.pressures import make_pressure_fitness

        fitness_fn = make_pressure_fitness()
    elif args.fitness == "real-pressure":
        # Stage2 後半: 実 on-prem LLM 苦手軸評価。個体 c_prompt→system prompt を固定 LLM に
        # 被せ実タスクを解かせ採点 (temp=0 決定論+キャッシュ)。measurement purity=on-prem only。
        from llive.llm.backend import OllamaBackend
        from llive.perf.evolutionary.real_pressures import (
            RealPressureConfig,
            make_real_pressure_fitness,
        )

        rp_backend = OllamaBackend(model=args.ollama_model, timeout=args.eval_timeout or 120.0)
        fitness_fn = make_real_pressure_fitness(
            rp_backend, RealPressureConfig(model=args.ollama_model)
        )
    elif args.fitness == "llm":
        # per-eval hang guard: 無応答 backend で run 全体が止まらないよう打ち切り淘汰。
        eval_timeout = args.eval_timeout if args.eval_timeout and args.eval_timeout > 0 else None
        fitness_fn = llm_fitness_factory(
            LlmFitnessConfig(
                backend_factory=on_prem_backend_factory(),
                eval_timeout_seconds=eval_timeout,
                fixed_backend=args.backend,  # None=genome選択 / "ollama"=実 ollama 固定
            )
        )

    # 0 → 無効化 (None) として run_persona_evolution に渡す。
    max_stall = args.max_stall if args.max_stall and args.max_stall > 0 else None

    # lldarwin 選択圧 (複数選択圧の多目的淘汰)。default なら EvolutionLoop 既定 Tournament。
    # criteria=() = rich-proxy の breakdown (archetype::*/factor_score/...) を動的に pressure 化。
    selection_obj = (
        MultiPressureSelector(epsilon=0.01, use_novelty=args.novelty)
        if args.selection == "lldarwin"
        else None
    )

    print(
        f"[run] personas={len(args.personas)} pop={args.population} "
        f"generations={args.generations} patience={patience} fitness={args.fitness} "
        f"genome={'Genome3D/' + args.crossover_mode if args.genome3d else 'flat'} "
        f"max_stall={max_stall} resume={'yes' if args.resume else 'no'} out={args.out}"
    )

    # トレーサビリティ: 条件を run 前に記録 (失敗しても「どう走らせたか」は必ず残る)。
    _write_run_manifest(args.out, args)

    try:
        res = run_persona_evolution(
            args.personas,
            fitness_fn=fitness_fn,
            is_proxy=(args.fitness not in ("llm", "real-pressure")),
            population_size=args.population,
            generations=args.generations,
            seed=args.seed,
            out_dir=args.out,
            genome3d=args.genome3d,
            crossover_mode=args.crossover_mode,
            mutation_step=args.mutation_step,
            diverse_founder_prompts=args.diverse_founder_prompts,
            inject_persona_ids=args.inject,
            patience=patience,
            diversity_floor=0.0,  # 多様性枯渇でも止めない (長期研究)
            checkpoint_every=args.checkpoint_every,
            resume_from=resume_from,
            persist_generation_log=True,  # generations.jsonl + snapshot (SVG材料 + resume)
            log_progress=True,
            # 安全弁: diversity_floor=0.0 で多様性停止を無効化しているため、全個体同一に
            # 収束した場合の空回りはこの hard guard で止める (ユーザー要望 2026-05-24)。
            max_stall_generations=max_stall,
            selection=selection_obj,
            lineage_reservoir=args.lineage_reservoir,
            reinject_interval=args.reinject_interval,
            max_wallclock_seconds=(
                args.max_wallclock_seconds if args.max_wallclock_seconds and args.max_wallclock_seconds > 0 else None
            ),
        )
    except Exception as exc:  # noqa: BLE001 - 失敗も実験結果として残す
        # 「失敗してもいいが結果が残らないと意味がない」: 失敗理由 + traceback を run_summary に記録。
        _write_run_summary(
            args.out, status="failed", error=exc, traceback_str=traceback.format_exc()
        )
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
