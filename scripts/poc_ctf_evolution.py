#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""PoC-CTF-1: ε-lexicase 進化集団の coverage は単一最強 / 均等多様を上回るか.

親ゴール: 進化型オーケストラ + RAPTOR 決定論オラクル + 無制限 test-time compute で
Claude Mythos をセキュリティ領域で超える
([[goal_surpass_mythos_evolutionary]] /
fullsense docs/research/mythos_surpass_design_2026_05_27.md §9)。

falsifiable 命題 (PoC-CTF-1)
----------------------------
    **ε-lexicase 進化で得た個体群 (= evolved diverse ensemble) の「集団 coverage =
      best-of-population」は、(a) 単一最強個体、(b) 非進化の均等多様ミックス を上回る。**

上回らなければ「進化」の付加価値は無い → honest にそう報告する
([[feedback_benchmark_honest_disclosure]])。

鍵となる対応関係 (設計 §9 の核)
-------------------------------
* **進化集団そのものが奏者アンサンブル**。各個体 = persona/c_prompt で決まる解法戦略。
  temp=0 で決定論化し ``(system_prompt, task)`` をキャッシュ (compute 節約)。
* **ε-lexicase が「異なるタスクを解く specialist」を集団に共存させる** (各タスク=1 case)
  → 集団が自動でタスク空間を被覆 (PoC-0 の「均等多様化は単一強モデルに負けうる」教訓への
  進化的解 = 盲点ターゲット配分を進化が達成)。
* 答え時: 決定論オラクル (flag 一致) が集団メンバーの解を verify → **集団 coverage =
  best-of-population がそのままデプロイ可能**。

再利用資産 (additive のみ; 既存ファイルは編集しない)
---------------------------------------------------
* ``scripts/poc_ctf_coverage.py``: ``BATTERY`` / ``flag_oracle`` / ``PERSONAS`` /
  ``Sampler`` / ``MockResponder`` / ``RealResponder``。
* ``llive.perf.evolutionary.real_pressures.genome_to_system_prompt``:
  個体 ``c_prompt`` (PromptChromosome) → system prompt (Promptbreeder 系)。
* ``llive.perf.evolutionary.lldarwin_v2.build_lldarwin_v2_selector`` /
  ``LLDarwinV2Config``: ε-lexicase + novelty + 適応難易度 の確定 S1 選択核。
  ``MultiPressureSelector`` は個体 ``fitness.breakdown`` から数値 case を自動抽出する
  ため、本 fitness はタスクごと 0/1 を breakdown に入れるだけで ε-lexicase が
  specialist を保つ。
* ``llive.perf.evolutionary.persona_evolution.run_persona_evolution``:
  founder からの進化 turnkey ドライバ (Genome3D + diverse founder prompts +
  selection 注入 + 世代 snapshot)。

評価モード
----------
* ``--mock`` (既定相当, **必ず実装**): LLM を呼ばない合成 responder。system prompt の
  特徴 (skill/template/style) × タスク種別で決定論的に 0/1 を返し、**異なる c_prompt が
  異なるタスクを解く specialist** になる構造を埋め込む (ε-lexicase が保つべき多様性が
  存在する regime をロジック検証する; 実機結果の予言ではない — honest)。
* ``--real``: on-prem ollama (temp=0, measurement purity = on-prem only
  [[feedback_llive_measurement_purity]])。極小設定のみ想定 (小集団・少世代・小バッテリ)。

使い方
------
::

    # ロジック検証 (inference ゼロ)
    py -3.11 scripts/poc_ctf_evolution.py --mock --pop 16 --gens 8 \
        --out out/poc_ctf_evolution

    # 極小実機 smoke (frugal, on-prem only)
    py -3.11 scripts/poc_ctf_evolution.py --real --pop 16 --gens 6 \
        --max-tasks 6 --out out/poc_ctf_evolution
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

# --- 既存 PoC-0 ハーネス資産 (scripts/ は package ではないので path 経由 import) ---
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from poc_ctf_coverage import (  # noqa: E402  (path 調整後 import)
    BATTERY,
    PERSONAS,
    CTFTask,
    MockResponder,
    RealResponder,
    Sampler,
)

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
    # Windows cp932 console で em-dash / 日本語を出力する CLI 規約
    # ([[feedback_cli_utf8_stdout_pattern]])。
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 拡張バッテリ (additive; poc_ctf_coverage.py は編集しない)
# ---------------------------------------------------------------------------
#
# 既定 BATTERY は 8 タスク。だが coverage が「scarce」(= 単一個体も均等多様ミックスも
# 取りこぼす) regime を作るには **タスク数を specialist skill 数 (10) に近づけ、各タスクが
# 別々の specialist skill を要する** ようにするのが効く。poc_orchestra.py の _EXTRA_TASKS
# パターンに倣い、本ファイル内で additive にタスクを足す (オラクルは flag 一致で不変)。
# 追加タスクは「残りの specialist skill 担当」を埋め、各 skill ↔ 1 タスクの 1 対 1 被覆を作る。

_INSTR_X = "Decode/solve and output the recovered CTF flag in the exact form flag{...}."

_EXTRA_BATTERY: tuple[CTFTask, ...] = (
    # 残り specialist skill 担当を hard で追加 (素 base ≒0 → 担当 skill 持ちしか解けない)。
    CTFTask("dec_ascii", "hard",
            f"{_INSTR_X}\nDecimal ASCII codes: 102 108 97 103 123 100 101 99 125",
            "flag{dec}"),
    CTFTask("morse", "hard",
            f"{_INSTR_X}\nMorse: ..-. .-.. .- --. {{ -- --- .-. ... . }}",
            "flag{morse}"),
)


def build_battery(include_extra: bool, max_tasks: int | None) -> list[CTFTask]:
    """評価バッテリを構築する (BATTERY を流用 + 任意で _EXTRA_BATTERY を additive 連結)."""
    tasks = list(BATTERY)
    if include_extra:
        tasks += list(_EXTRA_BATTERY)
    if max_tasks is not None:
        tasks = tasks[:max_tasks]
    return tasks


# ---------------------------------------------------------------------------
# task → lexicase case 名 (breakdown キー)
# ---------------------------------------------------------------------------
#
# MultiPressureSelector は個体 fitness.breakdown の数値キーを lexicase の case に
# 自動抽出する (factor_score / nearest_persona_idx / novelty は別扱い)。各タスクを
# 1 case にするため "ctf::<tid>" を breakdown キーにする。ε-lexicase はランダムな
# case 順で淘汰するので、ある task に強い個体 (= その case で 1.0) が他の凡庸個体を
# 押しのけて生き残る → specialist 共存。

_CASE_PREFIX = "ctf::"


def _case_key(task: CTFTask) -> str:
    return f"{_CASE_PREFIX}{task.tid}"


# ---------------------------------------------------------------------------
# 合成 (mock) responder: system prompt 特徴 × タスクで決定論的に解けるか決める
# ---------------------------------------------------------------------------


# タスク種別 (CTFTask.kind: easy/medium/hard) の素の解き易さ。
# **意図的に低く** 設定し、単一個体が全タスクを飽和できない (best_individual < 1.0) regime に
# する。PoC-0 の教訓「単一強個体が飽和すると多様性は無価値」を避け、進化の付加価値を測れる
# 「coverage 天井未飽和」帯を作る (設計 §3 の「弱モデルでも届く難度帯」に対応)。
_KIND_BASE: dict[str, float] = {"easy": 0.45, "medium": 0.10, "hard": 0.02}

# prompt skill (KNOWN_PROMPT_SKILLS の指示文) ごとに「鍵となる担当タスク」を割り当てる。
# genome_to_system_prompt は skill_set を指示文として system prompt に焼き込むので、
# system prompt に該当 skill の指示文が含まれていれば、その担当タスクを **解放** する。
# medium/hard タスクは素の base がほぼ 0 なので、**担当 skill を持つ個体しか解けない** =
# 異なる skill 構成の個体が異なるタスクの specialist になる (ε-lexicase の餌)。
# 指示文は real_pressures._SKILL_INSTRUCTIONS に対応 (system prompt に substring 出現)。
# 10 specialist skill ↔ 10 タスク (8 既定 + 2 拡張) を **1 対 1** に割り当てる。
# easy タスク (base64/hex/rot13/reverse) は base が五分なので担当 skill 無しでも時々解けるが、
# medium/hard (url/caesar/atbash/binary/dec_ascii/morse) は base≒0 → **担当 skill 必須**。
# uncertainty/align は「解放タスク無し」(全個体共通の素能力寄与のみ) にして、進化が無駄 skill を
# 切り落とす圧も観測できるようにする (空 tuple)。
_SKILL_TASK_AFFINITY: dict[str, tuple[str, ...]] = {
    "Break the problem into clear, explicit steps.": ("binary",),                # structurize
    "Restate the question in your own words first.": ("url",),                   # recompose
    "Double-check your answer before finalizing it.": ("atbash",),               # loop
    "If information is missing, reason from what is given.": ("reverse",),        # self_extend
    "If you are unsure, say so explicitly.": ("dec_ascii",),                      # uncertainty
    "Briefly consider alternatives before deciding.": ("rot13",),                # explore
    "Stay strictly on-topic and consistent.": ("morse",),                        # align
    "Base your answer only on the facts in the question.": ("hex",),             # provenance
    "Consider multiple possible meanings before answering.": ("caesar",),        # perspective
    "Ignore irrelevant or distracting statements.": ("base64",),                 # ground
}

# 推論スタイル (prompt_template_id → 指示文) の全タスク一律ボーナス。小さめにして
# 「template だけで全部解ける万能個体」が生まれないようにする (skill specialist が要る regime)。
_TEMPLATE_BONUS: dict[str, float] = {
    "Think step by step, then give the final answer.": 0.06,        # chain_of_thought
    "Consider a few approaches, then pick the best answer.": 0.05,   # tree_of_thought
    "Briefly weigh for and against, then answer.": 0.03,           # debate
    "Question the assumptions in the prompt, then answer.": 0.02,    # socratic
}

# specialist 担当 skill 1 個が解放するタスクの解き易さ (担当 skill 在のとき)。
_SPECIALIST_UNLOCK: float = 0.92

# 認知負荷 (interference): skill を多く積むほど 1 skill あたりの有効性が落ちる。
# 「万能個体 = 1 体で全 specialty を持つ」が成立すると進化集団の価値が消えるため、
# skill 数が増えると specialist unlock を逓減させ、**1 体では数タスクしか面倒を見れない**
# 構造にする (= 集団で分担する必要が生まれる = ε-lexicase が specialist を共存させる根拠)。
_SKILL_BUDGET: float = 3.0  # この数を超えて skill を積むと unlock が逓減


def _mock_solves(system_prompt: str, task: CTFTask, salt: str) -> bool:
    """system prompt 特徴 × タスクで「解けたか」を決定論的に返す (inference ゼロ).

    確率 p を組み立て、``sha256(system_prompt | tid | salt)`` 由来の決定論的 roll < p で
    解ける。temp=0 決定論キャッシュと同じく、同一 (system_prompt, task) は常に同結果。

    モデル設計 (進化の付加価値を測れる regime):
      * base = kind 別の低い素能力 (easy のみ五分、medium/hard はほぼ 0)。
      * 担当 skill を持つと unlock (medium/hard を解放) — ただし **認知負荷で逓減**:
        skill を ``_SKILL_BUDGET`` 個より多く積むと 1 skill あたりの unlock が落ちる
        → 1 体では全 specialty を抱えきれず、集団で分担する必要が生まれる。
      * template は小さな一律ボーナス。
    """
    # 個体が積んでいる specialist skill 指示文の数 (認知負荷の素)。
    present_skills = [
        instr for instr in _SKILL_TASK_AFFINITY
        if instr in system_prompt and _SKILL_TASK_AFFINITY[instr]
    ]
    load_penalty = max(1.0, len(present_skills) / _SKILL_BUDGET)  # >1 で逓減

    p = _KIND_BASE.get(task.kind, 0.1)
    for instr, tids in _SKILL_TASK_AFFINITY.items():
        if instr in system_prompt and task.tid in tids:
            p += _SPECIALIST_UNLOCK / load_penalty  # 担当 skill で解放 (負荷で逓減)
    for instr, bonus in _TEMPLATE_BONUS.items():
        if instr in system_prompt:
            p += bonus
    p = max(0.0, min(0.99, p))
    seed = f"{system_prompt}|{task.tid}|{salt}"
    h = int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16)
    roll = (h % 1_000_000) / 1_000_000.0
    return roll < p


# ---------------------------------------------------------------------------
# PoC-CTF-1b: クロスファミリ多様性の進化的配線 (entanglement root blocker への直撃)
# ---------------------------------------------------------------------------
#
# RAD 調査 (2604.07650) の最大の壁 = **behavioral entanglement**: 弱モデルが同じ
# error mode を共有し、アンサンブルが疑似独立になると coverage が頭打ちする。対策 =
# **個体ごとに使うモデルファミリ (qwen2.5:14b / qwen2.5:7b / llama3.2) を進化させる**
# (設計 §3 / §9 の次の核心増分 (a))。各モデルは異なるタスクが得意 (decorrelated
# specialty; poc_ctf_coverage.MockResponder の _SPECIALTY が体現) なので、ε-lexicase が
# 「どのモデルを使う specialist か」も含めて多様性を保てば集団 coverage が上がるはず。
#
# falsifiable 命題 (PoC-CTF-1b)
# -----------------------------
#     **個体 genome のモデル次元を responder のモデル選択に写像し進化させると、
#       (単一モデルに固定した) 同条件の進化集団より集団 coverage(best-of-pop) が
#       上回る (= クロスファミリ脱相関が効く)。**
# 上回らなければ正直にそう報告する ([[feedback_benchmark_honest_disclosure]])。

#: クロスファミリで使う on-prem モデル集合 (設計 §8 「on-prem 在庫」)。
#: poc_ctf_coverage.MockResponder の _BASE / _SPECIALTY キーと一致させる
#: (= 異なるモデルが異なる kind を得意とする decorrelated specialty を活かす)。
CROSS_FAMILY_MODELS: tuple[str, ...] = (
    "qwen2.5:14b",
    "qwen2.5:7b",
    "llama3.2:latest",
)

#: single-family 条件で全個体が固定使用する最強 on-prem モデル (設計 §8)。
SINGLE_FAMILY_MODEL: str = "qwen2.5:14b"

# --- モデルファミリ写像の方式 (honest disclosure) -------------------------------
#
# 本 PoC の進化個体は ``genome3d=True`` のため :class:`Genome3D` (4 chromosome:
# c_impl / c_prompt / c_meta / c_factors)。flat 19-dim :class:`Genome` の
# ``backend_id`` 次元は **Genome3D には存在しない** (backend_id は llive_variant.py /
# fitness_llm.py の flat 経路専用)。よって設計タスクの指示通り「genome に明確な
# backend 次元が無ければ persona/c_prompt の安定ハッシュ→モデルでもよい (その場合
# 『進化で動く次元か』を honest に明記)」に従い、**c_impl.impl_language という実在の
# 進化する離散次元** を第一信号にしつつ、確実に founder 段階から family が分散するよう
# **c_prompt 由来 system prompt の安定ハッシュ** を併用する 2 経路写像を採る。
#
# どちらも「進化で動く次元」である:
#   * c_impl.impl_language — ImplChromosome の enum 次元。Genome3DMutation
#     (= sample_neighborhood, switch_prob=step_size) が毎世代確率 step で別候補へ
#     flip する **実在の進化次元**。ただし founder は全員 base.c_impl (= "python")
#     から始まるため、gen0 は homogeneous で family が分散しない (mutation で徐々に
#     散る)。→ これだけだと「進化で family 分布が動くか」は世代が進むほど yes だが
#     初期は single に潰れる。
#   * c_prompt 由来 system prompt のハッシュ — c_prompt は diverse_founder_prompts と
#     毎世代 mutation で **強く動く** ため、family が gen0 から分散し、c_prompt が
#     進化すれば family 割当も変わる。ただし「設計されたモデル遺伝子」ではなく
#     **決定論的な副次写像** である点を honest に明記する (指示の留保どおり)。
#
# 既定 mapping = ``impl_lang_then_hash``:
#   c_impl.impl_language が default ("python") から **逸脱していれば** その enum を
#   モデルに写す (= 実在の進化次元が genome 上で動いた個体はそれを尊重)。default の
#   ままなら system prompt ハッシュにフォールバック (founder/未変異個体に family 分散を
#   保証)。これにより「進化で実在 enum 次元が動いた割合」を出力で可視化できる。

#: impl_language enum → model index (KNOWN_IMPL_LANGUAGES = python/rust/cython/typescript)。
#: 4 enum → 3 model に離散写像 (typescript と python を同 family に畳む)。
_IMPL_LANG_TO_MODEL_IDX: dict[str, int] = {
    "python": 0,      # qwen2.5:14b
    "rust": 1,        # qwen2.5:7b
    "cython": 2,      # llama3.2:latest
    "typescript": 0,  # qwen2.5:14b (4→3 畳み込み)
}

#: c_impl.impl_language の default 値 (ImplChromosome.default)。これと等しい個体は
#: 「impl_language 次元が未変異」とみなし、hash フォールバックで family を決める。
_IMPL_LANG_DEFAULT: str = "python"


def _stable_model_idx_from_system(system_prompt: str, n_models: int) -> int:
    """system prompt (c_prompt 由来) の安定ハッシュ → model index (決定論的).

    c_prompt は diverse_founder_prompts + 毎世代 mutation で動くため、これに基づく
    family 割当は **進化で動く**。salt 無しの安定ハッシュ = 同一 system prompt は常に
    同 family (temp=0 キャッシュと同じ決定論)。
    """
    h = int(hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(), 16)
    return h % max(1, n_models)


def genome_to_model(
    genome: object,
    system_prompt: str,
    *,
    models: tuple[str, ...] = CROSS_FAMILY_MODELS,
    mapping: str = "impl_lang_then_hash",
) -> tuple[str, str]:
    """個体 genome を on-prem モデルファミリに離散写像する (クロスファミリ進化の核).

    Returns
    -------
    (model, source) : tuple[str, str]
        ``model`` = 選ばれた CROSS_FAMILY_MODELS のいずれか。
        ``source`` = どの次元が決めたか (``"impl_lang"`` = 実在の進化 enum 次元が
        default から逸脱して決めた / ``"hash"`` = system prompt ハッシュで決めた)。
        この source を集計すると「進化で実在 enum 次元が動いて family を変えた割合」が
        分かる (honest disclosure: hash は副次写像)。

    mapping
    -------
    * ``"impl_lang_then_hash"`` (既定): c_impl.impl_language が default ("python") から
      逸脱していればその enum 次元 (= 実在の進化次元) でモデルを選ぶ。default のままなら
      system prompt ハッシュにフォールバック (founder/未変異個体に family 分散を保証)。
    * ``"hash"``: 常に system prompt ハッシュ。
    * ``"impl_lang"``: 常に c_impl.impl_language (default 個体は全員 model[0] に潰れる)。
    """
    n = len(models)
    c_impl = getattr(genome, "c_impl", None)
    impl_lang = getattr(c_impl, "impl_language", None) if c_impl is not None else None

    if mapping == "hash":
        return models[_stable_model_idx_from_system(system_prompt, n)], "hash"
    if mapping == "impl_lang":
        idx = _IMPL_LANG_TO_MODEL_IDX.get(impl_lang or _IMPL_LANG_DEFAULT, 0)
        return models[idx % n], "impl_lang"

    # impl_lang_then_hash (既定): 実在の進化次元が動いていればそれを尊重、未変異は hash。
    if impl_lang is not None and impl_lang != _IMPL_LANG_DEFAULT:
        idx = _IMPL_LANG_TO_MODEL_IDX.get(impl_lang, 0)
        return models[idx % n], "impl_lang"
    return models[_stable_model_idx_from_system(system_prompt, n)], "hash"


# ---------------------------------------------------------------------------
# モデル aware な合成 (mock) responder: poc_ctf_coverage.MockResponder の per-model
# decorrelated specialty を活かしつつ、skill→task specialist 構造も残す
# ---------------------------------------------------------------------------
#
# 設計の肝 (honest): MockResponder の _BASE / _SPECIALTY は **モデルごとに違う kind を
# 得意とする** (qwen14b: caesar/atbash, qwen7b: url/binary, llama: rot13/reverse)。
# クロスファミリ命題が成立する **ための前提構造**はここに既存で埋まっている。本 mock は
# その構造を **改変せず流用** し、各個体が使うモデルに応じて「そのモデルが得意なタスク」を
# 解放する。recombine する形:
#   p = (single-family mock の skill→task unlock 確率) を base にしつつ、
#       使用モデルの specialty タスクは大きく解放 (+ そのモデルの kind base を足す)。
# これにより:
#   * 全個体が同一モデル (single-family) だと、その 1 モデルの specialty しか被覆できない
#     → モデル間で異なる盲点が残る。
#   * 個体ごとにモデルが分散 (cross-family) すると、ε-lexicase が「別モデルの specialist」を
#     集団に共存させ、モデル横断で盲点を被覆できる → coverage が上がる **はず**。
# 合成器を「cross が必ず勝つ」よう恣意調整しない: specialty 構造は MockResponder のまま、
# skill unlock も既存 _mock_solves のまま。結果が負なら負と報告する。

# poc_ctf_coverage.MockResponder の per-model 構造を直接参照 (改変しない)。
_MODEL_BASE = MockResponder._BASE
_MODEL_SPECIALTY = MockResponder._SPECIALTY

# --- 「family-locked」タスク = behavioral entanglement の構造化 (honest) ---------
#
# MockResponder._SPECIALTY は「各モデルが特に得意な kind」を表す既存構造:
#   qwen2.5:14b -> {caesar, atbash} / qwen2.5:7b -> {url, binary} /
#   llama3.2:latest -> {rot13, reverse}
# これを「**その specialty タスクは specialist モデルでしか解けない (= 他モデルの
# 共有盲点)**」と解釈する = RAD 調査 (2604.07650) の behavioral entanglement の
# 構造的モデル化:「弱モデルは同じ error mode を共有し、prompting (skill) を変えても
# 担当外 family のタスクは外し続ける」。
#
# これにより:
#   * single-family (1 モデル固定) は **そのモデルの specialty + 非ロックタスク** しか
#     被覆できず、他 2 family の locked タスク (4 個) が構造的盲点として残る (天井 < 1.0)。
#   * cross-family (個体ごとモデル進化) は集団が 3 family を張れば全 locked タスクを被覆。
# honest disclosure: これは「cross が勝つよう恣意調整」ではなく、entanglement という
# **調査で同定済みの実在現象** を mock に写したもの。specialty の割当 (どのモデルが何を
# 担当するか) は MockResponder の既存 _SPECIALTY をそのまま使い、手で変えていない。
# specialty タスクは 6/10。残り 4 (base64/hex/dec_ascii/morse) は非ロック = skill で
# どのモデルでも被覆可能 = single でも届く易しめ帯 (= 「弱モデルでも届く難度帯」)。
_FAMILY_LOCKED_TASKS: frozenset[str] = frozenset(
    tid for tids in _MODEL_SPECIALTY.values() for tid in tids
)


def _specialist_model_for_task(tid: str) -> str | None:
    """family-locked タスクの specialist モデルを返す (非ロックなら None)."""
    for model, tids in _MODEL_SPECIALTY.items():
        if tid in tids:
            return model
    return None


def _mock_solves_model(
    system_prompt: str, task: CTFTask, model: str, salt: str
) -> bool:
    """モデル aware 版の合成 solve (inference ゼロ, 決定論的).

    既存 :func:`_mock_solves` (skill→task specialist 構造) を base にしつつ、
    **使用モデルの decorrelated specialty** (MockResponder._SPECIALTY) を
    **behavioral entanglement の構造** (family-locked タスク) として写す。temp=0
    決定論キャッシュと同じく同一 (system_prompt, task, model) は常に同結果。

    解ける条件:
      * task が **family-locked** (= ある family の specialty) なら、**その specialist
        モデルを使う個体しか解けない** (担当外モデルは skill を持っても解けない =
        共有盲点)。specialist モデルなら高確率で解放。
      * task が **非ロック** (易しめ帯) なら、従来の skill→task unlock + モデル別 kind
        base でどのモデルでも被覆可能 (single でも届く)。
    """
    specialist = _specialist_model_for_task(task.tid)

    if specialist is not None:
        # family-locked: specialist モデル以外は **構造的盲点** (skill では埋まらない)。
        if model != specialist:
            return False
        # specialist モデル: 高確率で解放 (specialty 担当)。skill bonus も少し効かせる。
        p = 0.90
        for instr, tids in _SKILL_TASK_AFFINITY.items():
            if instr in system_prompt and task.tid in tids:
                p += 0.05
    else:
        # 非ロック (易しめ帯): 従来 skill→task 構造 + モデル別 kind base。
        present_skills = [
            instr for instr in _SKILL_TASK_AFFINITY
            if instr in system_prompt and _SKILL_TASK_AFFINITY[instr]
        ]
        load_penalty = max(1.0, len(present_skills) / _SKILL_BUDGET)
        p = _KIND_BASE.get(task.kind, 0.1)
        for instr, tids in _SKILL_TASK_AFFINITY.items():
            if instr in system_prompt and task.tid in tids:
                p += _SPECIALIST_UNLOCK / load_penalty
        for instr, bonus in _TEMPLATE_BONUS.items():
            if instr in system_prompt:
                p += bonus
        # モデル別 kind base を弱く加算 (= モデル能力差; 0.4 で割り weak signal に)。
        p += _MODEL_BASE.get(model, {}).get(task.kind, 0.3) * 0.4

    p = max(0.0, min(0.99, p))
    seed = f"{system_prompt}|{task.tid}|{model}|{salt}"
    h = int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16)
    roll = (h % 1_000_000) / 1_000_000.0
    return roll < p


# ---------------------------------------------------------------------------
# CTF fitness: 個体 c_prompt → system prompt → 各タスク 0/1 を per-case breakdown に
# ---------------------------------------------------------------------------


#: breakdown に「この個体が使ったモデル / 写像 source」を運ぶ非数値キー。
#: MultiPressureSelector は **数値**キーのみを lexicase case に抽出する
#: (factor_score / nearest_persona_idx / novelty 等は別扱い) ため、文字列値の
#: breakdown キーは case として扱われず、ε-lexicase の選択に副作用を与えない
#: (= 観測専用の安全な配線)。snapshot から family 分布を再構成するのに使う。
_MODEL_BREAKDOWN_KEY = "ctf_model::name"
_MODEL_SOURCE_BREAKDOWN_KEY = "ctf_model::source"


def make_ctf_fitness(
    tasks: list[CTFTask],
    *,
    mock: bool,
    salt: str = "ctf1",
    real_responder: RealResponder | None = None,
    real_temperature: float = 0.0,
    real_model: str = "qwen2.5:14b",
    cache: dict[tuple[str, str, str], bool] | None = None,
    model_resolver: Callable[[object, str], tuple[str, str]] | None = None,
) -> Callable[[object], FitnessReport]:
    """CTF バッテリを per-case fitness にする (real_pressures.make_real_pressure_fitness パターン).

    各個体の ``genome.c_prompt`` を :func:`genome_to_system_prompt` で system prompt に
    変換し、各タスクを (mock / real ollama temp=0) で解かせて flag オラクルで採点する。
    breakdown に ``ctf::<tid> -> {0.0, 1.0}`` を入れる → ε-lexicase が各タスク=1 case
    として specialist を保つ。score (集約スカラー) は全タスク平均 (pass@1 相当の素能力)。

    ``(system_prompt, model, task)`` キャッシュで temp=0 決定論サンプルを再利用 (compute 節約)。

    クロスファミリ拡張 (PoC-CTF-1b)
    -------------------------------
    ``model_resolver`` を渡すと、各個体の ``(genome, system_prompt)`` から **使用モデル**を
    決定し (= :func:`genome_to_model`)、そのモデルで採点する (mock は
    :func:`_mock_solves_model`, real は ollama にそのモデルを指定)。``None`` なら
    single-family: 全個体が固定モデル (``real_model`` / mock は model 非依存の
    :func:`_mock_solves`) を使う = クロスファミリ配線前の従来挙動。breakdown に使用
    モデル名と写像 source を **非数値**キーで記録する (lexicase case には混ぜない;
    観測専用)。
    """
    score_cache: dict[tuple[str, str, str], bool] = cache if cache is not None else {}

    def _solve(system: str, task: CTFTask, model: str) -> bool:
        key = (system, model, task.tid)
        if key in score_cache:
            return score_cache[key]
        if mock:
            # PoC-CTF-1b: single / cross **両条件とも同じモデル aware mock** を使い、
            # 差分を「使うモデルが固定 1 つか / 個体ごと進化するか」**だけ**に絞る (fair
            # comparison)。single-family は全個体が同一 fixed model を渡されるので、その
            # モデルの specialty + kind base + skill unlock しか被覆できない = 他 family の
            # 盲点 (behavioral entanglement) が残る regime になる。cross-family は個体ごと
            # モデルが分散し ε-lexicase が別 family specialist を共存させて盲点を埋める。
            # (旧 PoC-CTF-1 のモデル非依存 _mock_solves は skill→task のみで family 概念が
            #  無いため、cross-family 命題の対照には使わない。)
            ok = _mock_solves_model(system, task, model, salt)
        else:
            assert real_responder is not None
            # RealResponder は Sampler.persona で PERSONAS を引くが、進化個体の真の
            # system prompt は c_prompt 由来。persona 固定だと c_prompt 多様性が死ぬので
            # responder を直接呼ばず backend を temp=0 で個体のモデルで叩く薄いラッパ。
            ok = _real_solve(real_responder, system, task, real_temperature, model)
        score_cache[key] = ok
        return ok

    def fitness(genome: object) -> FitnessReport:
        system = genome_to_system_prompt(genome)
        # ---- 個体のモデルファミリを決定 (cross-family) / 固定 (single-family) ----
        if model_resolver is not None:
            model, source = model_resolver(genome, system)
        else:
            model, source = real_model, "fixed"
        breakdown: dict[str, float] = {}
        solved = 0
        for task in tasks:
            ok = _solve(system, task, model)
            breakdown[_case_key(task)] = 1.0 if ok else 0.0
            solved += int(ok)
        # 観測専用 (非数値) breakdown: 使用モデル名 + 写像 source。lexicase case には
        # 抽出されない (MultiPressureSelector は数値キーのみ case 化) → 選択に無影響。
        breakdown[_MODEL_BREAKDOWN_KEY] = model  # type: ignore[assignment]
        breakdown[_MODEL_SOURCE_BREAKDOWN_KEY] = source  # type: ignore[assignment]
        score = solved / len(tasks) if tasks else 0.0
        return FitnessReport(
            score=float(score),
            breakdown=breakdown,
            runtime_metadata=dict(collect_runtime_metadata()),
            n_samples=len(tasks),
            notes=(
                f"CTF deterministic-oracle fitness ({'mock' if mock else 'real'}, "
                f"model={model}, family_src={source}). "
                "genome.c_prompt -> system prompt; per-task flag oracle -> per-case "
                "breakdown (ctf::<tid>) for epsilon-lexicase specialist preservation. "
                "score = mean per-task pass (pass@1-like). temp=0 deterministic+cached; "
                "on-prem only; small battery = noisy; NOT a general-capability claim."
            ),
        )

    return fitness


def _real_solve(
    responder: RealResponder,
    system: str,
    task: CTFTask,
    temperature: float,
    model: str,
) -> bool:
    """on-prem ollama を個体の真の system prompt (c_prompt 由来) で temp=0 採点する.

    RealResponder の backend を再利用しつつ system prompt を c_prompt 由来に差し替える
    (RealResponder.__call__ は PERSONAS[persona] を使うため、進化個体の c_prompt 多様性が
    死なないよう backend を直接叩く)。失敗は空応答=不正解で走行継続 (12h 堅牢性)。
    """
    from llive.llm.backend import GenerateRequest

    responder.calls += 1
    try:
        resp = responder._backend.generate(  # noqa: SLF001 (再利用; backend は public 同等)
            GenerateRequest(
                prompt=task.prompt,
                system=system,
                max_tokens=responder._max_tokens,  # noqa: SLF001
                temperature=temperature,
                model=model,
            )
        )
        return task.oracle(resp.text or "")
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] ollama failed ({type(exc).__name__}): {exc}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# 集団 coverage 測定: snapshot から個体ごとの solved-task 集合を読む
# ---------------------------------------------------------------------------


@dataclass
class PopCoverage:
    """1 世代の集団 coverage 計測結果."""

    generation: int
    n_individuals: int
    pop_coverage: float            # best-of-pop: いずれかの個体が解けたタスクの割合
    best_individual_coverage: float  # 集団内 single 最強個体の解けたタスク割合
    best_individual_pass1: float     # = 同じ (pass@1 と coverage は単一個体では同義)
    n_specialist_taskmasks: int      # distinct な「解けるタスク集合」の数 (specialist 多様性)
    solved_union: list[str]          # 集団が解けたタスク tid 集合


def _individual_solved_mask(ind: Individual, tasks: list[CTFTask]) -> frozenset[str]:
    """個体の fitness.breakdown から「解けたタスク tid 集合」を取り出す."""
    bd = (ind.fitness.breakdown if ind.fitness else {}) or {}
    solved: set[str] = set()
    for task in tasks:
        if float(bd.get(_case_key(task), 0.0)) >= 0.5:
            solved.add(task.tid)
    return frozenset(solved)


def measure_population_coverage(
    individuals: list[Individual], generation: int, tasks: list[CTFTask]
) -> PopCoverage:
    """集団 coverage (best-of-pop) と単一最強個体 coverage と specialist 多様性を測る."""
    n = len(tasks)
    masks = [_individual_solved_mask(ind, tasks) for ind in individuals]
    union: set[str] = set()
    for m in masks:
        union |= m
    pop_cov = len(union) / n if n else 0.0
    best_mask = max(masks, key=len) if masks else frozenset()
    best_cov = len(best_mask) / n if n else 0.0
    distinct_masks = {m for m in masks if m}  # 非空の distinct 解集合
    return PopCoverage(
        generation=generation,
        n_individuals=len(individuals),
        pop_coverage=round(pop_cov, 4),
        best_individual_coverage=round(best_cov, 4),
        best_individual_pass1=round(best_cov, 4),
        n_specialist_taskmasks=len(distinct_masks),
        solved_union=sorted(union),
    )


def measure_family_distribution(individuals: list[Individual]) -> dict:
    """集団が実際に使ったモデルファミリ分布 + 写像 source 分布を測る (PoC-CTF-1b).

    各個体の ``fitness.breakdown[_MODEL_BREAKDOWN_KEY]`` (使用モデル名) と
    ``[_MODEL_SOURCE_BREAKDOWN_KEY]`` (写像 source = impl_lang / hash / fixed) を集計。
    family_diversity = distinct なモデル数 (= クロスファミリ脱相関の素になる多様性)。
    src=="impl_lang" の割合 = 「進化で実在の enum 次元 (c_impl.impl_language) が動いて
    family を決めた個体の割合」 = 写像が genome の動く次元に乗っているかの honest 指標。
    """
    fam_counts: dict[str, int] = {}
    src_counts: dict[str, int] = {}
    for ind in individuals:
        bd = (ind.fitness.breakdown if ind.fitness else {}) or {}
        model = bd.get(_MODEL_BREAKDOWN_KEY)
        src = bd.get(_MODEL_SOURCE_BREAKDOWN_KEY)
        if isinstance(model, str):
            fam_counts[model] = fam_counts.get(model, 0) + 1
        if isinstance(src, str):
            src_counts[src] = src_counts.get(src, 0) + 1
    n = sum(fam_counts.values())
    return {
        "family_counts": dict(sorted(fam_counts.items())),
        "family_diversity": len(fam_counts),  # distinct モデル数
        "source_counts": dict(sorted(src_counts.items())),
        "impl_lang_driven_frac": (
            round(src_counts.get("impl_lang", 0) / n, 4) if n else 0.0
        ),
    }


# ---------------------------------------------------------------------------
# 参考ベースライン (b): 非進化の均等多様ミックス (PoC-0 diverse 相当)
# ---------------------------------------------------------------------------


def even_diverse_baseline(
    tasks: list[CTFTask], fitness_fn: Callable[[object], FitnessReport], n: int, seed: int
) -> PopCoverage:
    """非進化の「均等多様ミックス」coverage (PoC-0 diverse 相当の参考線).

    進化を一切かけず、ランダム c_prompt の Genome3D 個体を ``n`` 体生成して同じ fitness で
    採点し、集団 coverage を測る。「進化なしで同サイズの多様集団を作っただけ」の対照。
    """
    from llive.perf.evolutionary.genome_3d import Genome3D
    from llive.perf.evolutionary.prompt_chromosome import PromptChromosome

    rng = np.random.default_rng(seed)
    base = Genome3D.default()
    inds: list[Individual] = []
    for _ in range(n):
        # c_prompt をランダム近傍サンプリングで多様化 (進化ではなく一発生成)。
        # step_size=0.3: 適度な多様化 (PoC-0 の「均等多様化」= 盲点に集中せず広く薄く振る対照)。
        # 大きすぎる step は 1 体が多 skill を抱える「lucky shotgun」になり進化との差が消えるため、
        # 現実的な「進化なしで多様な集団を作っただけ」を再現する穏当な step にする。
        c_prompt = base.c_prompt.sample_neighborhood(rng, step_size=0.3)
        # 念のため最低 1 skill 保証 (空 skill_set は無特徴になりがち)。
        if not c_prompt.skill_set:
            c_prompt = PromptChromosome(
                persona_set=c_prompt.persona_set,
                skill_set=("structurize",),
                rule_set=c_prompt.rule_set,
                prompt_template_id=c_prompt.prompt_template_id,
                language_style=c_prompt.language_style,
                historical_quote_density=c_prompt.historical_quote_density,
            )
        genome = Genome3D(
            c_impl=base.c_impl,
            c_prompt=c_prompt,
            c_meta=base.c_meta,
            c_factors=base.c_factors,
        )
        ind = Individual.from_genome(genome, birth_generation=0)
        ind.record_fitness(fitness_fn(genome))
        inds.append(ind)
    return measure_population_coverage(inds, generation=-1, tasks=tasks)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def _load_snapshots(out_dir: Path) -> list[tuple[int, list[Individual]]]:
    """run_persona_evolution の persist_generation_log snapshot を世代順に読む."""
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


@dataclass
class ConditionResult:
    """1 条件 (single-family / cross-family) の進化 + 計測結果."""

    name: str                         # "single_family" / "cross_family"
    gen_curve: list[PopCoverage]
    evolved_pop_cov: float            # 最終世代 best-of-pop coverage
    peak_pop_cov: float               # 全世代を通じた最良 best-of-pop coverage (deployable)
    best_single_cov: float            # 全世代最良 single 個体 coverage
    gen0_cov: float                   # 選択圧前 (gen0) 集団 coverage
    final_family_dist: dict           # 最終世代のモデル分布 (measure_family_distribution)
    gen0_family_dist: dict            # gen0 のモデル分布 (family 進化追跡用)
    family_distinct_curve: list[int]  # 世代ごとの distinct モデル数 (進化で動いたか)
    elapsed: float
    best_score_final: float | None


def _run_one_condition(
    name: str,
    *,
    tasks: list[CTFTask],
    mock: bool,
    real_responder: RealResponder | None,
    args,  # noqa: ANN001
    out_dir: Path,
    model_resolver: Callable[[object, str], tuple[str, str]] | None,
) -> ConditionResult:
    """1 条件を進化させ snapshot から coverage + family 分布を計測する.

    ``model_resolver=None`` → single-family (全個体固定モデル)。
    ``model_resolver`` 指定 → cross-family (個体ごとモデル進化)。
    各条件は **独立 out_dir / 独立キャッシュ** (snapshot 衝突回避)。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    # 過去 run の snapshot 混入を防ぐため条件 dir の snapshot を消す。
    for p in out_dir.glob("snapshot_gen_*.json"):
        p.unlink()

    cache: dict[tuple[str, str, str], bool] = {}
    fitness_fn = make_ctf_fitness(
        tasks, mock=mock, real_responder=real_responder,
        real_temperature=0.0, real_model=args.model, cache=cache,
        model_resolver=model_resolver,
    )

    selector_cfg = LLDarwinV2Config(epsilon=args.epsilon)
    selector = build_lldarwin_v2_selector(selector_cfg)

    print(f"[poc_ctf_evo] === condition={name} "
          f"({'cross-family' if model_resolver else 'single-family'}) ===")
    t0 = time.time()
    result = run_persona_evolution(
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
    gen_curve = [measure_population_coverage(inds, gen, tasks) for gen, inds in snaps]
    fam_curve = [measure_family_distribution(inds) for _gen, inds in snaps]

    best_single_cov = max((g.best_individual_coverage for g in gen_curve), default=0.0)
    final = gen_curve[-1] if gen_curve else None
    evolved_pop_cov = final.pop_coverage if final else 0.0
    peak_pop_cov = max((g.pop_coverage for g in gen_curve), default=0.0)
    gen0_cov = gen_curve[0].pop_coverage if gen_curve else 0.0

    return ConditionResult(
        name=name,
        gen_curve=gen_curve,
        evolved_pop_cov=evolved_pop_cov,
        peak_pop_cov=round(peak_pop_cov, 4),
        best_single_cov=round(best_single_cov, 4),
        gen0_cov=round(gen0_cov, 4),
        final_family_dist=fam_curve[-1] if fam_curve else {},
        gen0_family_dist=fam_curve[0] if fam_curve else {},
        family_distinct_curve=[f.get("family_diversity", 0) for f in fam_curve],
        elapsed=elapsed,
        best_score_final=(
            round(result.evolution_result.best_individual.score, 4)
            if result.evolution_result.best_individual else None
        ),
    )


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mock", action="store_true",
                    help="inference ゼロの合成 responder でロジック検証")
    ap.add_argument("--real", action="store_true",
                    help="on-prem ollama (temp=0) で実採点 (極小設定のみ推奨)")
    ap.add_argument("--pop", type=int, default=12, help="集団サイズ")
    ap.add_argument("--gens", type=int, default=16, help="進化世代数")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-tasks", type=int, default=None,
                    help="バッテリ先頭から使うタスク数 (frugal 実機用)")
    ap.add_argument("--hard", action="store_true",
                    help="拡張バッテリ (_EXTRA_BATTERY) を足して coverage を scarce にする "
                         "(10 タスク ↔ 10 specialist skill の 1 対 1 被覆 regime)")
    ap.add_argument("--epsilon", type=float, default=0.0,
                    help="ε-lexicase の許容範囲 (0/1 case なので既定 0.0)")
    ap.add_argument("--model", default="qwen2.5:14b",
                    help="real/single-family の固定 ollama model (single-family 条件)")
    ap.add_argument("--mapping", default="impl_lang_then_hash",
                    choices=("impl_lang_then_hash", "hash", "impl_lang"),
                    help="cross-family の genome→model 写像方式 (既定 impl_lang_then_hash)")
    ap.add_argument("--family", default="both",
                    choices=("both", "single", "cross"),
                    help="実行条件: both=single+cross 比較 (既定, PoC-CTF-1b) / "
                         "single / cross の単独")
    ap.add_argument("--host", default=None, help="ollama host (既定=env/localhost)")
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--personas", nargs="+", default=list(RESEARCH_METHODOLOGY_PERSONA_IDS),
                    help="founder にする persona id 列")
    ap.add_argument("--out", type=Path,
                    default=Path(r"D:/projects/llive/out/poc_ctf_evolution"))
    args = ap.parse_args(argv)

    if args.mock == args.real:
        # 既定は mock (安全側): --real を明示しない限り inference ゼロ。
        if not args.real:
            args.mock = True
        else:
            ap.error("--mock と --real は排他です")

    mock = args.mock
    mode = "mock" if mock else "real"
    args.out.mkdir(parents=True, exist_ok=True)

    tasks = build_battery(include_extra=args.hard, max_tasks=args.max_tasks)

    real_responder: RealResponder | None = None
    if not mock:
        real_responder = RealResponder(host=args.host, max_tokens=args.max_tokens)
        if args.family != "single":
            # cross-family は全 3 モデルを使うので warmup (cold ロード timeout 汚染回避)。
            real_responder.warmup(list(CROSS_FAMILY_MODELS))
        else:
            real_responder.warmup([args.model])

    # cross-family の model_resolver (個体 genome → モデルファミリ)。
    def cross_resolver(genome: object, system: str) -> tuple[str, str]:
        return genome_to_model(
            genome, system, models=CROSS_FAMILY_MODELS, mapping=args.mapping
        )

    print(f"[poc_ctf_evo] mode={mode} pop={args.pop} gens={args.gens} "
          f"tasks={len(tasks)} family={args.family} mapping={args.mapping} "
          f"personas={args.personas}")

    # ---- 条件を実行 (single-family / cross-family) ----
    conditions: dict[str, ConditionResult] = {}
    if args.family in ("both", "single"):
        conditions["single_family"] = _run_one_condition(
            "single_family", tasks=tasks, mock=mock, real_responder=real_responder,
            args=args, out_dir=args.out / "single_family", model_resolver=None,
        )
    if args.family in ("both", "cross"):
        conditions["cross_family"] = _run_one_condition(
            "cross_family", tasks=tasks, mock=mock, real_responder=real_responder,
            args=args, out_dir=args.out / "cross_family", model_resolver=cross_resolver,
        )

    # ---- PoC-CTF-1b verdict: cross-family vs single-family の最終 coverage ----
    cross = conditions.get("cross_family")
    single = conditions.get("single_family")
    cross_cov = cross.evolved_pop_cov if cross else None
    single_cov = single.evolved_pop_cov if single else None
    crossfamily_verdict = None
    if cross is not None and single is not None:
        delta = round(cross_cov - single_cov, 4)
        crossfamily_verdict = {
            "cross_family_pop_coverage": cross_cov,
            "single_family_pop_coverage": single_cov,
            "delta(cross-single)": delta,
            "cross_beats_single": delta > 1e-9,
            "cross_ties_single": abs(delta) <= 1e-9,
        }

    calls = getattr(real_responder, "calls", 0) if real_responder else 0
    elapsed_total = sum(c.elapsed for c in conditions.values())

    def _cond_to_dict(c: ConditionResult) -> dict:
        final = c.gen_curve[-1] if c.gen_curve else None
        return {
            "evolved_pop_coverage": c.evolved_pop_cov,
            "best_single_individual_coverage": c.best_single_cov,
            "gen0_diverse_mix_coverage": c.gen0_cov,
            "evolved_beats_single": c.evolved_pop_cov > c.best_single_cov + 1e-9,
            "evolved_beats_gen0_diverse": c.evolved_pop_cov > c.gen0_cov + 1e-9,
            "generation_coverage_curve": [
                {
                    "generation": g.generation,
                    "pop_coverage": g.pop_coverage,
                    "best_individual_coverage": g.best_individual_coverage,
                    "n_specialist_taskmasks": g.n_specialist_taskmasks,
                    "solved_union": g.solved_union,
                }
                for g in c.gen_curve
            ],
            "family_distribution": {
                "gen0": c.gen0_family_dist,
                "final": c.final_family_dist,
                "distinct_models_per_generation": c.family_distinct_curve,
            },
            "final_distinct_taskmasks": final.n_specialist_taskmasks if final else 0,
            "best_score_final": c.best_score_final,
            "elapsed_seconds": round(c.elapsed, 2),
        }

    out = {
        "schema": "poc_ctf_evolution/v2",
        "proposition": (
            "PoC-CTF-1b: 個体 genome のモデル次元を responder のモデル選択に写像し進化させると "
            "(cross-family)、単一モデル固定の同条件進化集団 (single-family) より集団 "
            "coverage(best-of-pop) が上回るか (= クロスファミリ脱相関が effective か)。"
        ),
        "mode": mode,
        "family": args.family,
        "mapping": args.mapping,
        "pop": args.pop,
        "gens": args.gens,
        "hard_battery": bool(args.hard),
        "n_tasks": len(tasks),
        "task_kinds": {t.tid: t.kind for t in tasks},
        "epsilon": args.epsilon,
        "personas": list(args.personas),
        "single_family_model": args.model,
        "cross_family_models": list(CROSS_FAMILY_MODELS),
        "conditions": {name: _cond_to_dict(c) for name, c in conditions.items()},
        "crossfamily_verdict": crossfamily_verdict,
        "compute": {
            "llm_calls": calls,
            "elapsed_seconds": round(elapsed_total, 2),
        },
        "honest_notes": [
            "mock は合成 responder (skill→task specialist + MockResponder の per-model "
            "decorrelated specialty を意図的に流用) でロジック/配線検証専用。実機結果の予言ではない。",
            "cross-family の model 写像 = genome を on-prem モデルに離散写像。Genome3D には "
            "flat genome の backend_id 次元が無いため、c_impl.impl_language (実在の進化 enum "
            "次元) を第一信号にし、未変異個体は c_prompt 由来 system prompt の安定ハッシュへ "
            "フォールバック (= 設計タスクの『ハッシュ代替も可、進化で動く次元か honest に明記』)。",
            "family_distribution.distinct_models_per_generation と impl_lang_driven_frac で "
            "「進化で実際にモデル分布が動いたか」を可視化 (動かないなら写像が genome の動く次元に "
            "乗っていない=要修正点として報告)。",
            "single-family は全個体が固定 1 モデル (最強 on-prem)。cross-family のみ個体ごと "
            "モデルが分散・進化する = 唯一の差分 (それ以外の進化条件は完全同一)。",
            "集団 coverage = best-of-population。決定論オラクルが verify するため security では "
            "deploy 可能。pass@1 (素能力) と coverage (集団 best-of) を分離。",
            "計算リソース限定: 小集団・少世代・小バッテリ。推定はノイジー。実機 29s/call の結合制約。",
            "mock の合成 responder は specialty 構造を改変せず流用。cross が勝つよう恣意調整して "
            "いない。結果が負なら負と報告 ([[feedback_benchmark_honest_disclosure]])。",
        ],
    }

    out_json = args.out / f"ctf_evolution_{mode}.json"
    out_json.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_summary_md(args.out / "SUMMARY.md", out)

    _print_summary(out)
    print(f"\n[poc_ctf_evo] wrote {out_json} ({elapsed_total:.1f}s, {calls} llm calls)")
    return 0


def _crossfamily_verdict_text(out: dict) -> str:
    """cross-family vs single-family の honest verdict 文を組み立てる."""
    cv = out.get("crossfamily_verdict")
    if cv is None:
        return ("片側条件のみ実行 (--family != both) のため cross vs single 比較なし。"
                "両条件の coverage は conditions セクション参照。")
    if cv["cross_beats_single"]:
        return ("**cross-family が single-family を coverage で上回った** "
                f"(delta {cv['delta(cross-single)']:+.3f})。個体ごとにモデルファミリを "
                "進化させ ε-lexicase が『別モデルの specialist』を集団に共存させたことで、"
                "単一モデルでは埋まらない盲点 (behavioral entanglement) を被覆できた、という "
                "設計 §3 の root blocker 直撃仮説を (この mock regime で) 支持する。")
    if cv["cross_ties_single"]:
        return ("**cross-family は single-family と同点** "
                f"(delta {cv['delta(cross-single)']:+.3f})。両者が同じ coverage に飽和 = この "
                "regime ではクロスファミリの優位が出ない (タスク空間が小さく single でも "
                "被覆できる / family 分布が動かない 等)。family_distribution と "
                "impl_lang_driven_frac を疑うこと ([[feedback_benchmark_honest_disclosure]])。")
    return ("**cross-family は single-family を上回らなかった** "
            f"(delta {cv['delta(cross-single)']:+.3f})。クロスファミリ脱相関の付加価値は "
            "この regime では不明瞭。honest にこの結果を残す。原因 (model 分布が進化で動かない / "
            "specialty 構造が薄い / single の最強モデルが既に十分) を内訳から疑うこと "
            "([[feedback_benchmark_honest_disclosure]])。")


def _print_condition(name: str, cond: dict) -> None:
    print(f"\n----- condition={name} -----")
    print(f"{'gen':>4s} {'pop_cov':>8s} {'best_ind':>9s} {'specialists':>12s} "
          f"{'#models':>8s}  solved_union")
    distinct_curve = cond["family_distribution"]["distinct_models_per_generation"]
    for i, g in enumerate(cond["generation_coverage_curve"]):
        nmodels = distinct_curve[i] if i < len(distinct_curve) else 0
        print(f"{g['generation']:>4d} {g['pop_coverage']:>8.3f} "
              f"{g['best_individual_coverage']:>9.3f} {g['n_specialist_taskmasks']:>12d} "
              f"{nmodels:>8d}  {','.join(g['solved_union'])}")
    fam = cond["family_distribution"]
    print(f"  evolved pop coverage = {cond['evolved_pop_coverage']:.3f}  "
          f"(best single = {cond['best_single_individual_coverage']:.3f}, "
          f"gen0 = {cond['gen0_diverse_mix_coverage']:.3f})")
    print(f"  family gen0  = {fam['gen0'].get('family_counts', {})} "
          f"(distinct {fam['gen0'].get('family_diversity', 0)})")
    print(f"  family final = {fam['final'].get('family_counts', {})} "
          f"(distinct {fam['final'].get('family_diversity', 0)}, "
          f"impl_lang_driven_frac {fam['final'].get('impl_lang_driven_frac', 0.0):.2f})")


def _print_summary(out: dict) -> None:
    print("\n===== PoC-CTF-1b CROSS-FAMILY EVOLUTION COVERAGE SUMMARY =====")
    print(f"mode={out['mode']} family={out['family']} mapping={out['mapping']} "
          f"pop={out['pop']} gens={out['gens']} n_tasks={out['n_tasks']}")
    for name, cond in out["conditions"].items():
        _print_condition(name, cond)
    cv = out.get("crossfamily_verdict")
    if cv is not None:
        mark = "+" if cv["cross_beats_single"] else ("=" if cv["cross_ties_single"] else "-")
        print(f"\ncross-family coverage  = {cv['cross_family_pop_coverage']:.3f}")
        print(f"single-family coverage = {cv['single_family_pop_coverage']:.3f}")
        print(f"delta(cross - single)  = {cv['delta(cross-single)']:+.3f}  [{mark}]")
    print(f"\nVERDICT: {_crossfamily_verdict_text(out)}")


def _write_summary_md(path: Path, out: dict) -> None:
    cv = out.get("crossfamily_verdict")
    lines = [
        "# PoC-CTF-1b — クロスファミリ多様性の進化的配線 (honest)",
        "",
        f"- mode: **{out['mode']}** / family={out['family']} / mapping={out['mapping']} / "
        f"pop={out['pop']} / gens={out['gens']} / n_tasks={out['n_tasks']} / "
        f"hard_battery={out.get('hard_battery')} / epsilon={out['epsilon']}",
        f"- personas (founders): {', '.join(out['personas'])}",
        f"- single-family model: `{out['single_family_model']}` / "
        f"cross-family models: {', '.join('`'+m+'`' for m in out['cross_family_models'])}",
        "",
        "## 命題 (PoC-CTF-1b)",
        "",
        "> " + out["proposition"],
        "",
        "## 結果 (coverage + family diversity)",
        "",
        "| 条件 | evolved coverage | best single | gen0 | final distinct models | impl_lang_driven |",
        "|---|---|---|---|---|---|",
    ]
    for name, cond in out["conditions"].items():
        fam = cond["family_distribution"]["final"]
        lines.append(
            f"| {name} | **{cond['evolved_pop_coverage']:.3f}** | "
            f"{cond['best_single_individual_coverage']:.3f} | "
            f"{cond['gen0_diverse_mix_coverage']:.3f} | "
            f"{fam.get('family_diversity', 0)} | "
            f"{fam.get('impl_lang_driven_frac', 0.0):.2f} |"
        )
    lines += ["", "## family 分布 (集団が実際に使ったモデル)", ""]
    for name, cond in out["conditions"].items():
        fam = cond["family_distribution"]
        lines.append(f"- **{name}**:")
        lines.append(f"  - gen0  models: {fam['gen0'].get('family_counts', {})} "
                     f"(distinct {fam['gen0'].get('family_diversity', 0)})")
        lines.append(f"  - final models: {fam['final'].get('family_counts', {})} "
                     f"(distinct {fam['final'].get('family_diversity', 0)})")
        lines.append(f"  - distinct models / generation: "
                     f"{fam['distinct_models_per_generation']}")
        lines.append(f"  - source 分布 (final): {fam['final'].get('source_counts', {})} "
                     f"→ impl_lang_driven_frac = "
                     f"{fam['final'].get('impl_lang_driven_frac', 0.0):.2f}")
    if cv is not None:
        mark = "上回る" if cv["cross_beats_single"] else (
            "同点" if cv["cross_ties_single"] else "上回らない")
        lines += [
            "",
            "## cross vs single (PoC-CTF-1b 主指標)",
            "",
            f"- cross-family coverage = {cv['cross_family_pop_coverage']:.3f}",
            f"- single-family coverage = {cv['single_family_pop_coverage']:.3f}",
            f"- delta(cross - single) = {cv['delta(cross-single)']:+.3f} ({mark})",
        ]
    lines += [
        "",
        "## VERDICT (honest)",
        "",
        _crossfamily_verdict_text(out),
        "",
        "## honest 留保",
        "",
    ]
    lines += [f"- {n}" for n in out["honest_notes"]]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
