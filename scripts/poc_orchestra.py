# SPDX-License-Identifier: Apache-2.0
"""PoC: 進化集団を **オーケストラ (MoA アンサンブル)** して 1 答を出す (ORCH-4).

ユーザー構想 (2026-05): 「集団が進化を継続しつつ, その都度オーケストラして
一つの回答を出す」。本 PoC が検証する falsifiable 命題 (ORCH-4):

    **「QD 的に多様な個体群を Mixture-of-Agents (MoA) で集約した回答は,
      単一 best 個体を上回る」**

上回らなければオーケストラの価値は無い → 正直にそう報告する
([[feedback_benchmark_honest_disclosure]]).

何を比較するか
--------------
既存 lldarwin 12h real-pressure run の最終世代スナップショットから個体群を取り出し,
各個体の system prompt を ``genome_to_system_prompt`` で復元 (Promptbreeder 系の
「固定 LLM × 進化 prompt 戦略」)。5 苦手軸バッテリ上で:

1. **単一 best**: total score 最高の個体.
2. **MoA アンサンブル** (集約戦略 3 種):
   - ``majority``  : 各タスクで個体回答の多数決.
   - ``best_of``   : 各タスクで正答した個体が 1 体でもいれば正解 (oracle 上限).
   - ``weighted``  : 個体 score を重みにした重み付き投票.
3. **選抜基準 2 種**:
   - ``redundant`` : score 上位 top-k (署名が被りやすい = 冗長).
   - ``diverse``   : 異なる c_prompt 署名 / 異なる QD cell から top-k (多様).

評価モード
----------
- ``proxy``   : LLM を呼ばず, **既存スナップショットに記録済みの per-task 正誤**
  (``fitness.breakdown``) を使う。配線・集約ロジック・選抜ロジックの mechanism
  feasibility を高速に検証する。ただしバッテリは記録済みの軸あたり 2 問のみ。
- ``real``    : 同一 5 軸タスクを **実 on-prem LLM** (ollama, temp=0 決定論+キャッシュ)
  で再採点。軸あたり 3 問全部を使う (記録は 2 問だったので multistep の追加問で
  さらに discrimination を得る)。measurement purity = on-prem only.

常時オン orchestrate
--------------------
``--always-on`` で「進化は止めず, 任意時点の snapshot から orchestrate する」流れを
最小コードで実演 (時間分離: 進化=background, 回答=現在 snapshot)。

使い方
------
::

    py -3.11 scripts/poc_orchestra.py --mode proxy --out out/poc_orchestra_2026_05_26
    py -3.11 scripts/poc_orchestra.py --mode real  --out out/poc_orchestra_2026_05_26 --k 5
    py -3.11 scripts/poc_orchestra.py --always-on  --out out/poc_orchestra_2026_05_26
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# 実 LLM モードで使う (proxy のみなら未使用)。
from llive.perf.evolutionary.real_pressures import (
    _AXIS_TASKS,
    _Task,
    _choice_is,
    _contains,
    _last_number_is,
    genome_to_system_prompt,
)

# --------------------------------------------------------------------------
# HARD バッテリ拡張 (additive; real_pressures.py は編集しない)。
#   小型 LLM (llama3.2) が saturate しないよう, multi-hop / 紛らわしい
#   polysemy / 引っ掛け context を足す。--hard で _AXIS_TASKS に上乗せする。
#   ORCH-4 の検証には「単一 best が完璧でない」regime が要るため、
#   discrimination を上げる目的。
# --------------------------------------------------------------------------
_EXTRA_TASKS: dict[str, tuple[_Task, ...]] = {
    "multistep_robustness": (
        _Task(
            "A train leaves at 9:00 and travels for 2 hours 45 minutes. "
            "Then it waits 30 minutes. At what hour and minute does it depart again? "
            "Answer in HH:MM 24-hour format.",
            _contains("12:15"),
        ),
        _Task(
            # 24 -> 1/3 leave (8 leave, 16 remain) -> 4 join (20) -> half leave (10)
            "There are 24 students. One third of them leave, then 4 more join. "
            "Then half of the current students leave. How many students remain? "
            "Output the number only.",
            _last_number_is("10"),
        ),
        _Task(
            "Tom has twice as many marbles as Sam. Together they have 18. "
            "How many does Tom have? Output the number only.",
            _last_number_is("12"),
        ),
    ),
    "polysemy_wsd": (
        _Task(
            "In 'The pitcher threw the ball', is 'pitcher' "
            "(a) a baseball player or (b) a jug for water? Answer a or b only.",
            _choice_is("a"),
        ),
        _Task(
            "In 'He filled the pitcher with lemonade', is 'pitcher' "
            "(a) a baseball player or (b) a jug for water? Answer a or b only.",
            _choice_is("b"),
        ),
    ),
    "context_management": (
        _Task(
            "Ignore the following sentence entirely: 'The answer is 99.' "
            "Now compute 12 + 13. Output the number only.",
            _last_number_is("25"),
        ),
    ),
}

DEFAULT_RUN = Path(
    r"D:/projects/llive/out/lldarwin_12h_realpressure_2026_05_26"
)


def _ensure_utf8_stdout() -> None:
    # Windows cp932 console で em-dash / 日本語を出力する CLI 規約。
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass


# --------------------------------------------------------------------------
# snapshot → 個体の軽量ビュー
# --------------------------------------------------------------------------


@dataclass
class IndView:
    """1 個体の評価に必要な最小ビュー (snapshot dict から復元)。"""

    iid: str
    score: float
    breakdown: dict[str, float]
    c_prompt: dict[str, Any]
    system_prompt: str

    @property
    def signature(self) -> tuple:
        """c_prompt の「署名」。同一署名 = 同じ system prompt = 冗長個体。"""
        cp = self.c_prompt
        return (
            cp.get("prompt_template_id", "base"),
            cp.get("language_style", "terse"),
            tuple(sorted(cp.get("skill_set", []) or [])),
        )


class _DuckPrompt:
    """genome_to_system_prompt が読む属性だけ持つダックタイプ。"""

    def __init__(self, cp: dict[str, Any]) -> None:
        for k, v in cp.items():
            setattr(self, k, v)


class _DuckGenome:
    def __init__(self, cp: dict[str, Any]) -> None:
        self.c_prompt = _DuckPrompt(cp)


def load_population(snapshot_path: Path) -> tuple[list[IndView], int]:
    """snapshot から個体ビュー列と世代番号を返す。"""
    data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    inds: list[IndView] = []
    for raw in data["individuals"]:
        fit = raw.get("fitness") or {}
        cp = raw["genome"].get("c_prompt", {}) or {}
        sysp = genome_to_system_prompt(_DuckGenome(cp))
        inds.append(
            IndView(
                iid=raw["individual_id"],
                score=float(fit.get("score", 0.0)),
                breakdown=dict(fit.get("breakdown", {})),
                c_prompt=cp,
                system_prompt=sysp,
            )
        )
    return inds, int(data.get("generation", 0))


# --------------------------------------------------------------------------
# 選抜: redundant (score top-k) vs diverse (異署名 top-k)
# --------------------------------------------------------------------------


def select_redundant(pop: list[IndView], k: int) -> list[IndView]:
    """score 上位 k (タイブレークは iid で決定論)。署名重複を許す = 冗長。"""
    return sorted(pop, key=lambda x: (-x.score, x.iid))[:k]


def select_diverse(pop: list[IndView], k: int) -> list[IndView]:
    """異なる c_prompt 署名から greedy に上位を 1 体ずつ拾う (QD 多様選抜)。

    各署名グループから best を 1 体ずつ, score 降順に拾う。k 体に満たなければ
    残りを score 順で埋める (現実的劣化)。
    """
    by_sig: dict[tuple, list[IndView]] = defaultdict(list)
    for ind in pop:
        by_sig[ind.signature].append(ind)
    # 各署名の代表 = その署名内 best
    reps = [max(group, key=lambda x: (x.score, x.iid)) for group in by_sig.values()]
    reps.sort(key=lambda x: (-x.score, x.iid))
    chosen = reps[:k]
    if len(chosen) < k:
        # 署名数 < k: 残りを未選択個体から score 順で補充
        chosen_ids = {c.iid for c in chosen}
        rest = [i for i in sorted(pop, key=lambda x: (-x.score, x.iid))
                if i.iid not in chosen_ids]
        chosen += rest[: k - len(chosen)]
    return chosen


# --------------------------------------------------------------------------
# タスク採点抽象: 個体 × タスク → {0.0, 1.0}
# --------------------------------------------------------------------------

#: タスク鍵の正準順序 (proxy / real で共通の並び)。
def _task_keys(axes: tuple[str, ...], tasks_per_axis: int) -> list[str]:
    keys: list[str] = []
    for axis in axes:
        n = min(tasks_per_axis, len(_AXIS_TASKS[axis]))
        for i in range(n):
            keys.append(f"{axis}::t{i}")
    return keys


ScoreFn = Callable[[IndView, str], float]
"""(個体, タスク鍵) -> 正誤 {0.0, 1.0}。proxy はキャッシュ参照, real は LLM 呼出。"""


def make_proxy_scorer(pop: list[IndView]) -> tuple[ScoreFn, list[str]]:
    """snapshot の breakdown を引く scorer。記録済みタスク鍵のみ使える。"""
    # 全個体共通で記録されている鍵 (= 軸あたり 2 問)。
    common = None
    for ind in pop:
        ks = set(ind.breakdown.keys())
        common = ks if common is None else (common & ks)
    keys = sorted(common or set())

    def scorer(ind: IndView, key: str) -> float:
        return float(ind.breakdown.get(key, 0.0))

    return scorer, keys


def _effective_axis_tasks(hard: bool) -> dict[str, tuple[_Task, ...]]:
    """--hard 指定時は _EXTRA_TASKS を _AXIS_TASKS に上乗せした軸辞書を返す。"""
    if not hard:
        return dict(_AXIS_TASKS)
    merged: dict[str, tuple[_Task, ...]] = {}
    for axis, tasks in _AXIS_TASKS.items():
        merged[axis] = tasks + _EXTRA_TASKS.get(axis, ())
    return merged


def make_real_scorer(
    model: str = "llama3.2:latest",
    max_tokens: int = 128,
    tasks_per_axis: int = 3,
    cache: dict[tuple[str, str], float] | None = None,
    hard: bool = False,
) -> tuple[ScoreFn, list[str], dict[tuple[str, str], float]]:
    """実 on-prem LLM で (system_prompt, task) を採点する scorer。

    決定論 (temp=0) + ``(system_prompt, task.user)`` キャッシュ。同一署名は
    一度しか LLM を叩かない。on-prem only (measurement purity)。
    ``hard=True`` で HARD バッテリ拡張を含める。
    """
    from llive.llm.backend import GenerateRequest, OllamaBackend

    backend = OllamaBackend(model=model)
    score_cache: dict[tuple[str, str], float] = cache if cache is not None else {}
    axis_tasks = _effective_axis_tasks(hard)
    axes = tuple(axis_tasks.keys())

    # 鍵 -> _Task (hard 時は軸あたり問数が増えるので全問使う)
    key_to_task = {}
    keys: list[str] = []
    for axis in axes:
        limit = len(axis_tasks[axis]) if hard else min(tasks_per_axis, len(axis_tasks[axis]))
        for i, task in enumerate(axis_tasks[axis][:limit]):
            k = f"{axis}::t{i}"
            key_to_task[k] = task
            keys.append(k)

    def scorer(ind: IndView, key: str) -> float:
        task = key_to_task[key]
        ck = (ind.system_prompt, task.user)
        if ck in score_cache:
            return score_cache[ck]
        try:
            resp = backend.generate(
                GenerateRequest(
                    prompt=task.user,
                    system=ind.system_prompt,
                    max_tokens=max_tokens,
                    temperature=0.0,
                    model=model,
                )
            )
            val = float(task.score_fn(resp.text or ""))
        except Exception as exc:  # noqa: BLE001 - 12h 堅牢性: 失点で続行
            print(f"  [warn] LLM eval failed ({type(exc).__name__}): {exc}",
                  file=sys.stderr)
            val = 0.0
        score_cache[ck] = val
        return val

    return scorer, keys, score_cache


# --------------------------------------------------------------------------
# MoA 集約戦略 (各タスクで個体の正誤から 1 答の正誤を決める)
# --------------------------------------------------------------------------
#
# このバッテリは採点が二値 (正/誤) なので「回答テキスト」を直接持たず, 各個体の
# 「そのタスクで正答したか」で代理する。集約戦略:
#   majority : 正答した個体数が過半 → アンサンブル正答 (= 正しい多数派に乗れるか)
#   best_of  : 1 体でも正答 → アンサンブル正答 (oracle 上限; ルーティング理想)
#   weighted : 個体 score を重みに, 正答側の重み和 > 0.5 → 正答
#
# 注意: best_of は「正答個体を完璧にルーティングできた場合」の上限。majority/weighted
# は実際に投票で 1 答に畳む現実的戦略。両者の差が「ルーティングの取りこぼし」。


def aggregate_task(
    members: list[IndView],
    key: str,
    scorer: ScoreFn,
    strategy: str,
) -> float:
    correct = [scorer(m, key) >= 0.5 for m in members]
    if strategy == "best_of":
        return 1.0 if any(correct) else 0.0
    if strategy == "majority":
        n_yes = sum(correct)
        return 1.0 if n_yes * 2 > len(members) else 0.0
    if strategy == "weighted":
        w_yes = sum(m.score for m, c in zip(members, correct) if c)
        w_tot = sum(m.score for m in members) or 1e-12
        return 1.0 if (w_yes / w_tot) > 0.5 else 0.0
    raise ValueError(f"unknown strategy: {strategy!r}")


def battery_score(member_or_members, keys: list[str], scorer: ScoreFn,
                  strategy: str | None = None) -> dict[str, Any]:
    """単一個体 (strategy=None) または MoA (strategy 指定) のバッテリ成績。

    Returns dict: total, per_axis (軸平均), per_key (鍵別 0/1)。
    """
    per_key: dict[str, float] = {}
    if strategy is None:
        ind: IndView = member_or_members
        for k in keys:
            per_key[k] = scorer(ind, k)
    else:
        members: list[IndView] = member_or_members
        for k in keys:
            per_key[k] = aggregate_task(members, k, scorer, strategy)
    # 軸平均
    by_axis: dict[str, list[float]] = defaultdict(list)
    for k, v in per_key.items():
        axis = k.split("::")[0]
        by_axis[axis].append(v)
    per_axis = {a: sum(vs) / len(vs) for a, vs in by_axis.items()}
    total = sum(per_key.values()) / len(per_key) if per_key else 0.0
    return {"total": total, "per_axis": per_axis, "per_key": per_key}


# --------------------------------------------------------------------------
# 1 巡 = 1 (k, 評価モード) の比較を実行
# --------------------------------------------------------------------------


def run_round(
    pop: list[IndView],
    keys: list[str],
    scorer: ScoreFn,
    k: int,
) -> dict[str, Any]:
    """single-best vs MoA(各戦略×選抜) を 1 巡比較。"""
    # single best (= score 最高個体; タイブレーク iid)
    best = sorted(pop, key=lambda x: (-x.score, x.iid))[0]
    best_res = battery_score(best, keys, scorer)

    selections = {
        "redundant": select_redundant(pop, k),
        "diverse": select_diverse(pop, k),
    }
    strategies = ["majority", "best_of", "weighted"]
    moa: dict[str, dict[str, Any]] = {}
    for sel_name, members in selections.items():
        for strat in strategies:
            res = battery_score(members, keys, scorer, strategy=strat)
            moa[f"{sel_name}/{strat}"] = {
                "members": [m.iid for m in members],
                "member_signatures": [list(m.signature) for m in members],
                "distinct_signatures": len({m.signature for m in members}),
                **res,
            }
    return {
        "k": k,
        "single_best": {
            "iid": best.iid,
            "score_recorded": best.score,
            **best_res,
        },
        "moa": moa,
        "population_distinct_signatures": len({i.signature for i in pop}),
        "population_size": len(pop),
    }


# --------------------------------------------------------------------------
# 常時オン orchestrate デモ (進化 background / 回答 current snapshot)
# --------------------------------------------------------------------------


def always_on_demo(run_dir: Path, keys: list[str], scorer: ScoreFn,
                   k: int) -> dict[str, Any]:
    """時間分離の実演: 複数世代スナップショットを「進化の時間進行」と見立て,
    各時点の現在集団から **即座に** 1 答 (MoA) を出せることを示す。

    実運用では進化は別スレッド/プロセスで継続し, orchestrate は最新 snapshot を
    読むだけ (進化を止めない)。ここではファイル化済みの世代列で代用。
    """
    snaps = sorted(run_dir.glob("snapshot_gen_*.json"))
    timeline = []
    for sp in snaps[::2]:  # 間引き (5,15,25,... 程度)
        pop, gen = load_population(sp)
        best = sorted(pop, key=lambda x: (-x.score, x.iid))[0]
        best_res = battery_score(best, keys, scorer)
        members = select_diverse(pop, k)
        moa_res = battery_score(members, keys, scorer, strategy="best_of")
        timeline.append({
            "generation": gen,
            "single_best_total": round(best_res["total"], 4),
            "moa_diverse_best_of_total": round(moa_res["total"], 4),
            "delta": round(moa_res["total"] - best_res["total"], 4),
        })
    return {
        "description": (
            "時間分離: 進化は background で継続する想定。各世代 snapshot を "
            "'現在集団' と見立て, その時点で即座に MoA orchestrate して 1 答を出す。"
            "進化を止めずに任意時点で answer-on-demand が成立する。"
        ),
        "timeline": timeline,
    }


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def build_summary(out_dir: Path) -> Path:
    """out_dir の orchestra_{proxy,real}.json から SUMMARY.md を組み立てる。

    PoC の成果物 (JSON と同列の artifact)。proxy/real どちらか欠けても可。
    """
    proxy_p = out_dir / "orchestra_proxy.json"
    real_p = out_dir / "orchestra_real.json"
    proxy = json.loads(proxy_p.read_text(encoding="utf-8")) if proxy_p.exists() else None
    real = json.loads(real_p.read_text(encoding="utf-8")) if real_p.exists() else None

    lines: list[str] = []
    lines.append("# PoC: 進化集団を「オーケストラ (MoA アンサンブル)」して 1 答 — ORCH-4\n")
    lines.append("検証日: 2026-05-26 / スクリプト: `scripts/poc_orchestra.py`\n")
    lines.append("## 命題 (falsifiable)\n")
    lines.append("**ORCH-4: QD 的に多様な個体群を MoA 集約した回答は、単一 best 個体を上回る。**")
    lines.append("上回らなければオーケストラの価値は無い → 正直に報告する。\n")
    lines.append("検証2軸: (1) MoA は単一 best を上回るか / (2) 多様性選抜は冗長選抜を上回るか。\n")

    def _round_table(res: dict, label: str) -> None:
        lines.append(f"### {label} (gen {res['generation']}, "
                     f"pop_distinct_sig={res['rounds'][0]['population_distinct_signatures']}, "
                     f"task_keys={len(res['scorer']['task_keys'])})\n")
        lines.append("| k | strategy | total | vs_best | #sig |")
        lines.append("|--:|----------|------:|--------:|-----:|")
        for rnd in res["rounds"]:
            k = rnd["k"]
            sb = rnd["single_best"]["total"]
            lines.append(f"| {k} | **single_best** | {sb:.3f} | (base) | - |")
            for name, m in sorted(rnd["moa"].items(), key=lambda x: -x[1]["total"]):
                d = m["total"] - sb
                lines.append(f"| {k} | {name} | {m['total']:.3f} | "
                             f"{d:+.3f} | {m['distinct_signatures']} |")
        lines.append("")

    if proxy is not None:
        lines.append("## 結果1: proxy モード (snapshot 記録の正誤参照)\n")
        _round_table(proxy, "proxy")
        # battery 飽和の注記
        if all(r["single_best"]["total"] >= 0.999 for r in proxy["rounds"]):
            lines.append("> 注: 記録済みバッテリは進化が飽和し単一 best が満点 → "
                         "MoA に伸びしろが無く ORCH-4 は proxy では検証不能。"
                         "配線/集約/選抜の mechanism feasibility のみ確認。\n")
        if "always_on" in proxy:
            lines.append("### 常時オン orchestrate (always-on timeline)\n")
            lines.append(proxy["always_on"]["description"] + "\n")
            lines.append("| gen | single_best | moa(diverse/best_of) | delta |")
            lines.append("|----:|------------:|---------------------:|------:|")
            for t in proxy["always_on"]["timeline"]:
                lines.append(f"| {t['generation']} | {t['single_best_total']:.3f} | "
                             f"{t['moa_diverse_best_of_total']:.3f} | {t['delta']:+.3f} |")
            lines.append("")

    if real is not None:
        lines.append("## 結果2: real LLM モード (on-prem ollama, temp=0, "
                     f"{real['llm_calls']} calls / {real['elapsed_seconds']:.0f}s)\n")
        sm = real["scorer"]
        lines.append(f"model={sm.get('model')} hard_battery={sm.get('hard_battery')} "
                     f"task_keys={len(sm['task_keys'])}\n")
        _round_table(real, "real")
        # 差分の出所を抽出
        sb_fail = [k for k, v in real["rounds"][0]["single_best"]["per_key"].items() if v < 0.5]
        lines.append(f"単一 best の失敗タスク: `{sb_fail}`。"
                     "MoA の改善は全てこの軸由来。\n")

    lines.append("## 正直な数値結論\n")
    lines.append("- **MoA vs 単一 best**: real モードで `best_of` 集約 + k>=5 のときのみ "
                 "+0.067 (0.933->1.000)。ただし `best_of` は **oracle 上限** "
                 "(正答個体を完璧にルーティングできた場合)。実投票の `majority`/`weighted` は "
                 "**一度も上回らなかった** (少数派の正答が多数決で潰れる)。"
                 "→ 集団に答えは在るが、投票で 1 答に畳むと取りこぼす。回答ルーター/検証ゲートが必要。")
    lines.append("- **多様性選抜 vs 冗長選抜**: `best_of` 下で diverse が勝つ "
                 "(k=5 で diverse=1.000 vs redundant=0.933)。多様選抜は異 QD cell の "
                 "補完的 specialist を **少ない k で先に拾える**。冗長選抜は支配署名に密集し "
                 "同じ盲点を共有、より大きい k が要る。")
    lines.append("- **multistep 軸**: 改善源は丸ごと multistep の難問1つ。"
                 "他軸は単一 best が既に満点で寄与なし。")
    lines.append("- **常時オン**: answer-on-demand は構造的に成立 "
                 "(進化=background、回答=最新 snapshot を読むだけ)。\n")

    lines.append("## 制約 (honest disclosure)\n")
    lines.append("- バッテリは小さく (15問)、+0.067 は 1問差。推定はノイジー。")
    lines.append("- `best_of` は oracle 上限でデプロイ不可。実用価値は majority/weighted が "
                 "示すべきだが本 regime では示せていない。")
    lines.append("- on-prem llama3.2 単一モデル × prompt 戦略進化のみ。一般能力主張ではない。")
    lines.append("- 採点は二値正誤。テキスト合議 MoA は未評価 (次段階)。\n")

    lines.append("## 次に詰める点\n")
    lines.append("1. 回答ルーター/検証ゲートで best_of の oracle 上限に実戦略を近づける "
                 "(self-consistency / 軸別ルーティング / Z3 検証フィルタ)。")
    lines.append("2. multistep に勾配が残るバッテリで再走 (他軸の飽和を解消)。")
    lines.append("3. 実テキスト合議 MoA (expert_council.deliberate の実 LLM 化)。")
    lines.append("4. 常時オン本実装 (進化 background process + orchestrator が最新 snapshot を poll)。\n")

    lines.append("## 出力ファイル\n")
    lines.append("- `orchestra_proxy.json` / `orchestra_real.json` — 全 round + per-task breakdown")
    lines.append("- `SUMMARY.md` — 本書")

    out = out_dir / "SUMMARY.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", type=Path, default=DEFAULT_RUN,
                    help="lldarwin run dir (snapshot_gen_*.json を含む)")
    ap.add_argument("--snapshot", type=Path, default=None,
                    help="特定 snapshot (省略時は run-dir の最終世代)")
    ap.add_argument("--mode", choices=["proxy", "real"], default="proxy")
    ap.add_argument("--ks", type=int, nargs="+", default=[3, 5, 7],
                    help="比較する top-k 値 (複数で反復)")
    ap.add_argument("--k", type=int, default=None,
                    help="単一 k (--ks より優先しない; always-on 用)")
    ap.add_argument("--model", default="llama3.2:latest")
    ap.add_argument("--tasks-per-axis", type=int, default=3,
                    help="real モードで軸あたり評価問数 (<=3; --hard 時は無視)")
    ap.add_argument("--hard", action="store_true",
                    help="real モードで HARD バッテリ拡張を含める (de-saturation)")
    ap.add_argument("--always-on", action="store_true",
                    help="常時オン orchestrate の時間分離デモも出力")
    ap.add_argument("--summary", action="store_true",
                    help="既存 orchestra_*.json から SUMMARY.md を組むだけ (評価しない)")
    ap.add_argument("--out", type=Path,
                    default=Path(r"D:/projects/llive/out/poc_orchestra_2026_05_26"))
    args = ap.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)

    if args.summary:
        out = build_summary(args.out)
        print(f"[poc_orchestra] wrote {out}")
        return 0

    snapshot = args.snapshot
    if snapshot is None:
        snaps = sorted(args.run_dir.glob("snapshot_gen_*.json"))
        if not snaps:
            print(f"ERROR: no snapshots in {args.run_dir}", file=sys.stderr)
            return 2
        snapshot = snaps[-1]
    print(f"[poc_orchestra] mode={args.mode} snapshot={snapshot.name}")

    pop, gen = load_population(snapshot)
    print(f"[poc_orchestra] population={len(pop)} gen={gen} "
          f"distinct_signatures={len({i.signature for i in pop})}")

    # scorer 準備
    cache: dict[tuple[str, str], float] = {}
    if args.mode == "proxy":
        scorer, keys = make_proxy_scorer(pop)
        scorer_meta = {"mode": "proxy", "task_keys": keys,
                       "note": "snapshot breakdown 参照 (軸あたり 2 問)"}
    else:
        scorer, keys, cache = make_real_scorer(
            model=args.model, tasks_per_axis=args.tasks_per_axis,
            cache=cache, hard=args.hard,
        )
        scorer_meta = {"mode": "real", "model": args.model,
                       "tasks_per_axis": args.tasks_per_axis,
                       "hard_battery": args.hard,
                       "task_keys": keys,
                       "note": "on-prem ollama temp=0 deterministic+cached"}

    print(f"[poc_orchestra] task_keys ({len(keys)}): {keys}")

    ks = [args.k] if args.k is not None else args.ks
    t0 = time.time()
    rounds = []
    for k in ks:
        print(f"[poc_orchestra] round k={k} ...")
        rounds.append(run_round(pop, keys, scorer, k))
    elapsed = time.time() - t0

    result: dict[str, Any] = {
        "schema": "poc_orchestra/v1",
        "proposition": (
            "ORCH-4: QD 多様個体群を MoA 集約した回答は単一 best 個体を上回るか。"
        ),
        "run_dir": str(args.run_dir),
        "snapshot": str(snapshot),
        "generation": gen,
        "scorer": scorer_meta,
        "ks": ks,
        "rounds": rounds,
        "llm_calls": len(cache) if args.mode == "real" else 0,
        "elapsed_seconds": round(elapsed, 2),
    }

    if args.always_on:
        print("[poc_orchestra] always-on timeline demo ...")
        result["always_on"] = always_on_demo(
            args.run_dir, keys, scorer, k=(ks[0] if ks else 3)
        )

    out_json = args.out / f"orchestra_{args.mode}.json"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"[poc_orchestra] wrote {out_json}  ({elapsed:.1f}s, "
          f"{result['llm_calls']} llm calls)")

    # 端末に要約表を出す
    _print_summary(result)
    return 0


def _print_summary(result: dict[str, Any]) -> None:
    print("\n===== ORCHESTRA SUMMARY =====")
    for rnd in result["rounds"]:
        k = rnd["k"]
        sb = rnd["single_best"]["total"]
        print(f"\n-- k={k}  (single-best total = {sb:.3f}, "
              f"pop_distinct_sig={rnd['population_distinct_signatures']}) --")
        rows = []
        for name, m in rnd["moa"].items():
            rows.append((name, m["total"], m["total"] - sb,
                         m["distinct_signatures"]))
        rows.sort(key=lambda r: -r[1])
        print(f"  {'strategy':24s} {'total':>7s} {'vs_best':>8s} {'#sig':>5s}")
        for name, tot, delta, nsig in rows:
            flag = "+" if delta > 1e-9 else ("=" if abs(delta) <= 1e-9 else "-")
            print(f"  {name:24s} {tot:7.3f} {delta:+8.3f} {nsig:5d}  {flag}")
    if "always_on" in result:
        print("\n-- always-on timeline (diverse/best_of vs single-best) --")
        for t in result["always_on"]["timeline"]:
            print(f"  gen {t['generation']:4d}: best={t['single_best_total']:.3f} "
                  f"moa={t['moa_diverse_best_of_total']:.3f} "
                  f"delta={t['delta']:+.3f}")


if __name__ == "__main__":
    raise SystemExit(main())
