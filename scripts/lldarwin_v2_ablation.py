# SPDX-License-Identifier: Apache-2.0
"""lldarwin v2 ablation 実験 — 寄与率による最小コア探索.

北極星: 「連続進化 × ライブ MoA オーケストラ」の前提となる進化エンジンの健全性。

実験方針
--------
* proxy のみ (実 LLM なし = mechanism feasibility)。全結論に「proxy 限界」を明記。
* git commit/push しない。出力は out/ablation_2026_05_27/ 以下の tmp。
* 5 seed 平均で頑健性を確認 (1 seed の偶然で判断しない)。
* feedback_benchmark_honest_disclosure 準拠 (異常結果は内訳を疑う)。

3 指標
------
1. best_score_increment  : 末尾 30% 世代での best スコア増分 (飽和回避)
2. diversity_l2_mean     : 全世代平均の diversity_l2 (多様性維持)
3. final_pop_size        : 最終世代の個体数 (全滅回避)

追加指標 (MAP-Elites あり構成のみ)
4. map_elites_n_filled   : 最終 archive の occupied cells

ablation 構成
-------------
baseline       : 全 on (LLDarwinV2Config デフォルト)
no_novelty     : use_novelty=False
no_adaptive    : adaptive_difficulty=False
no_factor_sub  : factor_subspace_qd=False
no_reservoir   : lineage_reservoir=False
no_map_elites  : map_elites_archive=False (archive 無効; 選択器は baseline 同等)
tournament     : selection=None (lldarwin 全体 off = Tournament 対照群)

使い方
------
# フル実行 (5 seed × 7 構成 ≈ 数分)
py -3.11 scripts/lldarwin_v2_ablation.py

# 高速確認 (2 seed × 3 構成)
py -3.11 scripts/lldarwin_v2_ablation.py --seeds 0 1 --configs baseline no_novelty tournament

# 出力先を変える
py -3.11 scripts/lldarwin_v2_ablation.py --out D:/tmp/ablation_test
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

# --- パス設定 ---
_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from llive.perf.evolutionary.lldarwin_v2 import (
    LLDarwinV2Config,
    build_lldarwin_v2_selector,
)
from llive.perf.evolutionary.persona import RESEARCH_METHODOLOGY_PERSONA_IDS
from llive.perf.evolutionary.persona_evolution import (
    PersonaEvolutionResult,
    run_persona_evolution,
)
from llive.perf.evolutionary.pressures import make_pressure_fitness

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

DEFAULT_SEEDS: tuple[int, ...] = (0, 1, 2, 3, 4)
DEFAULT_POP_SIZE: int = 24
DEFAULT_GENERATIONS: int = 40

#: ALL_CONFIGS の定義順で表示する。
ALL_CONFIG_NAMES: tuple[str, ...] = (
    "baseline",
    "no_novelty",
    "no_adaptive",
    "no_factor_sub",
    "no_reservoir",
    "no_map_elites",
    "tournament",
)


# ---------------------------------------------------------------------------
# 構成ファクトリ
# ---------------------------------------------------------------------------


def _make_run_kwargs(config_name: str) -> dict[str, Any]:
    """構成名 → run_persona_evolution に渡す kwargs を返す.

    Returns
    -------
    dict
        ``selection``, ``map_elites``, ``lineage_reservoir``, ``reinject_interval``
        などの run_persona_evolution 引数。
    """
    if config_name == "baseline":
        cfg = LLDarwinV2Config()
        return dict(
            selection=build_lldarwin_v2_selector(cfg),
            map_elites=cfg.map_elites_archive,
            lineage_reservoir=cfg.lineage_reservoir,
            reinject_interval=cfg.reinject_interval,
        )

    if config_name == "no_novelty":
        cfg = LLDarwinV2Config(use_novelty=False)
        return dict(
            selection=build_lldarwin_v2_selector(cfg),
            map_elites=cfg.map_elites_archive,
            lineage_reservoir=cfg.lineage_reservoir,
            reinject_interval=cfg.reinject_interval,
        )

    if config_name == "no_adaptive":
        cfg = LLDarwinV2Config(adaptive_difficulty=False)
        return dict(
            selection=build_lldarwin_v2_selector(cfg),
            map_elites=cfg.map_elites_archive,
            lineage_reservoir=cfg.lineage_reservoir,
            reinject_interval=cfg.reinject_interval,
        )

    if config_name == "no_factor_sub":
        cfg = LLDarwinV2Config(factor_subspace_qd=False)
        return dict(
            selection=build_lldarwin_v2_selector(cfg),
            map_elites=cfg.map_elites_archive,
            lineage_reservoir=cfg.lineage_reservoir,
            reinject_interval=cfg.reinject_interval,
        )

    if config_name == "no_reservoir":
        cfg = LLDarwinV2Config(lineage_reservoir=False)
        return dict(
            selection=build_lldarwin_v2_selector(cfg),
            map_elites=cfg.map_elites_archive,
            lineage_reservoir=False,
            reinject_interval=cfg.reinject_interval,
        )

    if config_name == "no_map_elites":
        # archive は off、選択器は baseline と同等 (map_elites_archive フラグのみ off)
        cfg = LLDarwinV2Config(map_elites_archive=False)
        return dict(
            selection=build_lldarwin_v2_selector(cfg),
            map_elites=False,
            lineage_reservoir=cfg.lineage_reservoir,
            reinject_interval=cfg.reinject_interval,
        )

    if config_name == "tournament":
        # lldarwin 全体 off: selection=None → EvolutionLoop の既定 Tournament
        return dict(
            selection=None,
            map_elites=False,
            lineage_reservoir=False,
        )

    raise ValueError(f"unknown config_name: {config_name!r}")


# ---------------------------------------------------------------------------
# 指標抽出
# ---------------------------------------------------------------------------


def _extract_metrics(res: PersonaEvolutionResult, generations: int) -> dict[str, float]:
    """PersonaEvolutionResult から 3 (+1) 指標を抽出する.

    指標
    ----
    best_score_final     : 最終世代の best_score
    best_score_increment : 末尾 30% 世代での best スコア増分 (飽和回避指標)
                           末尾 30% の最大 − 最初の値。0 なら完全飽和。
    diversity_l2_mean    : 全世代平均 diversity_l2 (多様性維持)
    diversity_l2_final   : 最終世代の diversity_l2
    final_pop_size       : 最終世代の個体数 (全滅回避)
    stopped_reason       : 停止理由 (str)
    actual_generations   : 実際に回った世代数
    map_elites_n_filled  : MAP-Elites archive の occupied cells (archive なし = 0)
    saturation_gen       : best_score が初めて頭打ち (増分 < 1e-6) になった世代 (-1 なら未飽和)
    """
    er = res.evolution_result
    stats = er.stats_history  # list[PopulationStats] len = actual_gens + 1

    actual_gens = len(stats) - 1  # gen 0 含む (len = gens+1)
    if not stats:
        return {
            "best_score_final": 0.0,
            "best_score_increment": 0.0,
            "diversity_l2_mean": 0.0,
            "diversity_l2_final": 0.0,
            "final_pop_size": 0,
            "stopped_reason": "no_stats",
            "actual_generations": 0,
            "map_elites_n_filled": 0,
            "saturation_gen": -1,
        }

    best_scores = [s.best_score for s in stats]
    div_l2 = [s.diversity_l2 for s in stats]
    pop_sizes = [s.n_individuals for s in stats]

    # 末尾 30% 世代 (最低 1 世代)
    tail_start = max(0, int(len(stats) * 0.7))
    tail_best = best_scores[tail_start:]
    best_score_increment = float(max(tail_best) - tail_best[0]) if len(tail_best) >= 2 else 0.0

    # 飽和世代: best_score の増分が 1e-6 未満になった最初の世代
    saturation_gen = -1
    prev = best_scores[0]
    for i, bs in enumerate(best_scores[1:], 1):
        if abs(bs - prev) < 1e-6:
            saturation_gen = i
            break
        prev = bs

    map_elites_n_filled = 0
    if res.map_elites_archive is not None:
        map_elites_n_filled = int(res.map_elites_archive.n_filled)

    return {
        "best_score_final": float(best_scores[-1]),
        "best_score_increment": best_score_increment,
        "diversity_l2_mean": float(np.mean(div_l2)),
        "diversity_l2_final": float(div_l2[-1]),
        "final_pop_size": int(pop_sizes[-1]),
        "stopped_reason": er.stopped_reason,
        "actual_generations": actual_gens,
        "map_elites_n_filled": map_elites_n_filled,
        "saturation_gen": saturation_gen,
    }


# ---------------------------------------------------------------------------
# 1 run 実行
# ---------------------------------------------------------------------------


def run_one(
    config_name: str,
    seed: int,
    *,
    population_size: int = DEFAULT_POP_SIZE,
    generations: int = DEFAULT_GENERATIONS,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    """1 構成 × 1 seed を走らせて指標 dict を返す.

    Parameters
    ----------
    config_name : str
        ALL_CONFIG_NAMES のいずれか。
    seed : int
        RNG seed。
    population_size : int
        集団サイズ。
    generations : int
        進化世代数。
    out_dir : Path | None
        詳細ログの出力先。None なら何も書かない。

    Returns
    -------
    dict
        metrics + meta (config_name, seed, elapsed_s)。
    """
    run_dir = out_dir / config_name / f"seed_{seed}" if out_dir is not None else None
    if run_dir is not None:
        run_dir.mkdir(parents=True, exist_ok=True)

    kwargs = _make_run_kwargs(config_name)
    # patience/diversity_floor を無効化して指定世代を完走させる。
    # proxy は早く収束するため patience=generations+1 で実質無効化。
    kwargs.setdefault("is_proxy", True)

    t0 = time.perf_counter()
    res = run_persona_evolution(
        RESEARCH_METHODOLOGY_PERSONA_IDS,
        fitness_fn=make_pressure_fitness(),
        population_size=population_size,
        generations=generations,
        seed=seed,
        out_dir=run_dir,
        patience=generations + 1,  # 飽和しても完走
        diversity_floor=0.0,        # 多様性枯渇で止めない
        max_stall_generations=None, # 全個体一致でも止めない (ablation では世代数固定)
        **kwargs,
    )
    elapsed = time.perf_counter() - t0

    metrics = _extract_metrics(res, generations)
    metrics["config_name"] = config_name
    metrics["seed"] = seed
    metrics["elapsed_s"] = round(elapsed, 3)

    if run_dir is not None:
        (run_dir / "metrics_summary.json").write_text(
            json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    return metrics


# ---------------------------------------------------------------------------
# 寄与率計算
# ---------------------------------------------------------------------------


def _contribution_table(
    results: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    """baseline 対比の寄与率表を作る.

    Returns
    -------
    dict[config_name, dict[metric, contribution]]
        contribution = baseline[metric] - config[metric]
        正 = その要素を外すとその指標が下がる (= その要素が寄与している)
        負 = 外すと改善 (= その要素は有害または関係なし)
    """
    baseline = results.get("baseline", {})
    metrics = ["best_score_final", "best_score_increment", "diversity_l2_mean"]
    table: dict[str, dict[str, float]] = {}
    for cfg_name, cfg_metrics in results.items():
        if cfg_name == "baseline":
            table[cfg_name] = {m: 0.0 for m in metrics}
            continue
        row: dict[str, float] = {}
        for m in metrics:
            bv = baseline.get(m, 0.0)
            cv = cfg_metrics.get(m, 0.0)
            row[m] = round(bv - cv, 6)
        table[cfg_name] = row
    return table


# ---------------------------------------------------------------------------
# レポート生成
# ---------------------------------------------------------------------------


def _generate_report(
    per_seed_results: dict[str, list[dict]],
    avg_results: dict[str, dict[str, float]],
    contribution: dict[str, dict[str, float]],
    seeds: list[int],
    population_size: int,
    generations: int,
    out_dir: Path,
) -> str:
    """Markdown レポートを生成して返す。"""
    lines: list[str] = []
    lines.append("# lldarwin v2 Ablation Report")
    lines.append("")
    lines.append(f"日付: 2026-05-27  設定: pop={population_size}, gens={generations}, seeds={seeds}")
    lines.append("")
    lines.append("> **HONEST DISCLOSURE**: 本実験は proxy fitness のみ使用 (LLM 不使用)。")
    lines.append("> 「mechanism feasibility」= 選択アルゴリズムが proxy 指標で機能するか の検証。")
    lines.append("> 実 LLM 評価との相関は保証されない。結論は全て proxy 限界付きで解釈すること。")
    lines.append("")

    # --- 平均指標表 ---
    lines.append("## 1. 平均指標表 (5 seed 平均)")
    lines.append("")
    col_order = [
        "best_score_final",
        "best_score_increment",
        "diversity_l2_mean",
        "diversity_l2_final",
        "final_pop_size",
        "saturation_gen",
        "map_elites_n_filled",
    ]
    col_labels = {
        "best_score_final": "best_final",
        "best_score_increment": "best_incr(tail30%)",
        "diversity_l2_mean": "div_l2_mean",
        "diversity_l2_final": "div_l2_final",
        "final_pop_size": "pop_size",
        "saturation_gen": "sat_gen",
        "map_elites_n_filled": "me_filled",
    }
    header = "| 構成 | " + " | ".join(col_labels[c] for c in col_order) + " |"
    sep    = "| --- | " + " | ".join(["---"] * len(col_order)) + " |"
    lines.append(header)
    lines.append(sep)
    for cfg_name in ALL_CONFIG_NAMES:
        if cfg_name not in avg_results:
            continue
        vals = avg_results[cfg_name]
        row_vals = []
        for c in col_order:
            v = vals.get(c, float("nan"))
            if c == "saturation_gen":
                row_vals.append(f"{int(v)}" if v >= 0 else "未飽和")
            elif c in ("final_pop_size", "map_elites_n_filled"):
                row_vals.append(f"{int(v)}")
            else:
                row_vals.append(f"{v:.4f}")
        lines.append(f"| {cfg_name} | " + " | ".join(row_vals) + " |")
    lines.append("")

    # --- 寄与率表 ---
    lines.append("## 2. 寄与率表 (baseline − 構成, 3 指標)")
    lines.append("")
    lines.append("正 = その要素が baseline に寄与している (外すと指標が下がる)")
    lines.append("負 = 外すと改善または無関係")
    lines.append("")
    contrib_metrics = ["best_score_final", "best_score_increment", "diversity_l2_mean"]
    header2 = "| 構成 | " + " | ".join(col_labels[c] for c in contrib_metrics) + " | 合計寄与 |"
    sep2    = "| --- | " + " | ".join(["---"] * len(contrib_metrics)) + " | --- |"
    lines.append(header2)
    lines.append(sep2)
    for cfg_name in ALL_CONFIG_NAMES:
        if cfg_name == "baseline" or cfg_name not in contribution:
            continue
        row = contribution[cfg_name]
        vals_row = [f"{row.get(m, 0.0):+.4f}" for m in contrib_metrics]
        total = sum(row.get(m, 0.0) for m in contrib_metrics)
        lines.append(f"| {cfg_name} | " + " | ".join(vals_row) + f" | {total:+.4f} |")
    lines.append("")

    # --- 各要素の判定 ---
    lines.append("## 3. 各要素の寄与判定")
    lines.append("")
    judgments: dict[str, str] = {}
    for cfg_name in ALL_CONFIG_NAMES:
        if cfg_name in ("baseline", "tournament"):
            continue
        row = contribution.get(cfg_name, {})
        total = sum(row.get(m, 0.0) for m in contrib_metrics)
        best_incr_contrib = row.get("best_score_increment", 0.0)
        div_contrib = row.get("diversity_l2_mean", 0.0)

        # 判定ルール:
        # 必須: total > 0.02 かつ (best_incr_contrib > 0.001 or div_contrib > 0.001)
        # 有害: total < 0 (外すと改善 = 含まれると有害)
        # 削減候補: 0 <= total < 0.005 (寄与微小)
        # 補助: その間
        if total > 0.02 and (best_incr_contrib > 0.001 or div_contrib > 0.001):
            verdict = "**必須** — 外すと飽和/多様性が有意に低下"
        elif total < 0:
            verdict = "**削減候補 (有害方向)** — 外した方が指標が改善 (proxy 限定)"
        elif total < 0.005:
            verdict = "**削減候補** — 寄与微小 (proxy スケールでは必要性薄)"
        else:
            verdict = "**補助** — 小〜中程度の寄与"

        judgments[cfg_name] = verdict
        # 要素名マッピング
        element_name = {
            "no_novelty": "novelty (z-score 標準化)",
            "no_adaptive": "adaptive_difficulty (条件カリキュラム)",
            "no_factor_sub": "factor_subspace_qd (意味次元 QD ブレンド)",
            "no_reservoir": "lineage_reservoir (系統中立貯蔵庫)",
            "no_map_elites": "map_elites_archive (QD アーカイブ)",
        }.get(cfg_name, cfg_name)
        lines.append(f"- **{element_name}** (`{cfg_name}`): {verdict}")
    lines.append("")

    # --- tournament 対照群 ---
    if "tournament" in avg_results:
        t_vals = avg_results["tournament"]
        b_vals = avg_results.get("baseline", {})
        lines.append("### Tournament 対照群")
        lines.append("")
        lines.append(
            f"- baseline best_final={b_vals.get('best_score_final', 0):.4f} vs "
            f"tournament={t_vals.get('best_score_final', 0):.4f}"
        )
        lines.append(
            f"- diversity_l2_mean: baseline={b_vals.get('diversity_l2_mean', 0):.4f} vs "
            f"tournament={t_vals.get('diversity_l2_mean', 0):.4f}"
        )
        lines.append("")

    # --- 最小コア候補 ---
    lines.append("## 4. 破綻しない最小コア候補")
    lines.append("")
    # 削減候補を自動抽出
    removable = [
        cfg for cfg in ALL_CONFIG_NAMES
        if cfg not in ("baseline", "tournament")
        and contribution.get(cfg, {})
        and sum(contribution[cfg].get(m, 0.0) for m in contrib_metrics) < 0.005
    ]
    essential = [
        cfg for cfg in ALL_CONFIG_NAMES
        if cfg not in ("baseline", "tournament")
        and cfg not in removable
    ]

    _cfg_to_elem_short = {
        "no_novelty": "novelty",
        "no_adaptive": "adaptive_difficulty",
        "no_factor_sub": "factor_subspace_qd",
        "no_reservoir": "lineage_reservoir",
        "no_map_elites": "map_elites_archive",
    }
    if removable:
        lines.append(
            "削減候補 (寄与率 < 0.005 または有害方向、外しても破綻リスク低): "
            + ", ".join(_cfg_to_elem_short.get(c, c) for c in removable)
        )
        lines.append(
            "最小コア (残すべき要素): "
            + ", ".join(
                _cfg_to_elem_short.get(c, c) for c in (essential if essential else ["—"])
            )
        )
    else:
        lines.append("全要素が寄与率 >= 0.005: 最小コアは baseline 全構成が妥当。")
    lines.append("")
    lines.append("> **破綻境界**: 複数要素を同時に外す組み合わせ実験 (combo ablation) は")
    lines.append("> 本実験スコープ外。最小コア候補は 1 要素 off の推定のみ。")
    lines.append("> 実際の破綻境界は combo ablation (次ステップ) で確認すること。")
    lines.append("")

    # --- frozen 候補 ---
    lines.append("## 5. frozen 候補にできる要素")
    lines.append("")
    lines.append(
        "frozen = 「寄与率が一定以上あり、proxy スケールで挙動が安定している = "
        "チューニング不要で凍結できる」要素。"
    )
    lines.append("")
    _cfg_to_element = {
        "no_novelty": "novelty",
        "no_adaptive": "adaptive_difficulty",
        "no_factor_sub": "factor_subspace_qd",
        "no_reservoir": "lineage_reservoir",
        "no_map_elites": "map_elites_archive",
    }
    frozen_candidates = [
        cfg for cfg in essential
        if avg_results.get(cfg, {}).get("diversity_l2_mean", 0) > 0.0  # 多様性への寄与あり
    ]
    if frozen_candidates:
        lines.append(
            "frozen 候補 (要素名): "
            + ", ".join(_cfg_to_element.get(cfg, cfg) for cfg in frozen_candidates)
        )
    else:
        lines.append("今回の proxy 実験では frozen 候補を特定できなかった (実 LLM 実験が必要)。")
    lines.append("")

    # --- proxy 限界 ---
    lines.append("## 6. Proxy 限界 (Honest Disclosure)")
    lines.append("")
    lines.append(
        "本実験の fitness は `make_pressure_fitness()` による決定論的 proxy。"
        "思考因子の均衡スコアを返すだけであり、実 LLM タスク評価ではない。"
    )
    lines.append(
        "具体的な限界:"
    )
    lines.append(
        "1. **Goodhart リスク**: proxy はゲノム空間を直接測るため、novelty や多様性を"
        "「ゲノム座標の分散」として評価する。実 LLM の出力多様性・能力とは異なる可能性が高い。"
    )
    lines.append(
        "2. **飽和が早い**: proxy の値域は狭く (balance * (1 - std))、実 LLM より"
        "早期に best=1.0 近傍に到達しやすい。饱和世代 (saturation_gen) の絶対値は"
        "実 LLM ランとは直接比較できない。"
    )
    lines.append(
        "3. **lineage_reservoir の寄与**: proxy では全個体が同一の決定論的 fitness を"
        "返すため、系統固定圧が弱い。実 LLM では fitness の個体差が大きいため"
        "reservoir の寄与が更に大きくなる可能性がある。"
    )
    lines.append(
        "4. **map_elites の役割**: proxy では archive の多様性指標が選択圧に再帰しないため"
        "archive の寄与率が低く出やすい。実 LLM ランでの archive ベースの"
        "multi-criteria selection では寄与が逆転する可能性。"
    )
    lines.append(
        "5. **seed 変動**: 5 seed 平均だが、proxy の確定論的性質から seed 間分散が"
        "実 LLM より小さい。実 LLM ランでは分散が増え、各判定の信頼区間が広がる。"
    )
    lines.append("")
    lines.append("**結論の使い方**: 「proxy で寄与率が高い要素は実 LLM でも必須候補」だが、")
    lines.append("「proxy で削減候補」= 実 LLM でも不要 とは**言えない**。")
    lines.append("proxy 結果は実 LLM 実験の仮説生成と設計ガイドとして使う。")
    lines.append("")

    # --- seed-by-seed 詳細 (折り畳み) ---
    lines.append("## 7. Seed 別詳細 (raw)")
    lines.append("")
    lines.append("<details>")
    lines.append("<summary>展開して表示</summary>")
    lines.append("")
    for cfg_name in ALL_CONFIG_NAMES:
        per_seed = per_seed_results.get(cfg_name, [])
        if not per_seed:
            continue
        lines.append(f"### {cfg_name}")
        lines.append("")
        lines.append("```")
        for r in per_seed:
            lines.append(json.dumps(r, ensure_ascii=False))
        lines.append("```")
        lines.append("")
    lines.append("</details>")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# メインルーティン
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """ablation 実験を実行してレポートを書く."""
    # UTF-8 stdout 保証 (Windows cp932 対策)
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    parser = argparse.ArgumentParser(description="lldarwin v2 ablation experiment")
    parser.add_argument(
        "--seeds",
        nargs="+",
        type=int,
        default=list(DEFAULT_SEEDS),
        help=f"RNG seeds (default: {list(DEFAULT_SEEDS)})",
    )
    parser.add_argument(
        "--configs",
        nargs="+",
        default=list(ALL_CONFIG_NAMES),
        choices=list(ALL_CONFIG_NAMES),
        help="実行する構成 (default: 全構成)",
    )
    parser.add_argument(
        "--pop",
        type=int,
        default=DEFAULT_POP_SIZE,
        help=f"集団サイズ (default: {DEFAULT_POP_SIZE})",
    )
    parser.add_argument(
        "--gens",
        type=int,
        default=DEFAULT_GENERATIONS,
        help=f"進化世代数 (default: {DEFAULT_GENERATIONS})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("D:/projects/llive/out/ablation_2026_05_27"),
        help="出力ディレクトリ",
    )
    parser.add_argument(
        "--no-detail",
        action="store_true",
        help="詳細ログ (winners.jsonl 等) を書かない",
    )
    args = parser.parse_args(argv)

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    detail_dir = None if args.no_detail else out_dir / "detail"

    seeds: list[int] = args.seeds
    configs: list[str] = args.configs
    pop_size: int = args.pop
    generations: int = args.gens

    total_runs = len(configs) * len(seeds)
    print(
        f"[ablation] 開始: {len(configs)} 構成 × {len(seeds)} seed = {total_runs} run",
        flush=True,
    )
    print(f"           pop={pop_size}, gens={generations}, out={out_dir}", flush=True)

    per_seed_results: dict[str, list[dict]] = {c: [] for c in configs}
    run_idx = 0
    t_total_start = time.perf_counter()

    for cfg_name in configs:
        for seed in seeds:
            run_idx += 1
            print(
                f"  [{run_idx:02d}/{total_runs:02d}] {cfg_name} seed={seed} ...",
                end=" ",
                flush=True,
            )
            try:
                metrics = run_one(
                    cfg_name,
                    seed,
                    population_size=pop_size,
                    generations=generations,
                    out_dir=detail_dir,
                )
                per_seed_results[cfg_name].append(metrics)
                print(
                    f"best={metrics['best_score_final']:.4f} "
                    f"div={metrics['diversity_l2_mean']:.4f} "
                    f"elapsed={metrics['elapsed_s']:.1f}s",
                    flush=True,
                )
            except Exception as exc:
                print(f"ERROR: {exc}", flush=True)
                per_seed_results[cfg_name].append(
                    {"config_name": cfg_name, "seed": seed, "error": str(exc)}
                )

    elapsed_total = time.perf_counter() - t_total_start
    print(f"\n[ablation] 完了: 合計 {elapsed_total:.1f}s", flush=True)

    # --- 平均集計 ---
    metric_keys = [
        "best_score_final",
        "best_score_increment",
        "diversity_l2_mean",
        "diversity_l2_final",
        "final_pop_size",
        "saturation_gen",
        "map_elites_n_filled",
    ]
    avg_results: dict[str, dict[str, float]] = {}
    for cfg_name, runs in per_seed_results.items():
        valid = [r for r in runs if "error" not in r]
        if not valid:
            continue
        avg: dict[str, float] = {}
        for k in metric_keys:
            vals = [r[k] for r in valid if k in r]
            avg[k] = float(np.mean(vals)) if vals else float("nan")
        avg_results[cfg_name] = avg

    # --- 寄与率 ---
    contribution = _contribution_table(avg_results)

    # --- raw JSON 保存 ---
    raw_json = {
        "seeds": seeds,
        "configs": configs,
        "population_size": pop_size,
        "generations": generations,
        "per_seed_results": per_seed_results,
        "avg_results": {k: {mk: float(v) for mk, v in mv.items()} for k, mv in avg_results.items()},
        "contribution": {k: {mk: float(v) for mk, v in mv.items()} for k, mv in contribution.items()},
    }
    raw_path = out_dir / "ablation_raw.json"
    raw_path.write_text(json.dumps(raw_json, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[ablation] raw JSON: {raw_path}", flush=True)

    # --- Markdown レポート ---
    report_text = _generate_report(
        per_seed_results=per_seed_results,
        avg_results=avg_results,
        contribution=contribution,
        seeds=seeds,
        population_size=pop_size,
        generations=generations,
        out_dir=out_dir,
    )
    report_path = Path("D:/projects/llive/docs/research/lldarwin_v2_ablation_2026_05_27.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_text, encoding="utf-8")
    print(f"[ablation] レポート: {report_path}", flush=True)

    # --- サマリ表示 ---
    print("\n=== 寄与率サマリ (baseline − 構成) ===", flush=True)
    contrib_metrics = ["best_score_final", "best_score_increment", "diversity_l2_mean"]
    header = f"{'構成':<20} " + "  ".join(f"{m[:16]:<16}" for m in contrib_metrics) + "  合計"
    print(header, flush=True)
    print("-" * len(header), flush=True)
    for cfg_name in ALL_CONFIG_NAMES:
        if cfg_name == "baseline" or cfg_name not in contribution:
            continue
        row = contribution[cfg_name]
        vals = [f"{row.get(m, 0.0):+.4f}" for m in contrib_metrics]
        total = sum(row.get(m, 0.0) for m in contrib_metrics)
        print(f"{cfg_name:<20} " + "  ".join(f"{v:<16}" for v in vals) + f"  {total:+.4f}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
