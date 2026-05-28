# SPDX-License-Identifier: Apache-2.0
"""Phase D-1 進化接続: ``make_agentic_fitness`` を **multi-turn InterCode runner** に配線する.

親ゴール: 進化型オーケストラ + RAPTOR 決定論オラクル + 無制限 test-time compute で
Claude Mythos をセキュリティ領域で超える
([[goal_surpass_mythos_evolutionary]] /
 fullsense docs/research/mythos_surpass_design_2026_05_27.md §10 + Phase D-1 「next」(1))。

位置づけ (設計 §10-1 / Phase D-1 next-(1))
------------------------------------------
Phase D-1 (実機) で命題が支持された:
  * **multi-turn 自律エージェント性が実 picoCTF の file-backed タスクを 0→3 に反転**
    (1-turn no_tool 0.429 → multiturn 0.571)。観察→行動→観察の自律挙動が on-prem で創発。
  * = **非飽和帯が出た** → 進化を接続する条件が揃った。

設計 §10-1 / Phase D-1 next-(1) の指示:
  > ``poc_ctf_agentic_evolution.py`` の ``make_agentic_fitness`` を本 multi-turn runner に
  > 差替え、agentic 戦略(いつ ls するか/どのツール順/再試行/self-check)を ε-lexicase で
  > 進化。各 InterCode タスク=1 case。file-backed で「観察先行戦略 specialist」が立つか。

本ファイルはその **薄い配線** で、3 つの既存ハーネスを **import 利用のみ** (本体/上流無編集):
  * ``poc_intercode_agentic``  : ``build_intercode_battery`` (実 CTF ローダ) / Docker helper。
  * ``poc_intercode_multiturn``: ``run_multiturn_task`` (multi-turn ループ・**決定論オラクル不変**)
    / mock 軌跡 (``_mock_ideal_script`` / ``_mock_naive_script``)。
  * ``poc_ctf_agentic_evolution``: agentic 戦略遺伝子 ``tool_propensity`` / ``strategy_for`` /
    観測専用 breakdown キー規約 (= 数値キーのみ lexicase case 化される安全配線)。
  * ``llive.perf.evolutionary``: ``build_lldarwin_v2_selector`` (ε-lexicase 確定 S1) /
    ``run_persona_evolution`` (Genome3D turnkey) / ``genome_to_system_prompt``。

🟢 「agentic 戦略」の写像 (PoC-CTF-3 の code/direct → multi-turn では observe/naive)
-----------------------------------------------------------------------------------
PoC-CTF-3 は自明 decode で「code を書く / direct に答える」を戦略次元にした。本ファイルは
**実 CTF multi-turn** に持ち込むので、戦略次元を **multi-turn のエージェント規律レベル**に
写す (同じ ``tool_propensity`` を流用 = 進化で動く c_prompt 由来連続次元):

  p_tool(individual) >= 0.5  →  戦略 "observe"  (観察先行 specialist):
      * 各ターン system に「まず ls / 架空名禁止 / flag verbatim / 1 アクション」規律を効かせ
      * submit 前 self-check gate を有効 (``max_self_checks=1``; 算術の頭打ちを実行で消す)。
      → file-backed タスクで実ファイル名を ls→cat/grep し flag を verbatim 抽出できる。

  p_tool(individual) <  0.5  →  戦略 "naive"  (頭で当てる; 観察しない):
      * ls せず即座に頭で当てた flag を submit / self-check gate 無効。
      → file-backed タスクは構造的に解けない (1-turn 失敗モードの再現)。算術問のみ偶発正答。

つまり **「いつ ls するか / self-check するか」= agentic 戦略**を c_prompt 由来 propensity に
乗せ、ε-lexicase が **「file-backed タスクを解く observe specialist」を集団に保つ**かを測る。
各 InterCode タスク = 1 lexicase case (``ic::<tid>`` の 0/1)。

検証する命題 (falsifiable)
--------------------------
    **個体 c_prompt から「観察先行(observe)/頭で当てる(naive)」の multi-turn agentic 戦略を
      発現させ、multi-turn InterCode オラクル (flag 一致) で ε-lexicase 進化させると、集団
      coverage(best-of-pop) は「naive に固定した同条件の進化集団」を上回る。
      = ε-lexicase が file-backed タスクの observe specialist を集団に保つ。**

上回らなければ正直にそう報告する ([[feedback_benchmark_honest_disclosure]])。

🔴 honest 留保 (最重要)
-----------------------
* **--mock 必須**: 本ファイルの主用途は **配線/弁別ロジックの検証** (観察先行 vs ls せず戦略を
  弁別し、進化で観察先行が増えるロジック)。mock は canned 軌跡 (実機予言でない)。
* **real はフルでなく配線確認 or 極小**: multi-turn 実機は **~88s/task** (CPU 推論) で、
  集団(pop)×世代(gens)×タスク×ターン = 容易に数万秒になり **CPU では非現実的**。
  GPU が要る (size_vram>0)。real は「fitness が 1 個体 1 タスク回るか」の配線確認に限る。
* 自明帯では observe が満点に飽和し進化の伸びしろは小さい (PoC-0/1 教訓)。価値は **file-backed
  が混じる非飽和帯** (実 picoCTF easy 帯はまさにそれ) で出る。

使い方
------
::

    # 1. 配線/弁別ロジック検証 (LLM/Docker ゼロ; 観察先行 vs naive を弁別・進化で observe 増)
    py -3.11 scripts/poc_intercode_evolution.py --mock --pop 16 --gens 12 --max-tasks 7

    # 2. real 配線確認 (極小: 1 個体 1 タスクが multi-turn で回るか; CPU では集団×世代は非現実的)
    $env:PYTHONPATH='D:\\projects\\llive\\src'
    py -3.11 scripts/poc_intercode_evolution.py --real --pop 2 --gens 1 --max-tasks 1 --no-warmup
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# --- scripts/ を path に入れて姉妹 PoC を import (package ではないため) ---
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# 実 CTF ローダ + Docker helper (本体無編集 import)。
from poc_intercode_agentic import (  # noqa: E402
    _DEFAULT_REPO,
    IntercodeTask,
    build_intercode_battery,
    docker_available,
    image_present,
)

# multi-turn ループ本体 + mock 軌跡 (本体無編集 import; **決定論オラクル不変**)。
from poc_intercode_multiturn import (  # noqa: E402
    TaskTrace,
    _mock_ideal_script,
    _mock_naive_script,
    run_multiturn_task,
)

# agentic 戦略遺伝子 + 観測専用 breakdown キー規約 (PoC-CTF-3 と同じ安全配線)。
from poc_ctf_agentic_evolution import (  # noqa: E402
    tool_propensity,
)

from poc_ctf_toolexec import RealResponder  # noqa: E402

# --- 既存 llive 進化系資産 (編集せず import のみ) ---
from llive.benchmark.runtime_metadata import collect_runtime_metadata  # noqa: E402
from llive.perf.evolutionary.individual import FitnessReport, Individual  # noqa: E402
from llive.perf.evolutionary.lldarwin_v2 import (  # noqa: E402
    LLDarwinV2Config,
    build_lldarwin_v2_selector,
)
from llive.perf.evolutionary.persona import (  # noqa: E402
    RESEARCH_METHODOLOGY_PERSONA_IDS,
)
from llive.perf.evolutionary.persona_evolution import run_persona_evolution  # noqa: E402
from llive.perf.evolutionary.real_pressures import (  # noqa: E402
    genome_to_system_prompt,
)


def _ensure_utf8_stdout() -> None:
    # Windows cp932 console で picoCTF flag / 日本語を出力する CLI 規約
    # ([[feedback_cli_utf8_stdout_pattern]])。
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass


# ---------------------------------------------------------------------------
# agentic 戦略の写像: c_prompt → tool_propensity → "observe" / "naive"
# ---------------------------------------------------------------------------
#
# PoC-CTF-3 の閾値 (0.5) をそのまま流用 (= 同じ進化次元)。force_naive=True で戦略次元を殺す
# 対照条件 (= multi-turn 規律も self-check も無し = 1-turn 失敗モードに退化)。

_OBSERVE_THRESHOLD: float = 0.50


def multiturn_strategy_for(
    system_prompt: str, *, force_naive: bool
) -> tuple[str, float, float]:
    """個体 c_prompt → ("observe"/"naive", p_tool, skill_component).

    ``force_naive=True`` (naive-only 対照) は p_tool に関わらず "naive" を返す
    (= 進化させても観察先行戦略次元が無い対照集団)。
    """
    p, skill_component = tool_propensity(system_prompt)
    if force_naive:
        return "naive", p, skill_component
    return ("observe" if p >= _OBSERVE_THRESHOLD else "naive"), p, skill_component


# ---------------------------------------------------------------------------
# 1 個体 1 タスクの評価: 戦略 (observe/naive) で multi-turn runner を回す → 0/1
# ---------------------------------------------------------------------------


def eval_intercode_task(
    task: IntercodeTask,
    strategy: str,
    *,
    mock: bool,
    real_responder: RealResponder | None,
    real_model: str,
    max_turns: int,
    timeout: float,
) -> TaskTrace:
    """戦略に応じて multi-turn InterCode runner を回し、TaskTrace (solved 採点済) を返す.

    observe = 観察先行 + self-check gate 有効 / naive = ls せず頭で当てる + gate 無効。
    mock では multiturn の canned 軌跡 (_mock_ideal_script / _mock_naive_script) を使う。
    real では同 system 規律で実 ollama を回す (gate は戦略で on/off)。
    """
    observe = strategy == "observe"
    max_self_checks = 1 if observe else 0  # observe のみ submit 前 self-check を効かせる

    mock_script = None
    if mock:
        # observe = 理想軌跡 (ls→観察/検証→submit) / naive = ls せず誤 submit。
        mock_script = (_mock_ideal_script(task) if observe
                       else _mock_naive_script(task))

    return run_multiturn_task(
        task,
        max_turns=max_turns,
        timeout=timeout,
        responder=real_responder,
        model=real_model,
        mock_script=mock_script,
        max_self_checks=max_self_checks,
    )


# ---------------------------------------------------------------------------
# multi-turn InterCode agentic fitness: 個体 c_prompt → 戦略 → 各タスク 0/1 を per-case に
# ---------------------------------------------------------------------------
#
# PoC-CTF-3 make_agentic_fitness の **eval_task を multi-turn InterCode runner に差替えた版**。
# lexicase case は ``ic::<tid>`` の 0/1 のみ。観測専用キー (戦略 label / p_tool) は str 化して
# 格納 (数値だと lldarwin._infer_numeric_criteria が case 化し選択圧を汚染するため = 安全配線)。

_CASE_PREFIX = "ic::"
_STRAT_KEY = "ic_strategy::label"            # "observe" / "naive"
_PTOOL_KEY = "ic_strategy::p_tool"           # str(round(p_tool,4))
_SKILLDRV_KEY = "ic_strategy::skill_component"  # str(round(skill_component,4))


def _case_key(task: IntercodeTask) -> str:
    return f"{_CASE_PREFIX}ic{task.task_id}"


def make_intercode_agentic_fitness(
    tasks: list[IntercodeTask],
    *,
    mock: bool,
    force_naive: bool,
    real_responder: RealResponder | None = None,
    real_model: str = "qwen2.5:14b",
    max_turns: int = 8,
    timeout: float = 30.0,
    cache: dict[tuple[str, str, int], bool] | None = None,
) -> Callable[[object], FitnessReport]:
    """個体 c_prompt → multi-turn agentic 戦略 → 各 InterCode タスク 0/1 の per-case fitness.

    ``force_naive=True`` = naive-only 対照条件 (観察先行戦略次元を殺す)。それ以外は個体の
    c_prompt が tool-propensity を発現させ observe/naive を選ぶ (進化で動く戦略次元)。

    breakdown に ``ic::<tid> -> {0,1}`` を入れる → ε-lexicase が各 InterCode タスク=1 case
    として specialist (= file-backed を解く observe 個体) を集団に保つ。
    戦略 label / p_tool は観測専用キー (str 化) で記録 (case 化されない安全配線)。

    ``(system_prompt, strategy, task_id)`` キャッシュで temp=0 決定論サンプルを再利用
    (mock は task に対し決定論 → 同一キーで再計算回避; real の compute 結合制約を緩和)。
    """
    score_cache: dict[tuple[str, str, int], bool] = cache if cache is not None else {}

    def _solve(system: str, strategy: str, task: IntercodeTask) -> bool:
        key = (system, strategy, task.task_id)
        if key in score_cache:
            return score_cache[key]
        tr = eval_intercode_task(
            task, strategy, mock=mock, real_responder=real_responder,
            real_model=real_model, max_turns=max_turns, timeout=timeout,
        )
        score_cache[key] = bool(tr.solved)
        return bool(tr.solved)

    def fitness(genome: object) -> FitnessReport:
        system = genome_to_system_prompt(genome)
        strategy, p_tool, skill_component = multiturn_strategy_for(
            system, force_naive=force_naive)
        breakdown: dict[str, float] = {}
        solved = 0
        for task in tasks:
            ok = _solve(system, strategy, task)
            breakdown[_case_key(task)] = 1.0 if ok else 0.0
            solved += int(ok)
        # 観測専用 — **すべて str 化**して格納 (数値だと lexicase case 汚染; PoC-CTF-3 同様)。
        breakdown[_STRAT_KEY] = strategy  # type: ignore[assignment]
        breakdown[_PTOOL_KEY] = str(round(p_tool, 4))  # type: ignore[assignment]
        breakdown[_SKILLDRV_KEY] = str(round(skill_component, 4))  # type: ignore[assignment]
        score = solved / len(tasks) if tasks else 0.0
        return FitnessReport(
            score=float(score),
            breakdown=breakdown,
            runtime_metadata=dict(collect_runtime_metadata()),
            n_samples=len(tasks),
            notes=(
                f"InterCode multi-turn agentic fitness ({'mock' if mock else 'real'}, "
                f"strategy={strategy}, p_tool={p_tool:.2f}, force_naive={force_naive}). "
                "genome.c_prompt -> system prompt -> multi-turn strategy "
                "(observe: ls-first+self-check / naive: guess-in-head); deterministic "
                "flag oracle (multi-turn submit) -> per-case breakdown (ic::<tid>) for "
                "epsilon-lexicase observe-specialist preservation. score = mean per-task "
                "pass. temp=0 cached; on-prem only; CPU real is impractical for full "
                "pop x gens x multi-turn (GPU required) = wiring check, NOT a capability "
                "claim."
            ),
        )

    return fitness


# ---------------------------------------------------------------------------
# 集団 coverage + 戦略分布の計測 (PoC-CTF-3 の measure_* を InterCode キーに合わせて再実装)
# ---------------------------------------------------------------------------


@dataclass
class PopCoverage:
    generation: int
    n_individuals: int
    pop_coverage: float            # best-of-pop (union of solved)
    best_individual_coverage: float
    n_specialist_taskmasks: int
    n_observe: int
    n_naive: int
    solved_union: list[str]


def _coerce_float(val: object) -> float | None:
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            return None
    return None


def _solved_mask(ind: Individual, tasks: list[IntercodeTask]) -> frozenset[str]:
    bd = (ind.fitness.breakdown if ind.fitness else {}) or {}
    return frozenset(
        f"ic{t.task_id}" for t in tasks
        if float(bd.get(_case_key(t), 0.0)) >= 0.5
    )


def _strategy_of(ind: Individual) -> str | None:
    bd = (ind.fitness.breakdown if ind.fitness else {}) or {}
    s = bd.get(_STRAT_KEY)
    return s if isinstance(s, str) else None


def measure_population_coverage(
    individuals: list[Individual], generation: int, tasks: list[IntercodeTask]
) -> PopCoverage:
    n = len(tasks)
    masks = [_solved_mask(ind, tasks) for ind in individuals]
    union: set[str] = set()
    for m in masks:
        union |= m
    pop_cov = len(union) / n if n else 0.0
    best_mask = max(masks, key=len) if masks else frozenset()
    best_cov = len(best_mask) / n if n else 0.0
    distinct = {m for m in masks if m}
    strategies = [_strategy_of(ind) for ind in individuals]
    n_observe = sum(1 for s in strategies if s == "observe")
    n_naive = sum(1 for s in strategies if s == "naive")
    return PopCoverage(
        generation=generation,
        n_individuals=len(individuals),
        pop_coverage=round(pop_cov, 4),
        best_individual_coverage=round(best_cov, 4),
        n_specialist_taskmasks=len(distinct),
        n_observe=n_observe,
        n_naive=n_naive,
        solved_union=sorted(union),
    )


def measure_strategy_distribution(individuals: list[Individual]) -> dict:
    """戦略分布 + 「進化で観察先行が増えたか」の honest 指標."""
    n_observe = n_naive = 0
    p_tools: list[float] = []
    skill_driven = 0
    n = 0
    for ind in individuals:
        bd = (ind.fitness.breakdown if ind.fitness else {}) or {}
        s = bd.get(_STRAT_KEY)
        if not isinstance(s, str):
            continue
        n += 1
        if s == "observe":
            n_observe += 1
        else:
            n_naive += 1
        pt = _coerce_float(bd.get(_PTOOL_KEY))
        sc = _coerce_float(bd.get(_SKILLDRV_KEY))
        if pt is not None:
            p_tools.append(pt)
        if sc is not None and sc > 1e-9:
            skill_driven += 1
    return {
        "n_observe": n_observe,
        "n_naive": n_naive,
        "observe_frac": round(n_observe / n, 4) if n else 0.0,
        "mean_p_tool": round(sum(p_tools) / len(p_tools), 4) if p_tools else 0.0,
        "strategy_skill_driven_frac": round(skill_driven / n, 4) if n else 0.0,
    }


# ---------------------------------------------------------------------------
# 1 条件 (evolved-strategy / naive-only) の進化 + 計測
# ---------------------------------------------------------------------------


@dataclass
class ConditionResult:
    name: str
    gen_curve: list[PopCoverage]
    strat_curve: list[dict]
    evolved_pop_cov: float
    peak_pop_cov: float
    best_single_cov: float
    gen0_cov: float
    elapsed: float


def build_single_loop_verdict(
    evolved_single_cov: float, naive_single_cov: float, eps: float = 1e-9,
) -> dict:
    """新主経路 (進化×単一 agentic ループ) verdict — 進化チャンピオンを 1 ループで deploy.

    オーケストラ (best-of-pop=k ループ) でなく **単一チャンピオン deploy=1 ループ** の
    コスト軽量経路 ([[goal_surpass_mythos_evolutionary]] 2026-05-28 ユーザー方針:
    オーケストラ Phase B 条件付き保留 → 進化×単一 agentic ループを Mythos 目標の主経路に)
    が成立するかを foreground する pure 関数。pop_coverage (orchestra) verdict と独立。
    進化チャンピオン (best individual) が naive 単一を上回ったか、+ deploy コスト記載。
    """
    delta = round(evolved_single_cov - naive_single_cov, 4)
    return {
        "evolved_champion_single_coverage": round(evolved_single_cov, 4),
        "naive_champion_single_coverage": round(naive_single_cov, 4),
        "delta(evolved-naive)": delta,
        "evolved_champion_beats_naive": delta > eps,
        "evolved_champion_ties_naive": abs(delta) <= eps,
        "deploy_cost": (
            "single multi-turn loop (1x); NOT population aggregation (kx). "
            "進化で得た単一個体を deploy → 推論コスト = 1 ループ = "
            "orchestra (best-of-pop) の 1/k。"),
        "note": (
            "オーケストラ (Phase B) 条件付き保留 (2026-05-28) に伴う主経路評価: "
            "進化が単一 deployable agentic 個体を naive 単一より引き上げたか。"
            "pop_coverage (orchestra) verdict とは独立に、deploy=1 ループ前提で測る。"),
    }


def _load_snapshots(out_dir: Path) -> list[tuple[int, list[Individual]]]:
    from llive.perf.evolutionary.population import Population

    snaps: list[tuple[int, list[Individual]]] = []
    for p in sorted(out_dir.glob("snapshot_gen_*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            pop = Population.from_dict(data)
            gen = int(data.get("generation", pop.generation))
            snaps.append((gen, list(pop.individuals)))
        except Exception as exc:  # noqa: BLE001
            print(f"  [warn] failed to read {p.name}: {exc}", file=sys.stderr)
    return snaps


def _run_one_condition(
    name: str,
    *,
    tasks: list[IntercodeTask],
    mock: bool,
    force_naive: bool,
    real_responder: RealResponder | None,
    args,  # noqa: ANN001
    out_dir: Path,
) -> ConditionResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    for p in out_dir.glob("snapshot_gen_*.json"):
        p.unlink()

    cache: dict[tuple[str, str, int], bool] = {}
    fitness_fn = make_intercode_agentic_fitness(
        tasks, mock=mock, force_naive=force_naive,
        real_responder=real_responder, real_model=args.model,
        max_turns=args.max_turns, timeout=args.timeout, cache=cache,
    )
    selector = build_lldarwin_v2_selector(LLDarwinV2Config(epsilon=args.epsilon))

    print(f"[poc_intercode_evo] === condition={name} "
          f"({'naive-only' if force_naive else 'evolved-strategy'}) ===")
    t0 = time.time()
    run_persona_evolution(
        args.personas,
        population_size=args.pop,
        generations=args.gens,
        seed=args.seed,
        out_dir=out_dir,
        fitness_fn=fitness_fn,
        is_proxy=False,
        genome3d=True,
        diverse_founder_prompts=True,
        selection=selector,
        lineage_reservoir=True,
        reinject_interval=1,
        persist_generation_log=True,
        checkpoint_every=1,
        patience=args.gens + 1,
        max_stall_generations=None,
    )
    elapsed = time.time() - t0

    snaps = _load_snapshots(out_dir)
    gen_curve = [measure_population_coverage(inds, g, tasks) for g, inds in snaps]
    strat_curve = [measure_strategy_distribution(inds) for _g, inds in snaps]
    best_single = max((g.best_individual_coverage for g in gen_curve), default=0.0)
    final = gen_curve[-1] if gen_curve else None
    return ConditionResult(
        name=name,
        gen_curve=gen_curve,
        strat_curve=strat_curve,
        evolved_pop_cov=final.pop_coverage if final else 0.0,
        peak_pop_cov=round(max((g.pop_coverage for g in gen_curve), default=0.0), 4),
        best_single_cov=round(best_single, 4),
        gen0_cov=round(gen_curve[0].pop_coverage if gen_curve else 0.0, 4),
        elapsed=elapsed,
    )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mock", action="store_true",
                    help="inference/Docker ゼロの canned 軌跡で配線/弁別ロジックを検証")
    ap.add_argument("--real", action="store_true",
                    help="on-prem ollama + Docker で実採点 (極小 配線確認のみ推奨; CPU は非現実的)")
    ap.add_argument("--pop", type=int, default=16, help="集団サイズ")
    ap.add_argument("--gens", type=int, default=12, help="進化世代数")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-tasks", type=int, default=7,
                    help="InterCode offline easy 帯から先頭 n 件")
    ap.add_argument("--max-turns", type=int, default=8,
                    help="1 タスクの最大ターン数 (multi-turn ループ)")
    ap.add_argument("--epsilon", type=float, default=0.0,
                    help="ε-lexicase の許容範囲 (0/1 case なので既定 0.0)")
    ap.add_argument("--model", default="qwen2.5:14b",
                    help="real の固定 ollama model (on-prem 最強)")
    ap.add_argument("--condition", default="both",
                    choices=("both", "evolved", "naive"),
                    help="both=evolved-strategy + naive-only 比較 (既定) / 片側")
    ap.add_argument("--host", default=None, help="ollama host (既定=env/localhost)")
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--timeout", type=float, default=30.0,
                    help="コンテナ実行 timeout 秒")
    ap.add_argument("--no-warmup", action="store_true",
                    help="warmup(max_tokens=1) を省く (極小 token warmup の hang 回避)")
    ap.add_argument("--repo", type=Path, default=_DEFAULT_REPO,
                    help="intercode repo path")
    ap.add_argument("--personas", nargs="+",
                    default=list(RESEARCH_METHODOLOGY_PERSONA_IDS),
                    help="founder にする persona id 列")
    ap.add_argument("--out", type=Path,
                    default=Path(r"D:/projects/llive/out/poc_intercode_evolution"))
    args = ap.parse_args(argv)

    if args.mock == args.real:
        if not args.real:
            args.mock = True
        else:
            ap.error("--mock と --real は排他です")

    mock = args.mock
    mode = "mock" if mock else "real"
    args.out.mkdir(parents=True, exist_ok=True)

    if not mock:
        if not docker_available():
            print("[poc_intercode_evo] ERROR: docker daemon に接続できません。",
                  file=sys.stderr)
            return 2
        if not image_present():
            print("[poc_intercode_evo] ERROR: image 'intercode-ctf' が無い。先に build:\n"
                  "  docker build -t intercode-ctf -f docker/ctf.fixed.Dockerfile .",
                  file=sys.stderr)
            return 2

    tasks = build_intercode_battery(args.max_tasks, repo=args.repo)
    file_backed_ids = [f"ic{t.task_id}" for t in tasks if t.file_backed]

    real_responder: RealResponder | None = None
    if not mock:
        real_responder = RealResponder(host=args.host, max_tokens=args.max_tokens)
        if not args.no_warmup:
            real_responder.warmup([args.model])

    print(f"[poc_intercode_evo] mode={mode} pop={args.pop} gens={args.gens} "
          f"tasks={len(tasks)} max_turns={args.max_turns} condition={args.condition} "
          f"ids={[t.task_id for t in tasks]} file_backed={file_backed_ids}")

    conditions: dict[str, ConditionResult] = {}
    if args.condition in ("both", "evolved"):
        conditions["evolved_strategy"] = _run_one_condition(
            "evolved_strategy", tasks=tasks, mock=mock, force_naive=False,
            real_responder=real_responder, args=args,
            out_dir=args.out / "evolved_strategy",
        )
    if args.condition in ("both", "naive"):
        conditions["naive_only"] = _run_one_condition(
            "naive_only", tasks=tasks, mock=mock, force_naive=True,
            real_responder=real_responder, args=args,
            out_dir=args.out / "naive_only",
        )

    evolved = conditions.get("evolved_strategy")
    naive = conditions.get("naive_only")
    verdict = None
    if evolved is not None and naive is not None:
        delta = round(evolved.evolved_pop_cov - naive.evolved_pop_cov, 4)
        peak_delta = round(evolved.peak_pop_cov - naive.peak_pop_cov, 4)
        verdict = {
            "evolved_strategy_pop_coverage": evolved.evolved_pop_cov,
            "naive_only_pop_coverage": naive.evolved_pop_cov,
            "delta(evolved-naive)": delta,
            "evolved_beats_naive": delta > 1e-9,
            "evolved_ties_naive": abs(delta) <= 1e-9,
            "evolved_strategy_peak_coverage": evolved.peak_pop_cov,
            "naive_only_peak_coverage": naive.peak_pop_cov,
            "delta_peak(evolved-naive)": peak_delta,
            "evolved_beats_naive_peak": peak_delta > 1e-9,
        }

    # 新主経路 verdict (オーケストラ条件付き保留に伴い 2026-05-28 追加): 進化で得た
    # 単一チャンピオンを 1 ループ deploy したカバレッジで naive 単一を超えるか。
    single_loop_verdict = None
    if evolved is not None and naive is not None:
        single_loop_verdict = build_single_loop_verdict(
            evolved.best_single_cov, naive.best_single_cov)

    calls = getattr(real_responder, "calls", 0) if real_responder else 0
    elapsed_total = sum(c.elapsed for c in conditions.values())

    def _cond_to_dict(c: ConditionResult) -> dict:
        return {
            "evolved_pop_coverage": c.evolved_pop_cov,
            "peak_pop_coverage": c.peak_pop_cov,
            "best_single_individual_coverage": c.best_single_cov,
            "gen0_coverage": c.gen0_cov,
            "generation_curve": [
                {
                    "generation": g.generation,
                    "pop_coverage": g.pop_coverage,
                    "best_individual_coverage": g.best_individual_coverage,
                    "n_specialist_taskmasks": g.n_specialist_taskmasks,
                    "n_observe": g.n_observe,
                    "n_naive": g.n_naive,
                    "solved_union": g.solved_union,
                    **{f"strat_{k}": v for k, v in s.items()},
                }
                for g, s in zip(c.gen_curve, c.strat_curve)
            ],
            "elapsed_seconds": round(c.elapsed, 2),
        }

    out = {
        "schema": "poc_intercode_evolution/v2",
        "benchmark": "InterCode-CTF (princeton-nlp/intercode, picoCTF tasks, MIT)",
        "phase": ("Phase D-1 next-(1) + 新主経路 single-loop verdict (2026-05-28, "
                  "オーケストラ Phase B 条件付き保留に伴う主経路評価追加)"),
        "proposition": (
            "個体 c_prompt から observe(観察先行)/naive(頭で当てる) の multi-turn agentic 戦略を "
            "発現させ、multi-turn InterCode オラクル (flag 一致) で ε-lexicase 進化させると、"
            "集団 coverage(best-of-pop) は naive に固定した同条件進化集団を上回る (= ε-lexicase が "
            "file-backed タスクの observe specialist を集団に保つ)。"),
        "mode": mode,
        "condition": args.condition,
        "pop": args.pop,
        "gens": args.gens,
        "max_turns": args.max_turns,
        "n_tasks": len(tasks),
        "task_ids": [t.task_id for t in tasks],
        "file_backed_ids": file_backed_ids,
        "epsilon": args.epsilon,
        "personas": list(args.personas),
        "model": args.model,
        "agentic_gene": {
            "mapping": ("c_prompt -> system prompt -> tool_propensity p_tool -> "
                        "observe (>=0.5: ls-first + submit self-check) / "
                        "naive (<0.5: guess-in-head, no observation/self-check)"),
            "threshold": _OBSERVE_THRESHOLD,
            "note": (
                "PoC-CTF-3 の code/direct 写像を multi-turn の observe/naive に流用 (同じ "
                "tool_propensity = 進化で動く c_prompt 由来連続次元)。observe = file-backed を "
                "ls→cat/grep で解く + 算術を self-check で救う / naive = 1-turn 失敗モード再現。"),
        },
        "lexicase_case": ("各 InterCode タスク = 1 case (ic::<tid> の 0/1)。"
                          "MultiPressureSelector が breakdown の数値キーを自動抽出 → "
                          "observe specialist が集団に保たれる。戦略 label は str 化 = case 化されない。"),
        "conditions": {name: _cond_to_dict(c) for name, c in conditions.items()},
        "verdict": verdict,
        "compute": {"llm_calls": calls, "elapsed_seconds": round(elapsed_total, 2)},
        "honest_notes": [
            "--mock 必須: 本ファイルの主用途は配線/弁別ロジック検証 (観察先行 vs naive を弁別し、"
            "進化で observe 個体が増えるロジック)。mock は canned 軌跡 = 実機予言ではない。",
            "real はフルでなく配線確認 or 極小。multi-turn 実機は ~88s/task (CPU) で pop x gens x "
            "task x turn = 数万秒 → CPU では非現実的・GPU 必須 (size_vram>0)。real は 1 個体 1 "
            "タスクの multi-turn fitness 配線が回るかの確認に限る。",
            "オラクルは run_multiturn_task 内の flag_oracle (multi-turn submit 採点) で不変 "
            "(設計 §10-1 指示どおり)。各タスク = 1 lexicase case (ic::<tid>)。",
            "戦略写像 observe/naive は PoC-CTF-3 の code/direct と同じ tool_propensity (c_prompt "
            "由来連続次元)。skill flip = 進化で動く実在次元 (主), hash = gen0 戦略分散の副次写像。",
            "自明帯では observe が満点飽和 → 進化の伸びしろ小 (PoC-0/1 教訓)。価値は file-backed が "
            "混じる非飽和帯 (実 picoCTF easy 帯) で出る。負なら負と報告 "
            "([[feedback_benchmark_honest_disclosure]])。",
            "MultiPressureSelector は breakdown の数値キー (ic::<tid>) のみ lexicase case に抽出。"
            "strategy label / p_tool (非数値 str) は case に混ざらない = 観測専用の安全配線。",
        ],
    }

    out_json = args.out / f"intercode_evolution_{mode}.json"
    out_json.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_summary_md(args.out / "SUMMARY.md", out)
    _print_summary(out)
    print(f"\n[poc_intercode_evo] wrote {out_json} "
          f"({elapsed_total:.1f}s, {calls} llm calls)")
    return 0


def _verdict_text(out: dict) -> str:
    v = out.get("verdict")
    if v is None:
        return "片側条件のみ (--condition != both) のため evolved vs naive 比較なし。"
    peak = (f" peak(全世代最良) は evolved {v['evolved_strategy_peak_coverage']:.3f} vs "
            f"naive {v['naive_only_peak_coverage']:.3f} "
            f"(delta_peak {v['delta_peak(evolved-naive)']:+.3f})。")
    if v["evolved_beats_naive"] or v["evolved_beats_naive_peak"]:
        head = ("**evolved-strategy が naive-only を coverage で上回った** "
                if v["evolved_beats_naive"] else
                "**evolved-strategy は最終世代では同点だが peak で naive-only を上回った** ")
        return (head + f"(最終 delta {v['delta(evolved-naive)']:+.3f}).{peak} "
                "ε-lexicase が『観察先行 (ls→cat/grep) で file-backed タスクを解く observe "
                "specialist』を集団に保ち、naive-only では構造的に解けない file-backed タスクを "
                "multi-turn 観察で被覆した = 設計 Phase D-1 next-(1)『make_agentic_fitness を "
                "multi-turn に配線』の mechanism を (この regime で) 実証。mock canned ゆえ "
                "実機予言ではない。")
    if v["evolved_ties_naive"]:
        return ("**evolved-strategy は naive-only と同点** "
                f"(最終 delta {v['delta(evolved-naive)']:+.3f}).{peak} この regime では observe 戦略の "
                "優位が coverage に出ない (タスクが naive でも解ける帯に飽和 / 戦略分布が動かない)。"
                "observe_frac と n_observe/n_naive を疑うこと "
                "([[feedback_benchmark_honest_disclosure]])。")
    return ("**evolved-strategy は naive-only を上回らなかった** "
            f"(最終 delta {v['delta(evolved-naive)']:+.3f}).{peak} observe 戦略進化の付加価値は "
            "この regime で不明瞭。honest にこの結果を残す。")


def _print_condition(name: str, cond: dict) -> None:
    print(f"\n----- condition={name} -----")
    print(f"{'gen':>4s} {'pop_cov':>8s} {'best_ind':>9s} {'spec':>5s} "
          f"{'obs':>4s} {'naive':>6s}  solved_union")
    for g in cond["generation_curve"]:
        print(f"{g['generation']:>4d} {g['pop_coverage']:>8.3f} "
              f"{g['best_individual_coverage']:>9.3f} {g['n_specialist_taskmasks']:>5d} "
              f"{g['n_observe']:>4d} {g['n_naive']:>6d}  {','.join(g['solved_union'])}")
    print(f"  evolved pop coverage = {cond['evolved_pop_coverage']:.3f}  "
          f"(peak {cond['peak_pop_coverage']:.3f}, "
          f"best single {cond['best_single_individual_coverage']:.3f}, "
          f"gen0 {cond['gen0_coverage']:.3f})")
    if cond["generation_curve"]:
        last = cond["generation_curve"][-1]
        print(f"  final observe_frac = {last.get('strat_observe_frac', 0.0):.2f}  "
              f"mean_p_tool = {last.get('strat_mean_p_tool', 0.0):.2f}  "
              f"skill_driven_frac = {last.get('strat_strategy_skill_driven_frac', 0.0):.2f}")


def _print_summary(out: dict) -> None:
    print("\n===== PoC InterCode multi-turn EVOLUTION SUMMARY =====")
    print(f"mode={out['mode']} condition={out['condition']} pop={out['pop']} "
          f"gens={out['gens']} n_tasks={out['n_tasks']} max_turns={out['max_turns']} "
          f"file_backed={out['file_backed_ids']}")
    for name, cond in out["conditions"].items():
        _print_condition(name, cond)
    v = out.get("verdict")
    if v is not None:
        mark = "+" if v["evolved_beats_naive"] else (
            "=" if v["evolved_ties_naive"] else "-")
        print(f"\nevolved-strategy coverage = {v['evolved_strategy_pop_coverage']:.3f} "
              f"(peak {v['evolved_strategy_peak_coverage']:.3f})")
        print(f"naive-only     coverage = {v['naive_only_pop_coverage']:.3f} "
              f"(peak {v['naive_only_peak_coverage']:.3f})")
        print(f"delta(evolved - naive) = {v['delta(evolved-naive)']:+.3f}  [{mark}]  "
              f"(peak delta {v['delta_peak(evolved-naive)']:+.3f})")
    print(f"\nVERDICT: {_verdict_text(out)}")


def _write_summary_md(path: Path, out: dict) -> None:
    v = out.get("verdict")
    lines = [
        "# PoC InterCode multi-turn — agentic 戦略の進化 (make_agentic_fitness を multi-turn に配線, honest)",
        "",
        f"- benchmark: **{out['benchmark']}**",
        f"- phase: **{out['phase']}**",
        f"- mode: **{out['mode']}** / condition={out['condition']} / pop={out['pop']} / "
        f"gens={out['gens']} / n_tasks={out['n_tasks']} / max_turns={out['max_turns']} / "
        f"epsilon={out['epsilon']}",
        f"- task_ids: {out['task_ids']} / file_backed: {out['file_backed_ids']}",
        f"- personas (founders): {', '.join(out['personas'])}",
        f"- model (real): `{out['model']}`",
        f"- compute: {out['compute']['llm_calls']} llm calls, "
        f"{out['compute']['elapsed_seconds']}s",
        "",
        "## 命題",
        "",
        "> " + out["proposition"],
        "",
        "## agentic 戦略遺伝子の写像",
        "",
        f"- {out['agentic_gene']['mapping']}",
        f"- threshold={out['agentic_gene']['threshold']}",
        f"- {out['agentic_gene']['note']}",
        f"- lexicase case: {out['lexicase_case']}",
        "",
        "## 結果 (coverage + 戦略分布)",
        "",
        "| 条件 | evolved coverage (最終) | peak coverage | best single | gen0 | "
        "final observe/naive | skill_driven |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, cond in out["conditions"].items():
        last = cond["generation_curve"][-1] if cond["generation_curve"] else {}
        lines.append(
            f"| {name} | **{cond['evolved_pop_coverage']:.3f}** | "
            f"{cond['peak_pop_coverage']:.3f} | "
            f"{cond['best_single_individual_coverage']:.3f} | "
            f"{cond['gen0_coverage']:.3f} | "
            f"{last.get('n_observe', 0)}/{last.get('n_naive', 0)} | "
            f"{last.get('strat_strategy_skill_driven_frac', 0.0):.2f} |"
        )
    if v is not None:
        mark = "上回る" if v["evolved_beats_naive"] else (
            "同点" if v["evolved_ties_naive"] else "上回らない")
        lines += [
            "",
            "## evolved vs naive (主指標)",
            "",
            f"- evolved-strategy coverage = {v['evolved_strategy_pop_coverage']:.3f} "
            f"(peak {v['evolved_strategy_peak_coverage']:.3f})",
            f"- naive-only coverage = {v['naive_only_pop_coverage']:.3f} "
            f"(peak {v['naive_only_peak_coverage']:.3f})",
            f"- delta(evolved - naive) = {v['delta(evolved-naive)']:+.3f} ({mark}) / "
            f"peak delta = {v['delta_peak(evolved-naive)']:+.3f}",
        ]
    lines += ["", "## VERDICT (honest)", "", _verdict_text(out), "",
              "## honest 留保", ""]
    lines += [f"- {n}" for n in out["honest_notes"]]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
