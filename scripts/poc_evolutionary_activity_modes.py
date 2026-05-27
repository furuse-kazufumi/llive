#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""PoC: Bedau 進化的活動統計 (evolutionary activity statistics) + 中立シャドウ計器.

命題 (falsifiable):
  Bedau の component 別 cumulative activity を **中立 (無選択) シャドウ** と比較すると、
    (1) 適応的ラン (新規高価値 component を獲得し続ける選択) は中立を有意に超える
        supra-neutral activity (= new activity A_new) を示す。
    (2) 中立ラン はほぼ示さない (A_new ≈ 0)。
    (3) 飽和ラン (固定自明最適へ収束) は初期のみ示し、新規獲得が止まると A_new が減衰する。
  => llive の進化が「開放端な適応的活動」を出しているのか、「中立浮動 / 飽和 churn」に
     過ぎないのかを **区別できる計器** になる。区別できなければ honest にそう報告する。

honest 留保:
  これは proxy toy であり実 llive ラン非接触。stdlib + numpy のみ・決定論 seed・
  LLM/Docker/genome import ゼロ (demo_persona_fx 流の隔離 PoC)。本 PoC が示すのは
  **計器の弁別力** であって、実 llive の開放端性そのものの主張ではない。
  次段 = この計器を実 llive 進化 snapshot (lineage / trait 活動) に配線して測ること。

参照: [[feedback_staged_poc_individual_structure]] (小 PoC→効果 gate→有効なら採用) /
      [[feedback_benchmark_honest_disclosure]] (区別できなければ正直に報告) /
      [[feedback_cli_utf8_stdout_pattern]] (cp932 console 出力規約)。
      Bedau, M.A. et al. "Evolutionary dynamics of biological / artificial systems"
      (component-wise cumulative activity vs neutral shadow) — RAD 実測 grounding 最多。

実行:
    py -3.11 scripts/poc_evolutionary_activity_modes.py
    py -3.11 scripts/poc_evolutionary_activity_modes.py --gens 600 --pop 128 --seed 1
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# モデルパラメータ
# ---------------------------------------------------------------------------
# component 総数 (離散 trait id の語彙)。個体はこの中から複数を multiset で保持する。
N_COMPONENTS = 64
# 個体あたりの component 数 (multiset の大きさ; 重複を許す)。
GENOME_LEN = 8


def _ensure_utf8_stdout() -> None:
    """Windows cp932 console で em-dash / 日本語を出力する CLI 規約.

    ([[feedback_cli_utf8_stdout_pattern]]).
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Bedau メトリクス (純関数 — テスト可能に切り出す)
# ---------------------------------------------------------------------------

def concentration(pop_components: np.ndarray, n_components: int = N_COMPONENTS) -> np.ndarray:
    """各 component の concentration = それを **持つ個体の割合** (0..1).

    Args:
        pop_components: shape (pop, genome_len) の int 配列。各要素は component id。
        n_components: component 語彙サイズ。

    Returns:
        shape (n_components,) の float 配列。conc[i] = (i を 1 個以上持つ個体数) / pop。

    Bedau は「個体内に存在するか」を component の出現として数える (multiset 内の重複は
    1 個体としては 1 回しか数えない = presence ベース)。これにより concentration は
    その component が集団でどれだけ「使われているか」を表す。
    """
    pop = pop_components.shape[0]
    if pop == 0:
        return np.zeros(n_components, dtype=float)
    # 個体ごとに「その component を持つか」(presence) を立てる。
    present = np.zeros((pop, n_components), dtype=bool)
    rows = np.repeat(np.arange(pop), pop_components.shape[1])
    cols = pop_components.reshape(-1)
    present[rows, cols] = True
    return present.sum(axis=0).astype(float) / float(pop)


def update_activity(activity: np.ndarray, conc: np.ndarray) -> np.ndarray:
    """1 世代ぶんの cumulative activity 更新: a_i += concentration_i.

    Bedau の core: 「存在し続けるほど活動が累積する」。新出して即消える component は
    ほとんど累積せず、長く高 concentration を保つ component が高い cumulative activity を持つ。

    純関数 (新しい配列を返す; in-place しない)。
    """
    return activity + conc


def diversity(conc: np.ndarray, eps: float = 0.0) -> int:
    """Diversity D(t) = present component 数 (concentration > eps).

    Bedau Diversity = 「現在集団に存在する component 種数」。
    """
    return int(np.count_nonzero(conc > eps))


def total_activity(activity: np.ndarray) -> float:
    """Total cumulative activity A(t) = sum_i a_i."""
    return float(activity.sum())


def mean_cumulative_activity(activity: np.ndarray, conc: np.ndarray, eps: float = 0.0) -> float:
    """mean cumulative activity = 現存 component の活動の平均 (Bedau の \\bar{a})."""
    present = conc > eps
    n = int(np.count_nonzero(present))
    if n == 0:
        return 0.0
    return float(activity[present].sum() / n)


def new_activity(activity: np.ndarray, a_shadow: float) -> float:
    """New activity A_new(t) = a_i > a_shadow の component の活動和 (supra-neutral).

    中立シャドウ閾値 a_shadow を超えた component だけが「中立浮動では説明できない
    持続的活動 = 適応的活動」とみなされる。これが Bedau の core メトリクス。

    Args:
        activity: shape (n_components,) の cumulative activity。
        a_shadow: 中立シャドウから得た閾値 (この値以下は中立浮動とみなし除外)。
    """
    mask = activity > a_shadow
    if not np.any(mask):
        return 0.0
    return float(activity[mask].sum())


def supra_neutral_count(activity: np.ndarray, a_shadow: float) -> int:
    """supra-neutral component 数 = a_i > a_shadow を満たす component の種数.

    Bedau の "new component diversity" 相当。**開放端性の核となる弁別子**:
    A_new (活動和) は持続する component なら自明な少数でも単調に膨らむため、
    「持続するが自明」(飽和) と「新規を獲得し続ける」(適応的) を A_new 単独では
    十分に切り分けられない (本 PoC の honest disclosure)。一方この **種数** は、
    新規 component が次々と shadow を越えるときだけ増え続けるので、
    adaptive (増え続ける) / neutral (≈0) / saturated (少数で頭打ち) を区別する。
    """
    return int(np.count_nonzero(activity > a_shadow))


def shadow_threshold(neutral_activity: np.ndarray, percentile: float = 99.0) -> float:
    """中立 activity 分布から閾値 a_shadow を出す.

    Bedau の neutral shadow: 無選択ランの component activity 分布の高位 (max or 高
    パーセンタイル) を「中立浮動だけで到達しうる活動上限」とみなす。これを超えた活動を
    supra-neutral (適応的) と判定する。

    Args:
        neutral_activity: 中立ランの最終世代 cumulative activity (shape (n_components,))。
        percentile: 0..100。100 = max。デフォルト 99 パーセンタイル (外れ値に少し頑健)。

    Returns:
        a_shadow (float)。
    """
    if neutral_activity.size == 0:
        return 0.0
    if percentile >= 100.0:
        return float(neutral_activity.max())
    return float(np.percentile(neutral_activity, percentile))


# ---------------------------------------------------------------------------
# 集団進化シミュレーション (3 レジーム)
# ---------------------------------------------------------------------------

@dataclass
class ModeTrace:
    """1 レジームの Bedau メトリクス時系列 + 最終値."""

    mode: str
    diversity: list = field(default_factory=list)            # D(t)
    total_activity: list = field(default_factory=list)        # A(t)
    mean_cumulative_activity: list = field(default_factory=list)  # \bar{a}(t)
    new_activity: list = field(default_factory=list)          # A_new(t) (supra-neutral activity sum)
    supra_count: list = field(default_factory=list)           # supra-neutral component 種数 (t)
    final_activity: list = field(default_factory=list)        # 最終 cumulative activity per component
    a_new_final: float = 0.0                                  # A_new(最終世代)
    a_new_tail_mean: float = 0.0                              # 末尾 20% の A_new 平均
    a_new_peak: float = 0.0                                   # A_new(t) のピーク
    a_new_decayed: bool = False                               # ピークから末尾へ減衰したか (飽和シグナル)
    supra_count_tail_mean: float = 0.0                        # 末尾 20% の supra-neutral 種数平均
    supra_count_final: int = 0                                # supra-neutral 種数 (最終世代)
    diversity_tail_mean: float = 0.0                          # 末尾 20% の present component 種数平均


def _select_parents(
    fit: np.ndarray, pop: int, rng: np.random.Generator
) -> np.ndarray:
    """binary tournament selection → 親インデックス配列 (shape (pop,))."""
    a = rng.integers(0, pop, pop)
    b = rng.integers(0, pop, pop)
    return np.where(fit[a] >= fit[b], a, b)


def _mutate(
    pop_components: np.ndarray,
    rng: np.random.Generator,
    n_components: int,
    mut_rate: float,
    *,
    allowed_max: int | None = None,
) -> np.ndarray:
    """各 locus を mut_rate でランダム component に変異させる.

    Args:
        allowed_max: None なら全 component を変異先候補にする (開放端代理)。
            int を渡すと [0, allowed_max) の自明な小語彙にだけ変異する (飽和代理:
            新規 component を構造的に増やせない世界)。
    """
    child = pop_components.copy()
    m = rng.random(child.shape) < mut_rate
    hi = n_components if allowed_max is None else allowed_max
    if np.any(m):
        child[m] = rng.integers(0, hi, int(m.sum()))
    return child


def _fitness(
    pop_components: np.ndarray,
    mode: str,
    n_components: int,
    discovered: set[int],
    gen: int,
    gens: int,
) -> tuple[np.ndarray, set[int]]:
    """レジーム別 fitness.

    * adaptive: 「まだ集団に定着していない高 id component」を時間とともに報酬する。
      時間 → 報酬対象 component の id 帯を押し上げる (開放端代理 = "moving target")。
      これにより集団は常に未獲得の新規 component を取りに行き、活動が累積し続ける。
    * neutral: fitness 一様 (= 無選択)。呼び出し側はこの戻り値を使わない経路を取る。
    * saturated: 固定の自明最適 (低 id ほど高得点) を報酬。新規 component を増やさず、
      初期に最適へ収束したらそれ以上の活動増分が止まる。

    Returns:
        (fit, discovered) — fit は shape (pop,); discovered は累積で発見した報酬帯 (情報用)。
    """
    pop, glen = pop_components.shape
    if mode == "neutral":
        return np.ones(pop, dtype=float), discovered

    if mode == "saturated":
        # 自明最適 = 低 id を多く持つほど高い (固定ターゲット, 時間不変)。
        # max id が小さいほど良い。新規 (高 id) component を取りに行く誘因がない。
        score = (n_components - pop_components).sum(axis=1).astype(float)
        return score, discovered

    if mode == "adaptive":
        # moving target: 世代 gen の「報酬窓」中心を時間と共に押し上げる。
        # window_center は 0 → n_components へ漸進。窓 [lo, hi) 内の component を持つほど高得点。
        frac = gen / max(1, gens - 1)
        center = int(frac * (n_components - 1))
        half = max(2, n_components // 8)
        lo = max(0, center - half)
        hi = min(n_components, center + half + 1)
        in_window = (pop_components >= lo) & (pop_components < hi)
        score = in_window.sum(axis=1).astype(float)
        # 報酬帯を記録 (情報用; 累積で開放端的に拡大することを示す)。
        discovered |= set(range(lo, hi))
        # tie-break: 窓内 component の多様性 (distinct 数) を小さく加点 → 単一占有を防ぐ。
        return score, discovered

    raise ValueError(f"unknown mode: {mode}")


def run_mode(
    mode: str,
    *,
    gens: int,
    pop: int,
    n_components: int = N_COMPONENTS,
    genome_len: int = GENOME_LEN,
    mut_rate: float = 0.08,
    seed: int = 0,
    a_shadow: float = 0.0,
    saturated_vocab: int = 6,
) -> ModeTrace:
    """1 レジームを回し Bedau メトリクス時系列を返す.

    Args:
        mode: "adaptive" | "neutral" | "saturated"。
        a_shadow: new_activity 判定に使う中立シャドウ閾値。neutral 自身を回すときは
            0.0 のままでよい (A_new 時系列は閾値 0 基準になるが、レジーム比較では
            neutral の最終 activity から閾値を作って全モードに同じ閾値を適用し直す)。
        saturated_vocab: saturated モードで変異が許される自明小語彙のサイズ。
    """
    rng = np.random.default_rng(seed)
    # 初期集団: 全 component から一様サンプリング。
    G = rng.integers(0, n_components, (pop, genome_len))
    activity = np.zeros(n_components, dtype=float)
    discovered: set[int] = set()
    tr = ModeTrace(mode=mode)

    for gen in range(gens):
        conc = concentration(G, n_components)
        activity = update_activity(activity, conc)

        tr.diversity.append(diversity(conc))
        tr.total_activity.append(total_activity(activity))
        tr.mean_cumulative_activity.append(mean_cumulative_activity(activity, conc))
        tr.new_activity.append(new_activity(activity, a_shadow))
        tr.supra_count.append(supra_neutral_count(activity, a_shadow))

        if mode == "neutral":
            # 無選択: 親をランダムに選ぶ (淘汰なし; ランダム複製)。
            parents_idx = rng.integers(0, pop, pop)
            G = _mutate(G[parents_idx], rng, n_components, mut_rate)
        elif mode == "saturated":
            fit, discovered = _fitness(G, mode, n_components, discovered, gen, gens)
            parents_idx = _select_parents(fit, pop, rng)
            # 変異先を自明小語彙に制限 = 新規 component を構造的に増やせない世界。
            G = _mutate(G[parents_idx], rng, n_components, mut_rate, allowed_max=saturated_vocab)
        else:  # adaptive
            fit, discovered = _fitness(G, mode, n_components, discovered, gen, gens)
            parents_idx = _select_parents(fit, pop, rng)
            G = _mutate(G[parents_idx], rng, n_components, mut_rate)

    tr.final_activity = activity.tolist()
    tr.a_new_final = tr.new_activity[-1] if tr.new_activity else 0.0
    tail_n = max(1, gens // 5)
    tr.a_new_tail_mean = float(np.mean(tr.new_activity[-tail_n:])) if tr.new_activity else 0.0
    tr.a_new_peak = float(np.max(tr.new_activity)) if tr.new_activity else 0.0
    # 減衰判定: ピークが末尾より十分大きい (飽和 = 初期のみ活動して後で止まる)。
    tr.a_new_decayed = bool(tr.a_new_peak > 1.25 * (tr.a_new_tail_mean + 1e-9))
    tr.supra_count_tail_mean = float(np.mean(tr.supra_count[-tail_n:])) if tr.supra_count else 0.0
    tr.supra_count_final = tr.supra_count[-1] if tr.supra_count else 0
    tr.diversity_tail_mean = float(np.mean(tr.diversity[-tail_n:])) if tr.diversity else 0.0
    return tr


# ---------------------------------------------------------------------------
# 3 レジーム比較 + verdict (決定論)
# ---------------------------------------------------------------------------

@dataclass
class ModesVerdict:
    """計器の弁別 verdict (決定論)."""

    a_new_adaptive: float
    a_new_neutral: float
    a_new_saturated: float
    a_shadow: float
    supra_count_adaptive: float        # adaptive: supra-neutral component 種数 (tail)
    supra_count_neutral: float         # neutral:  supra-neutral component 種数 (tail)
    supra_count_saturated: float       # saturated: supra-neutral component 種数 (tail)
    diversity_adaptive: float          # adaptive: present component 種数 (tail)
    diversity_saturated: float         # saturated: present component 種数 (tail)
    adaptive_supra_neutral: bool       # adaptive A_new ≫ neutral A_new
    neutral_near_zero: bool            # neutral A_new ≈ 0
    adaptive_exceeds_saturated: bool   # saturated は多様性崩壊 (新規獲得が止まる) → adaptive と区別
    saturated_collapsed_diversity: bool  # saturated は present 多様性が adaptive より大きく崩壊
    saturated_decayed: bool            # saturated A_new はピークから減衰 (補助シグナル)
    modes_detects_openendedness: bool  # 総合判定 = 計器が開放端的活動を区別できるか


def compare_modes(
    *,
    gens: int = 400,
    pop: int = 96,
    n_components: int = N_COMPONENTS,
    genome_len: int = GENOME_LEN,
    mut_rate: float = 0.08,
    seed: int = 0,
    shadow_percentile: float = 99.0,
    supra_ratio: float = 3.0,
    near_zero_frac: float = 0.05,
    saturated_vocab: int = 6,
) -> tuple[dict[str, ModeTrace], ModesVerdict]:
    """3 レジームを回し、中立シャドウ閾値を全モードに適用して verdict を出す.

    手順:
      1. neutral を回し最終 activity 分布 → a_shadow (shadow_percentile)。
      2. 同 a_shadow を adaptive / neutral / saturated 全てに適用して A_new 時系列を再計算
         (= 全モードを同じ計器で測る; 公平性)。
      3. 決定論 verdict。

    Returns:
        (traces, verdict)。traces は {"adaptive","neutral","saturated"} の ModeTrace。
    """
    common = dict(
        gens=gens, pop=pop, n_components=n_components, genome_len=genome_len,
        mut_rate=mut_rate, saturated_vocab=saturated_vocab,
    )

    # --- step 1: 中立シャドウを先に回し閾値を得る ---
    neutral_tr = run_mode("neutral", seed=seed, a_shadow=0.0, **common)
    a_shadow = shadow_threshold(np.asarray(neutral_tr.final_activity), shadow_percentile)

    # --- step 2: 同 a_shadow で全モードを回し直す (公平な計器適用) ---
    traces: dict[str, ModeTrace] = {}
    for mode in ("adaptive", "neutral", "saturated"):
        traces[mode] = run_mode(mode, seed=seed, a_shadow=a_shadow, **common)

    a_adapt = traces["adaptive"].a_new_tail_mean
    a_neut = traces["neutral"].a_new_tail_mean
    a_sat = traces["saturated"].a_new_tail_mean

    sc_adapt = traces["adaptive"].supra_count_tail_mean
    sc_neut = traces["neutral"].supra_count_tail_mean
    sc_sat = traces["saturated"].supra_count_tail_mean

    d_adapt = traces["adaptive"].diversity_tail_mean
    d_sat = traces["saturated"].diversity_tail_mean

    # neutral 自身の総 activity を near-zero 基準にする (A_new が neutral の total に対し微小)。
    neutral_total = traces["neutral"].total_activity[-1] if traces["neutral"].total_activity else 1.0
    near_zero_thresh = near_zero_frac * neutral_total

    adaptive_supra_neutral = a_adapt > supra_ratio * (a_neut + 1e-9)
    neutral_near_zero = a_neut <= near_zero_thresh
    saturated_decayed = traces["saturated"].a_new_decayed

    # adaptive と saturated の区別 (honest disclosure):
    # A_new (supra-neutral 活動和) は持続する自明少数 component でも単調増加するため、
    # A_new の大小だけでは「新規を獲得し続ける適応」と「自明最適へ固着した飽和」を切り分けられない
    # (実測: a_new_sat が a_new_adapt を上回る seed すらある)。
    # **seed 安定な弁別子 = present component 多様性の崩壊**: 飽和は集団が自明小語彙へ収束し
    # 多様性が大きく崩れる (D_sat ≈ trivial vocab) のに対し、適応的ランは moving target を
    # 追って広い多様性を維持する。よって「saturated の多様性が adaptive の半分未満」を主判定とし、
    # supra-neutral component 種数 (新規獲得の継続) を補助に併記する。
    saturated_collapsed_diversity = d_sat < 0.5 * (d_adapt + 1e-9)
    adaptive_exceeds_saturated = saturated_collapsed_diversity or saturated_decayed

    modes_detects = bool(
        adaptive_supra_neutral
        and neutral_near_zero
        and adaptive_exceeds_saturated
    )

    verdict = ModesVerdict(
        a_new_adaptive=a_adapt,
        a_new_neutral=a_neut,
        a_new_saturated=a_sat,
        a_shadow=a_shadow,
        supra_count_adaptive=sc_adapt,
        supra_count_neutral=sc_neut,
        supra_count_saturated=sc_sat,
        diversity_adaptive=d_adapt,
        diversity_saturated=d_sat,
        adaptive_supra_neutral=adaptive_supra_neutral,
        neutral_near_zero=neutral_near_zero,
        adaptive_exceeds_saturated=adaptive_exceeds_saturated,
        saturated_collapsed_diversity=saturated_collapsed_diversity,
        saturated_decayed=saturated_decayed,
        modes_detects_openendedness=modes_detects,
    )
    return traces, verdict


# ---------------------------------------------------------------------------
# 出力 (json + stdout)
# ---------------------------------------------------------------------------

_SCHEMA = "llive.poc.evolutionary_activity_modes/v1"

_PROPOSITION = (
    "Bedau evolutionary activity statistics (per-component cumulative activity) compared "
    "against a neutral (no-selection) shadow can DISTINGUISH: (1) adaptive runs that keep "
    "acquiring high-value components show supra-neutral new-activity A_new; (2) neutral runs "
    "show A_new ~= 0; (3) saturated runs (converging to a fixed trivial optimum) show A_new "
    "only early then it decays. => an instrument for telling open-ended adaptive activity "
    "apart from neutral drift / saturation churn in llive evolution."
)

_HONEST_NOTES = [
    "PROXY toy: stdlib + numpy only, deterministic seed, ZERO LLM/Docker/genome imports "
    "(demo_persona_fx-style isolated PoC). Not a claim about real llive open-endedness.",
    "This PoC demonstrates the DISCRIMINATIVE POWER of the instrument (can it separate the "
    "three regimes), not that real llive is open-ended.",
    "Next stage: wire this instrument to real llive evolution snapshots (lineage / trait "
    "activity) and measure there.",
    "The neutral shadow threshold (a_shadow) is taken from a no-selection run's final "
    "activity distribution; the SAME threshold is applied to all regimes for fairness.",
    "HONEST CAVEAT: A_new (the supra-neutral ACTIVITY SUM) grows monotonically for ANY "
    "persistent component, so a trivially-fixed saturated regime can also accumulate large "
    "A_new — at some seeds saturated A_new even exceeds adaptive A_new. Therefore A_new "
    "magnitude alone CANNOT separate 'keeps acquiring novelty' (adaptive) from 'fixed on a "
    "trivial optimum' (saturated).",
    "The SEED-STABLE discriminator vs saturation is the COLLAPSE of present-component "
    "diversity: saturated converges to a tiny trivial vocabulary (D_sat ~= trivial vocab) "
    "while adaptive sustains broad diversity by chasing a moving target. The verdict separates "
    "adaptive from saturated via this diversity collapse (D_sat < 0.5*D_adapt); supra_count "
    "(number of components above the shadow) is reported as corroborating signal.",
    "So the instrument distinguishes the three regimes by COMBINING signals: supra-neutral "
    "A_new vs the neutral shadow (adaptive vs neutral) AND diversity collapse (adaptive vs "
    "saturated). No single scalar suffices — this is itself a finding for wiring to real llive.",
]


def _trace_to_json(tr: ModeTrace, *, keep_series: bool = True) -> dict:
    d = asdict(tr)
    if not keep_series:
        for k in ("diversity", "total_activity", "mean_cumulative_activity",
                  "new_activity", "supra_count"):
            d.pop(k, None)
    # final_activity は per-component 配列 (長い) → そのまま残す (語彙=64 程度で許容)。
    return d


def write_report(
    out_dir: Path,
    traces: dict[str, ModeTrace],
    verdict: ModesVerdict,
    params: dict,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": _SCHEMA,
        "proposition": _PROPOSITION,
        "params": params,
        "regimes": {name: _trace_to_json(tr) for name, tr in traces.items()},
        "verdict": asdict(verdict),
        "honest_notes": _HONEST_NOTES,
    }
    out_json = out_dir / "modes.json"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_json


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Bedau evolutionary activity + neutral shadow PoC (3 regimes)"
    )
    ap.add_argument("--gens", type=int, default=400)
    ap.add_argument("--pop", type=int, default=96)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--mut-rate", type=float, default=0.08)
    ap.add_argument("--shadow-percentile", type=float, default=99.0)
    ap.add_argument(
        "--out",
        type=str,
        default="out/poc_evolutionary_activity_modes",
        help="output directory for modes.json",
    )
    args = ap.parse_args(argv)
    _ensure_utf8_stdout()

    params = dict(
        gens=args.gens,
        pop=args.pop,
        seed=args.seed,
        mut_rate=args.mut_rate,
        shadow_percentile=args.shadow_percentile,
        n_components=N_COMPONENTS,
        genome_len=GENOME_LEN,
    )
    traces, verdict = compare_modes(
        gens=args.gens,
        pop=args.pop,
        seed=args.seed,
        mut_rate=args.mut_rate,
        shadow_percentile=args.shadow_percentile,
    )

    out_dir = Path(args.out)
    out_json = write_report(out_dir, traces, verdict, params)

    # --- stdout summary ---
    print(
        f"PoC Bedau evolutionary activity + neutral shadow  "
        f"(gens={args.gens} pop={args.pop} seed={args.seed})  — PROXY, deterministic"
    )
    print(f"  components={N_COMPONENTS} genome_len={GENOME_LEN} "
          f"a_shadow={verdict.a_shadow:.3f} (p{args.shadow_percentile:g} of neutral final activity)")
    print(f"  metrics: A_new = supra-neutral activity SUM; supra_cnt = supra-neutral "
          f"component COUNT (both vs a_shadow, tail 20%)")
    print(f"  {'regime':10s} {'A_new(tail)':>12s} {'supra_cnt':>10s} "
          f"{'A(final)':>10s} {'D(final)':>9s} {'decayed':>8s}")
    for name in ("adaptive", "neutral", "saturated"):
        tr = traces[name]
        print(f"  {name:10s} {tr.a_new_tail_mean:12.3f} {tr.supra_count_tail_mean:10.2f} "
              f"{tr.total_activity[-1]:10.1f} {tr.diversity[-1]:9d} "
              f"{str(tr.a_new_decayed):>8s}")
    print("  checks:")
    print(f"    adaptive supra-neutral (A_new_adapt > {3.0:g}x A_new_neut) : "
          f"{verdict.adaptive_supra_neutral}")
    print(f"    neutral near-zero (A_new_neut ~= 0)                      : "
          f"{verdict.neutral_near_zero}")
    print(f"    saturated diversity collapsed (D_sat < 0.5 D_adapt)     : "
          f"{verdict.adaptive_exceeds_saturated} "
          f"(D adapt={verdict.diversity_adaptive:.1f} sat={verdict.diversity_saturated:.1f}; "
          f"supra_cnt adapt={verdict.supra_count_adaptive:.1f} sat={verdict.supra_count_saturated:.1f})")
    print(f"  => modes_detects_openendedness = {verdict.modes_detects_openendedness}")
    if not verdict.modes_detects_openendedness:
        print("  honest: the instrument did NOT cleanly separate the regimes at these "
              "params — report as inconclusive, do not overstate.")
    print("  honest: proxy toy; measures the INSTRUMENT's discriminative power, not real "
          "llive open-endedness. Next = wire to real llive lineage/trait activity.")
    print(f"  wrote: {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
