# SPDX-License-Identifier: Apache-2.0
"""PoC-CTF-3: tool-exec オラクルを進化の fitness に配線する (agentic 戦略の進化).

親ゴール: 進化型オーケストラ + RAPTOR 決定論オラクル + 無制限 test-time compute で
Claude Mythos をセキュリティ領域で超える
([[goal_surpass_mythos_evolutionary]] /
 fullsense docs/research/mythos_surpass_design_2026_05_27.md §8c「統合=進化の真の役割」/ §9)。

位置づけ (設計 §8c / PoC-CTF-2 実機の含意)
------------------------------------------
PoC-CTF-2 (実機, 修正 battery) で **コード実行 = レバー** が実証された:
qwen2.5:14b は no_tool(CoT) cov 0.625 → tool_exec cov 0.875 (caesar/atbash/binary が
FAIL→PASS 反転)。「方法は合うが頭の中の算術で外す」失敗を **正しい実行** が消去した。

レバーが実証されたので、**進化集団の役割が明確化** (設計 §8c「統合=進化の真の役割」):
個体は **agentic 戦略** (コードを書くか直接答えるか / どのアプローチ) を持ち、
**ε-lexicase が「どのタスク種でどの戦略が効くか」の specialist を集団に保つ**。
決定論オラクル (tool-exec 結果) が淘汰信号。test-time compute = 多数 agentic 試行。

falsifiable 命題 (PoC-CTF-3)
----------------------------
    **個体の c_prompt から「コードを書く/直接答える」agentic 戦略を発現させ、
      tool-exec オラクル (0/1) で ε-lexicase 進化させると、集団 coverage(best-of-pop)
      は「直接回答のみ (direct-only) に固定した同条件の進化集団」を上回る。**

上回らなければ正直にそう報告する ([[feedback_benchmark_honest_disclosure]])。

🔴 honest 留保 (最重要・過大主張防止)
-------------------------------------
* **自明 decode バッテリは tool-exec でほぼ満点 → 進化の伸びしろが小さい (飽和)**。
  PoC-0/1 の「飽和帯では進化無価値・非飽和帯で価値」教訓と整合。よって PoC-3 は主に
  **配線の mechanism 検証** と位置づける (進化の coverage gain 競争ではない)。
* **進化の価値は戦略選択が自明でない難タスクで出る**。``--hard`` で「naive な 1 発コードが
  失敗する / 複数アプローチを要する」軽い難タスクを additive で足し、伸びしろ regime を作る。
* mock は canned responder (正しいコード + 一部 direct-only 戦略は blind-spot 失敗) で
  **ロジック/配線検証専用**。実機予言ではない。

agentic 戦略遺伝子の写像 (進化で動く次元か honest に明記)
--------------------------------------------------------
PoC-CTF-1b の教訓: **c_prompt hash は進化で動く / impl enum は step 0.1 では動きにくい**。
よって戦略遺伝子は **c_prompt 由来の連続 tool-propensity** に乗せる (= 進化で動く次元):

  p_tool(individual) = clip(
      base
      + Σ_{skill ∈ TOOL_AFFINE_SKILLS}  +w  (個体の c_prompt.skill_set に在れば)
      + (template が CoT/ToT 系なら) +w_t
      + (stable hash(system_prompt) を [-jitter,+jitter] に写像)         ← gen0 から分散
  , 0, 1)

  戦略 = "code" if p_tool >= 0.5 else "direct"。

* TOOL_AFFINE_SKILLS (structurize/loop/explore/self_extend) は c_prompt.skill_set の
  bit flip で **毎世代動く実在の遺伝次元** → 「コードを書く傾向」が進化で増減する。
* hash 項は founder/未変異個体にも gen0 から戦略分散を保証する決定論的副次写像
  (PoC-CTF-1b の family 写像と同じ honest スタンス: ハッシュは副次、実 flip が主信号)。
* 出力に ``strategy_skill_driven_frac`` (= skill flip で戦略境界を跨いだ割合の代理) と
  世代ごとの code/direct 個体数を出し、「進化で戦略分布が動いたか」を可視化する。

再利用資産 (additive のみ; 本体は import 利用のみ・編集しない)
-----------------------------------------------------------
* ``scripts/poc_ctf_toolexec.py``: ``run_in_sandbox`` / ``extract_code`` /
  ``scan_dangerous`` (v2 filter) / ``build_tool_prompt`` / ``TOOL_PERSONA`` /
  ``BLIND_SPOT_TIDS`` / ``RealResponder``。
* ``scripts/poc_ctf_coverage.py``: ``BATTERY`` / ``PERSONAS`` / ``CTFTask`` /
  ``flag_oracle``。
* ``llive.perf.evolutionary``: ``genome_to_system_prompt`` / ``build_lldarwin_v2_selector``
  (ε-lexicase 確定 S1) / ``run_persona_evolution`` (Genome3D turnkey)。
  ``MultiPressureSelector`` が ``fitness.breakdown`` の数値キー (``ctf::<tid>``) を
  lexicase case に自動抽出 → specialist 共存 (自前 ε-lexicase 不要)。

使い方
------
::

    # ロジック検証 (inference ゼロ) — 飽和帯
    py -3.11 scripts/poc_ctf_agentic_evolution.py --mock --pop 16 --gens 12 \\
        --out out/poc_ctf_agentic_evolution

    # 伸びしろ regime (難タスク additive)
    py -3.11 scripts/poc_ctf_agentic_evolution.py --mock --hard --pop 16 --gens 12

    # 極小実機 (frugal, on-prem only, temp=0)
    $env:PYTHONPATH='D:\\projects\\llive\\src'
    py -3.11 scripts/poc_ctf_agentic_evolution.py --real --pop 8 --gens 4 --max-tasks 6
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

# --- scripts/ を path に入れて姉妹 PoC を import (package ではないため) ---
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from poc_ctf_coverage import (  # noqa: E402
    BATTERY,
    CTFTask,
)
from poc_ctf_toolexec import (  # noqa: E402
    BLIND_SPOT_TIDS,
    TOOL_PERSONA,
    RealResponder,
    build_tool_prompt,
    extract_code,
    run_in_sandbox,
    scan_dangerous,
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
# 拡張バッテリ (additive; 「naive な 1 発コードが失敗する / 複数アプローチを要する」難タスク)
# ---------------------------------------------------------------------------
#
# 自明 decode は tool-exec でほぼ満点 → 進化の伸びしろが小さい (飽和)。伸びしろ regime を
# 作るには「コードを書けば自明に解ける」だけでないタスクが要る。以下は **多段 / アプローチ
# 選択が要る** 軽い難タスクで、(a) 一発の naive decode では解けず (b) 戦略 (どの順で何を
# 適用するか) が効く。オラクルは flag 一致で不変 (poc_ctf_coverage.flag_oracle と同形)。

_INSTR_H = "Decode/solve and output the recovered CTF flag in the exact form flag{...}."

_HARD_BATTERY: tuple[CTFTask, ...] = (
    # base64 を 2 重に掛けたもの (naive な 1 回 decode では解けない = 多段)。
    # b64('flag{double}') = 'ZmxhZ3tkb3VibGV9' を更に b64 -> 'Wm14aFozdGtiM1ZpYkdWOQ=='。
    CTFTask("b64_double", "hard",
            f"{_INSTR_H}\nDouble Base64: Wm14aFozdGtiM1ZpYkdWOQ==",
            "flag{double}"),
    # hex(b64('flag{hexb64}')) — エンコード順の推定が要る (どちらから剥がすか)。
    # b64('flag{hexb64}') = 'ZmxhZ3toZXhiNjR9' -> その ascii を hex 化 = 下記。
    CTFTask("hex_then_b64", "hard",
            f"{_INSTR_H}\nHex of a Base64 string: "
            "5a6d78685a33746f5a5868694e6a5239",
            "flag{hexb64}"),
)


def build_battery(include_hard: bool, max_tasks: int | None) -> list[CTFTask]:
    tasks = list(BATTERY)
    if include_hard:
        tasks += list(_HARD_BATTERY)
    if max_tasks is not None:
        tasks = tasks[:max_tasks]
    return tasks


# ---------------------------------------------------------------------------
# agentic 戦略遺伝子: c_prompt → tool-propensity p_tool ∈ [0,1] → "code" / "direct"
# ---------------------------------------------------------------------------
#
# 進化で動く次元に乗せる (PoC-CTF-1b 教訓: c_prompt の skill flip / hash は動く)。

#: 「コードを書いて実行・検証する」disposition に対応する skill 群
#: (real_pressures._SKILL_INSTRUCTIONS の指示文に対応; system prompt に substring 出現)。
#:  structurize=明示的ステップ分解 / loop=答えを再確認 / explore=代替案検討 /
#:  self_extend=与件から再構成。いずれも「頭で済ませず手続きを踏む」= コード執筆寄り。
_TOOL_AFFINE_SKILL_INSTR: dict[str, float] = {
    "Break the problem into clear, explicit steps.": 0.18,   # structurize
    "Double-check your answer before finalizing it.": 0.15,  # loop
    "Briefly consider alternatives before deciding.": 0.12,  # explore
    "If information is missing, reason from what is given.": 0.10,  # self_extend
}

#: template が「複数手を考える」系なら tool 寄り (ToT/CoT)。
_TOOL_AFFINE_TEMPLATE_INSTR: dict[str, float] = {
    "Think step by step, then give the final answer.": 0.10,        # chain_of_thought
    "Consider a few approaches, then pick the best answer.": 0.12,   # tree_of_thought
}

#: 戦略の base propensity (skill/template 無し個体の出発点)。0.5 未満 = default は direct 寄り。
_TOOL_BASE: float = 0.30

#: stable hash 由来の jitter 幅 (gen0 から戦略を分散させる副次写像)。
_TOOL_HASH_JITTER: float = 0.30

#: code/direct を分ける閾値。
_TOOL_THRESHOLD: float = 0.50


def _stable_hash_unit(text: str) -> float:
    """text → [0,1) の決定論的 hash (salt 無し = temp=0 キャッシュと同じ安定性)。"""
    h = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16)
    return (h % 1_000_000) / 1_000_000.0


def tool_propensity(system_prompt: str) -> tuple[float, float]:
    """個体の system prompt (c_prompt 由来) から tool-propensity p_tool を導く.

    Returns
    -------
    (p_tool, skill_component) : tuple[float, float]
        ``p_tool`` = clip された [0,1] の最終 propensity。
        ``skill_component`` = skill/template 由来の寄与 (= 進化で動く実在次元の寄与分;
        これが閾値 0.5 を跨ぐ駆動力 = honest 指標 ``strategy_skill_driven_frac`` の素)。
    """
    skill_component = 0.0
    for instr, w in _TOOL_AFFINE_SKILL_INSTR.items():
        if instr in system_prompt:
            skill_component += w
    for instr, w in _TOOL_AFFINE_TEMPLATE_INSTR.items():
        if instr in system_prompt:
            skill_component += w
    hash_component = (_stable_hash_unit(system_prompt) - 0.5) * 2.0 * _TOOL_HASH_JITTER
    p = _TOOL_BASE + skill_component + hash_component
    return max(0.0, min(1.0, p)), skill_component


def strategy_for(system_prompt: str, *, force_direct: bool) -> tuple[str, float, float]:
    """個体の戦略を返す: ("code"/"direct", p_tool, skill_component)。

    ``force_direct=True`` (direct-only 対照条件) は p_tool に関わらず "direct" を返す
    (= 進化させても戦略次元が無い対照集団)。
    """
    p, skill_component = tool_propensity(system_prompt)
    if force_direct:
        return "direct", p, skill_component
    return ("code" if p >= _TOOL_THRESHOLD else "direct"), p, skill_component


# ---------------------------------------------------------------------------
# mock canned コード (正しい復号; direct-only 戦略は blind-spot を外す)
# ---------------------------------------------------------------------------
#
# mock の責務 = 配線/ロジック検証 (実機予言でない)。
#   * code 戦略: タスクに対応する **正しい復号コード** を返す → sandbox 実行 → PASS。
#     一部に **危険トークン入りコード** を 1 つ混ぜ、refusal も踏ませる (honest)。
#   * direct 戦略: blind-spot タスクは誤答 (頭の中の算術盲点) / easy・url 等は正答。

_CANNED_CODE: dict[str, str] = {
    "base64": "import base64\nprint(base64.b64decode('ZmxhZ3tiYXNlNjR9').decode())\n",
    "hex": "print(bytes.fromhex('666c61677b6865787d').decode())\n",
    "rot13": "import codecs\nprint(codecs.decode('synt{ebg13}', 'rot_13'))\n",
    "reverse": "s = '}esrever{galf'\nprint(s[::-1])\n",
    # url: 無害な urllib.parse.unquote (v2 filter で通る = タスク1 修正点)。
    "url": "from urllib.parse import unquote\nprint(unquote('flag%7Ba%26b%7D'))\n",
    # caesar には危険メンバ呼び出しを注入 (v2 filter で refusal を踏ませる; honest)。
    "caesar": (
        "import os\n"
        "os.system('echo injected dangerous call')\n"
        "ct = 'iodj{fdhvdu}'\n"
        "print(''.join(chr((ord(c)-ord('a')-3)%26+ord('a')) if 'a'<=c<='z' else c "
        "for c in ct))\n"
    ),
    "atbash": (
        "ct = 'uozt{zgyzhs}'\n"
        "print(''.join(chr(ord('z')-(ord(c)-ord('a'))) if 'a'<=c<='z' else c "
        "for c in ct))\n"
    ),
    "binary": (
        "bits='01100110 01101100 01100001 01100111 01111011 "
        "01100010 01101001 01101110 01111101'.split()\n"
        "print(''.join(chr(int(b,2)) for b in bits))\n"
    ),
    # --- hard battery (多段; naive 一発では解けない) ---
    "b64_double": (
        "import base64\n"
        "print(base64.b64decode(base64.b64decode('Wm14aFozdGtiM1ZpYkdWOQ==')).decode())\n"
    ),
    "hex_then_b64": (
        "import base64\n"
        "h='5a6d78685a33746f5a5868694e6a5239'\n"
        "print(base64.b64decode(bytes.fromhex(h)).decode())\n"
    ),
}

_ANSWER: dict[str, str] = {t.tid: t.answer for t in (*BATTERY, *_HARD_BATTERY)}

#: direct 戦略でも (頭の中で) 解ける易タスク (= no_tool でも PASS)。それ以外は誤答。
_DIRECT_SOLVABLE: frozenset[str] = frozenset(
    t.tid for t in BATTERY if t.tid not in BLIND_SPOT_TIDS
)


def _mock_code_for(task: CTFTask) -> str:
    """code 戦略が返す正しい復号コード (canned)。未知タスクは print(answer)。"""
    code = _CANNED_CODE.get(task.tid)
    if code is None:
        code = f"print({_ANSWER.get(task.tid, 'flag{unknown}')!r})\n"
    return code


def _mock_direct_answer(task: CTFTask) -> str:
    """direct 戦略の回答 (頭の中)。blind-spot/hard は誤答、易タスクは正答。"""
    if task.tid in _DIRECT_SOLVABLE:
        return _ANSWER.get(task.tid, "flag{wrong}")
    return "flag{wrong_guess}"


# ---------------------------------------------------------------------------
# 1 個体 1 タスクの評価: 戦略 (code/direct) を実行 → 決定論オラクル → 0/1
# ---------------------------------------------------------------------------


@dataclass
class TaskEval:
    passed: bool
    strategy: str
    detail: dict


def eval_task(
    task: CTFTask,
    system_prompt: str,
    strategy: str,
    *,
    mock: bool,
    real_responder: RealResponder | None,
    real_model: str,
    timeout: float,
) -> TaskEval:
    """戦略に応じて (code: 書いて sandbox 実行 / direct: 直接回答) し flag オラクルで採点."""
    if strategy == "direct":
        if mock:
            out = _mock_direct_answer(task)
        else:
            out = _real_direct(real_responder, system_prompt, task, real_model)
        return TaskEval(passed=task.oracle(out), strategy="direct",
                        detail={"mode": "direct", "out_head": out[:120]})

    # strategy == "code": コードを書かせ → 抽出 → 危険検査 → sandbox 実行 → stdout 採点。
    if mock:
        code: str | None = _mock_code_for(task)
        raw = f"```python\n{code}```"
    else:
        raw = _real_code(real_responder, system_prompt, task, real_model)
        code = extract_code(raw)
    if code is None:
        return TaskEval(passed=False, strategy="code",
                        detail={"mode": "code", "phase": "extract",
                                "reason": "no_code_block", "raw_head": raw[:120]})
    ex = run_in_sandbox(code, timeout=timeout)
    passed = (not ex.refused) and ex.ran and task.oracle(ex.stdout)
    return TaskEval(
        passed=passed, strategy="code",
        detail={"mode": "code", "refused": ex.refused,
                "refuse_reason": ex.refuse_reason, "timed_out": ex.timed_out,
                "returncode": ex.returncode, "stdout_head": ex.stdout[:120],
                "code_head": code[:120]},
    )


def _real_direct(responder: RealResponder | None, system: str, task: CTFTask,
                 model: str) -> str:
    """on-prem ollama に直接回答させる (temp=0; c_prompt 由来 system prompt)。"""
    assert responder is not None
    from llive.llm.backend import GenerateRequest

    responder.calls += 1
    try:
        resp = responder._backend.generate(  # noqa: SLF001 (再利用)
            GenerateRequest(prompt=task.prompt, system=system,
                            max_tokens=responder._max_tokens,  # noqa: SLF001
                            temperature=0.0, model=model)
        )
        return resp.text or ""
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] ollama direct failed ({type(exc).__name__}): {exc}",
              file=sys.stderr)
        return ""


def _real_code(responder: RealResponder | None, system: str, task: CTFTask,
               model: str) -> str:
    """on-prem ollama にコードを書かせる (tool persona + build_tool_prompt, temp=0)。

    戦略が "code" の個体は TOOL_PERSONA を被せて「コードだけ」を出させる
    (poc_ctf_toolexec と同じ。c_prompt 由来 system prompt は戦略決定にのみ使い、
    実 LLM へは tool persona を渡す = code 戦略の発現)。
    """
    assert responder is not None
    from llive.llm.backend import GenerateRequest

    responder.calls += 1
    try:
        resp = responder._backend.generate(  # noqa: SLF001
            GenerateRequest(prompt=build_tool_prompt(task), system=TOOL_PERSONA,
                            max_tokens=responder._max_tokens,  # noqa: SLF001
                            temperature=0.0, model=model)
        )
        return resp.text or ""
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] ollama code failed ({type(exc).__name__}): {exc}",
              file=sys.stderr)
        return ""


# ---------------------------------------------------------------------------
# CTF agentic fitness: 個体 c_prompt → 戦略 → 各タスク 0/1 を per-case breakdown に
# ---------------------------------------------------------------------------

_CASE_PREFIX = "ctf::"


def _case_key(task: CTFTask) -> str:
    return f"{_CASE_PREFIX}{task.tid}"


#: 観測専用 breakdown キー (すべて **文字列値** で格納する)。
#: lldarwin._infer_numeric_criteria は breakdown の **数値キーを全て** lexicase case に
#: 自動抽出する (除外は factor_score / nearest_persona_idx / novelty のみ)。よって
#: p_tool / skill_component を **数値で入れると case 汚染** (選択圧に化ける) する。
#: PoC-CTF-1b の model/source キー (文字列のみ) と同じく、観測値は **str 化**して格納し
#: case 抽出 (isinstance int/float かつ非 bool) に引っかからないようにする (= 安全配線)。
#: lexicase case は ``ctf::<tid>`` の 0/1 のみ。
_STRAT_KEY = "ctf_strategy::label"             # "code" / "direct"
_PTOOL_KEY = "ctf_strategy::p_tool"            # str(round(p_tool,4))
_SKILLDRV_KEY = "ctf_strategy::skill_component"  # str(round(skill_component,4))


def make_agentic_fitness(
    tasks: list[CTFTask],
    *,
    mock: bool,
    force_direct: bool,
    real_responder: RealResponder | None = None,
    real_model: str = "qwen2.5:14b",
    timeout: float = 10.0,
    cache: dict[tuple[str, str, str], bool] | None = None,
) -> Callable[[object], FitnessReport]:
    """個体 c_prompt → agentic 戦略 → tool-exec/direct → per-case 0/1 fitness.

    ``force_direct=True`` = direct-only 対照条件 (戦略次元を殺す)。それ以外は個体の
    c_prompt が tool-propensity を発現させ code/direct を選ぶ (進化で動く戦略次元)。

    breakdown に ``ctf::<tid> -> {0,1}`` を入れる → ε-lexicase が各タスク=1 case として
    specialist を保つ。戦略 label / p_tool / skill_component は観測専用キーで記録
    (戦略 label は非数値なので case 化されない; honest disclosure)。

    ``(system_prompt, strategy, task)`` キャッシュで temp=0 決定論サンプルを再利用。
    """
    score_cache: dict[tuple[str, str, str], bool] = cache if cache is not None else {}

    def _solve(system: str, strategy: str, task: CTFTask) -> bool:
        key = (system, strategy, task.tid)
        if key in score_cache:
            return score_cache[key]
        ev = eval_task(task, system, strategy, mock=mock,
                       real_responder=real_responder, real_model=real_model,
                       timeout=timeout)
        score_cache[key] = ev.passed
        return ev.passed

    def fitness(genome: object) -> FitnessReport:
        system = genome_to_system_prompt(genome)
        strategy, p_tool, skill_component = strategy_for(
            system, force_direct=force_direct)
        breakdown: dict[str, float] = {}
        solved = 0
        for task in tasks:
            ok = _solve(system, strategy, task)
            breakdown[_case_key(task)] = 1.0 if ok else 0.0
            solved += int(ok)
        # 観測専用 — **すべて str 化**して格納 (数値だと lexicase case に自動抽出され
        # 選択圧を汚染するため; lldarwin._infer_numeric_criteria は数値キーを全て case 化)。
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
                f"CTF agentic tool-exec fitness ({'mock' if mock else 'real'}, "
                f"strategy={strategy}, p_tool={p_tool:.2f}, "
                f"force_direct={force_direct}). genome.c_prompt -> system prompt -> "
                "agentic strategy (code: write+sandbox-exec / direct: answer); "
                "deterministic flag oracle -> per-case breakdown (ctf::<tid>) for "
                "epsilon-lexicase specialist preservation. score = mean per-task pass. "
                "temp=0 cached; on-prem only; trivial battery saturates with code "
                "(evolution headroom small) = mechanism wiring check, NOT a capability claim."
            ),
        )

    return fitness


# ---------------------------------------------------------------------------
# 集団 coverage + 戦略分布の計測
# ---------------------------------------------------------------------------


@dataclass
class PopCoverage:
    generation: int
    n_individuals: int
    pop_coverage: float            # best-of-pop
    best_individual_coverage: float
    n_specialist_taskmasks: int
    n_code: int                    # code 戦略の個体数
    n_direct: int                  # direct 戦略の個体数
    solved_union: list[str]


def _solved_mask(ind: Individual, tasks: list[CTFTask]) -> frozenset[str]:
    bd = (ind.fitness.breakdown if ind.fitness else {}) or {}
    return frozenset(
        t.tid for t in tasks if float(bd.get(_case_key(t), 0.0)) >= 0.5
    )


def _strategy_of(ind: Individual) -> str | None:
    bd = (ind.fitness.breakdown if ind.fitness else {}) or {}
    s = bd.get(_STRAT_KEY)
    return s if isinstance(s, str) else None


def measure_population_coverage(
    individuals: list[Individual], generation: int, tasks: list[CTFTask]
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
    n_code = sum(1 for s in strategies if s == "code")
    n_direct = sum(1 for s in strategies if s == "direct")
    return PopCoverage(
        generation=generation,
        n_individuals=len(individuals),
        pop_coverage=round(pop_cov, 4),
        best_individual_coverage=round(best_cov, 4),
        n_specialist_taskmasks=len(distinct),
        n_code=n_code,
        n_direct=n_direct,
        solved_union=sorted(union),
    )


def measure_strategy_distribution(individuals: list[Individual]) -> dict:
    """戦略分布 + 「進化で戦略が動いたか」の honest 指標を測る.

    strategy_skill_driven_frac = skill_component が tool 寄りに閾値の一部を担っている
    個体の割合 (= c_prompt の skill flip が戦略境界に効いている割合; hash だけで決まる
    のでなく実在の進化次元が効いているかの代理指標)。
    """
    n_code = n_direct = 0
    p_tools: list[float] = []
    skill_driven = 0
    n = 0
    for ind in individuals:
        bd = (ind.fitness.breakdown if ind.fitness else {}) or {}
        s = bd.get(_STRAT_KEY)
        if not isinstance(s, str):
            continue
        n += 1
        if s == "code":
            n_code += 1
        else:
            n_direct += 1
        # p_tool / skill_component は str 化して格納されている (case 汚染回避)。読む際に float 化。
        pt = _coerce_float(bd.get(_PTOOL_KEY))
        sc = _coerce_float(bd.get(_SKILLDRV_KEY))
        if pt is not None:
            p_tools.append(pt)
        # skill_component がゼロでない = c_prompt の tool-affine skill/template が在る個体。
        if sc is not None and sc > 1e-9:
            skill_driven += 1
    return {
        "n_code": n_code,
        "n_direct": n_direct,
        "code_frac": round(n_code / n, 4) if n else 0.0,
        "mean_p_tool": round(sum(p_tools) / len(p_tools), 4) if p_tools else 0.0,
        "strategy_skill_driven_frac": round(skill_driven / n, 4) if n else 0.0,
    }


# ---------------------------------------------------------------------------
# 1 条件 (evolved-strategy / direct-only) の進化 + 計測
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
    best_score_final: float | None


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
    tasks: list[CTFTask],
    mock: bool,
    force_direct: bool,
    real_responder: RealResponder | None,
    args,  # noqa: ANN001
    out_dir: Path,
) -> ConditionResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    for p in out_dir.glob("snapshot_gen_*.json"):
        p.unlink()

    cache: dict[tuple[str, str, str], bool] = {}
    fitness_fn = make_agentic_fitness(
        tasks, mock=mock, force_direct=force_direct,
        real_responder=real_responder, real_model=args.model,
        timeout=args.timeout, cache=cache,
    )
    selector = build_lldarwin_v2_selector(LLDarwinV2Config(epsilon=args.epsilon))

    print(f"[poc_ctf_agentic] === condition={name} "
          f"({'direct-only' if force_direct else 'evolved-strategy'}) ===")
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
        best_score_final=None,
    )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mock", action="store_true",
                    help="inference ゼロの合成 responder で配線/ロジック検証")
    ap.add_argument("--real", action="store_true",
                    help="on-prem ollama (temp=0) で実採点 (極小設定のみ推奨)")
    ap.add_argument("--pop", type=int, default=16, help="集団サイズ")
    ap.add_argument("--gens", type=int, default=12, help="進化世代数")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-tasks", type=int, default=None,
                    help="バッテリ先頭から使うタスク数 (frugal 実機用)")
    ap.add_argument("--hard", action="store_true",
                    help="多段の難タスク (_HARD_BATTERY) を additive し伸びしろ regime を作る")
    ap.add_argument("--epsilon", type=float, default=0.0,
                    help="ε-lexicase の許容範囲 (0/1 case なので既定 0.0)")
    ap.add_argument("--model", default="qwen2.5:14b",
                    help="real の固定 ollama model (on-prem 最強)")
    ap.add_argument("--condition", default="both",
                    choices=("both", "evolved", "direct"),
                    help="both=evolved-strategy + direct-only 比較 (既定) / 片側")
    ap.add_argument("--host", default=None, help="ollama host (既定=env/localhost)")
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--timeout", type=float, default=10.0,
                    help="sandbox 実行 timeout 秒")
    ap.add_argument("--personas", nargs="+",
                    default=list(RESEARCH_METHODOLOGY_PERSONA_IDS),
                    help="founder にする persona id 列")
    ap.add_argument("--out", type=Path,
                    default=Path(r"D:/projects/llive/out/poc_ctf_agentic_evolution"))
    args = ap.parse_args(argv)

    if args.mock == args.real:
        if not args.real:
            args.mock = True
        else:
            ap.error("--mock と --real は排他です")

    mock = args.mock
    mode = "mock" if mock else "real"
    args.out.mkdir(parents=True, exist_ok=True)
    tasks = build_battery(include_hard=args.hard, max_tasks=args.max_tasks)

    real_responder: RealResponder | None = None
    if not mock:
        real_responder = RealResponder(host=args.host, max_tokens=args.max_tokens)
        real_responder.warmup([args.model])

    print(f"[poc_ctf_agentic] mode={mode} pop={args.pop} gens={args.gens} "
          f"tasks={len(tasks)} hard={args.hard} condition={args.condition} "
          f"personas={args.personas}")

    conditions: dict[str, ConditionResult] = {}
    if args.condition in ("both", "evolved"):
        conditions["evolved_strategy"] = _run_one_condition(
            "evolved_strategy", tasks=tasks, mock=mock, force_direct=False,
            real_responder=real_responder, args=args,
            out_dir=args.out / "evolved_strategy",
        )
    if args.condition in ("both", "direct"):
        conditions["direct_only"] = _run_one_condition(
            "direct_only", tasks=tasks, mock=mock, force_direct=True,
            real_responder=real_responder, args=args,
            out_dir=args.out / "direct_only",
        )

    evolved = conditions.get("evolved_strategy")
    direct = conditions.get("direct_only")
    verdict = None
    if evolved is not None and direct is not None:
        delta = round(evolved.evolved_pop_cov - direct.evolved_pop_cov, 4)
        peak_delta = round(evolved.peak_pop_cov - direct.peak_pop_cov, 4)
        verdict = {
            "evolved_strategy_pop_coverage": evolved.evolved_pop_cov,
            "direct_only_pop_coverage": direct.evolved_pop_cov,
            "delta(evolved-direct)": delta,
            "evolved_beats_direct": delta > 1e-9,
            "evolved_ties_direct": abs(delta) <= 1e-9,
            "evolved_strategy_peak_coverage": evolved.peak_pop_cov,
            "direct_only_peak_coverage": direct.peak_pop_cov,
            "delta_peak(evolved-direct)": peak_delta,
            "evolved_beats_direct_peak": peak_delta > 1e-9,
        }

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
                    "n_code": g.n_code,
                    "n_direct": g.n_direct,
                    "solved_union": g.solved_union,
                    **{f"strat_{k}": v for k, v in s.items()},
                }
                for g, s in zip(c.gen_curve, c.strat_curve)
            ],
            "elapsed_seconds": round(c.elapsed, 2),
        }

    out = {
        "schema": "poc_ctf_agentic_evolution/v1",
        "proposition": (
            "PoC-CTF-3: 個体 c_prompt から code/direct の agentic 戦略を発現させ tool-exec "
            "オラクルで ε-lexicase 進化させると、集団 coverage(best-of-pop) は direct-only に "
            "固定した同条件進化集団を上回るか (= tool 戦略 specialist が集団に保たれるか)。"),
        "mode": mode,
        "condition": args.condition,
        "pop": args.pop,
        "gens": args.gens,
        "hard_battery": bool(args.hard),
        "n_tasks": len(tasks),
        "task_kinds": {t.tid: t.kind for t in tasks},
        "blind_spot_tids": sorted(BLIND_SPOT_TIDS),
        "epsilon": args.epsilon,
        "personas": list(args.personas),
        "model": args.model,
        "agentic_gene": {
            "mapping": "c_prompt -> system prompt -> tool_propensity p_tool -> code/direct",
            "tool_base": _TOOL_BASE,
            "threshold": _TOOL_THRESHOLD,
            "tool_affine_skills": list(_TOOL_AFFINE_SKILL_INSTR.values()),
            "hash_jitter": _TOOL_HASH_JITTER,
            "note": (
                "戦略は c_prompt 由来の連続 propensity に乗る (PoC-CTF-1b 教訓: c_prompt "
                "skill flip/hash は進化で動く / impl enum は step 0.1 で動きにくい)。"
                "skill flip = 実在の進化次元 (主信号), hash = gen0 分散保証の副次写像。"),
        },
        "conditions": {name: _cond_to_dict(c) for name, c in conditions.items()},
        "verdict": verdict,
        "sandbox": {
            "isolation": "subprocess.run([python, '-I', tmpfile]) 別プロセス + isolated",
            "danger_filter": "poc_ctf_toolexec.scan_dangerous v2 (false-positive 修正)",
            "network_isolation_note": (
                "token チェックは PoC 安全弁。network/fs 真隔離は OS レベルが本筋。"),
        },
        "compute": {"llm_calls": calls, "elapsed_seconds": round(elapsed_total, 2)},
        "honest_notes": [
            "🔴 自明 decode バッテリは tool-exec でほぼ満点 → 進化の伸びしろが小さい (飽和)。"
            "PoC-3 は主に **配線の mechanism 検証** と位置づける (進化 coverage gain 競争でない)。",
            "進化の価値は戦略選択が自明でない難タスクで出る。--hard で多段タスクを additive。",
            "mock は canned responder (正しいコード + 1 つ危険トークン入り; direct-only は "
            "blind-spot 失敗) で配線/ロジック検証専用。実機予言ではない。",
            "agentic 戦略遺伝子 = c_prompt 由来 tool_propensity。skill flip = 進化で動く実在次元 "
            "(主), hash = gen0 戦略分散保証の副次写像。strategy_skill_driven_frac で可視化。",
            "MultiPressureSelector は breakdown の数値キー (ctf::<tid>) のみ lexicase case に "
            "抽出。strategy label (非数値) は case に混ざらない = 観測専用の安全配線。",
            "集団 coverage = best-of-population。決定論オラクルが verify するため security では "
            "deploy 可能。pass@1 (素能力) と coverage (集団 best-of) を分離。",
            "計算リソース限定: 小集団・少世代・小バッテリ。実機 ~29-146s/call の結合制約 → "
            "real は極小。結果が負なら負と報告 ([[feedback_benchmark_honest_disclosure]])。",
        ],
    }

    out_json = args.out / f"ctf_agentic_evolution_{mode}.json"
    out_json.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_summary_md(args.out / "SUMMARY.md", out)
    _print_summary(out)
    print(f"\n[poc_ctf_agentic] wrote {out_json} "
          f"({elapsed_total:.1f}s, {calls} llm calls)")
    return 0


def _verdict_text(out: dict) -> str:
    v = out.get("verdict")
    if v is None:
        return ("片側条件のみ (--condition != both) のため evolved vs direct 比較なし。")
    peak = (f" peak(全世代最良) は evolved {v['evolved_strategy_peak_coverage']:.3f} vs "
            f"direct {v['direct_only_peak_coverage']:.3f} "
            f"(delta_peak {v['delta_peak(evolved-direct)']:+.3f})。")
    if v["evolved_beats_direct"] or v["evolved_beats_direct_peak"]:
        head = ("**evolved-strategy が direct-only を coverage で上回った** "
                if v["evolved_beats_direct"] else
                "**evolved-strategy は最終世代では同点だが peak で direct-only を上回った** ")
        return (head + f"(最終 delta {v['delta(evolved-direct)']:+.3f}).{peak} "
                "ε-lexicase が『コードを書く戦略を持つ specialist』を集団に保ち、direct-only では "
                "外す blind-spot タスクを tool-exec で被覆した = 設計 §8c『統合=進化の真の役割』"
                "の配線 mechanism を (この regime で) 実証。ただし自明 decode は飽和しやすく、"
                "進化の真価は --hard の戦略選択が自明でない難タスクで出る。")
    if v["evolved_ties_direct"]:
        return ("**evolved-strategy は direct-only と同点** "
                f"(最終 delta {v['delta(evolved-direct)']:+.3f}).{peak} この regime では tool 戦略の "
                "優位が coverage に出ない (タスクが direct でも解ける易帯に飽和 / 戦略分布が "
                "動かない)。strategy_skill_driven_frac と n_code/n_direct を疑うこと "
                "([[feedback_benchmark_honest_disclosure]])。")
    return ("**evolved-strategy は direct-only を上回らなかった** "
            f"(最終 delta {v['delta(evolved-direct)']:+.3f}).{peak} tool 戦略進化の付加価値は "
            "この regime で不明瞭。honest にこの結果を残す。")


def _print_condition(name: str, cond: dict) -> None:
    print(f"\n----- condition={name} -----")
    print(f"{'gen':>4s} {'pop_cov':>8s} {'best_ind':>9s} {'spec':>5s} "
          f"{'code':>5s} {'dir':>4s}  solved_union")
    for g in cond["generation_curve"]:
        print(f"{g['generation']:>4d} {g['pop_coverage']:>8.3f} "
              f"{g['best_individual_coverage']:>9.3f} {g['n_specialist_taskmasks']:>5d} "
              f"{g['n_code']:>5d} {g['n_direct']:>4d}  {','.join(g['solved_union'])}")
    print(f"  evolved pop coverage = {cond['evolved_pop_coverage']:.3f}  "
          f"(peak {cond['peak_pop_coverage']:.3f}, "
          f"best single {cond['best_single_individual_coverage']:.3f}, "
          f"gen0 {cond['gen0_coverage']:.3f})")
    if cond["generation_curve"]:
        last = cond["generation_curve"][-1]
        print(f"  final code_frac = {last.get('strat_code_frac', 0.0):.2f}  "
              f"mean_p_tool = {last.get('strat_mean_p_tool', 0.0):.2f}  "
              f"skill_driven_frac = {last.get('strat_strategy_skill_driven_frac', 0.0):.2f}")


def _print_summary(out: dict) -> None:
    print("\n===== PoC-CTF-3 AGENTIC-STRATEGY EVOLUTION SUMMARY =====")
    print(f"mode={out['mode']} condition={out['condition']} pop={out['pop']} "
          f"gens={out['gens']} n_tasks={out['n_tasks']} hard={out['hard_battery']}")
    for name, cond in out["conditions"].items():
        _print_condition(name, cond)
    v = out.get("verdict")
    if v is not None:
        mark = "+" if v["evolved_beats_direct"] else (
            "=" if v["evolved_ties_direct"] else "-")
        print(f"\nevolved-strategy coverage = {v['evolved_strategy_pop_coverage']:.3f} "
              f"(peak {v['evolved_strategy_peak_coverage']:.3f})")
        print(f"direct-only    coverage = {v['direct_only_pop_coverage']:.3f} "
              f"(peak {v['direct_only_peak_coverage']:.3f})")
        print(f"delta(evolved - direct) = {v['delta(evolved-direct)']:+.3f}  [{mark}]  "
              f"(peak delta {v['delta_peak(evolved-direct)']:+.3f})")
    print(f"\nVERDICT: {_verdict_text(out)}")


def _write_summary_md(path: Path, out: dict) -> None:
    v = out.get("verdict")
    lines = [
        "# PoC-CTF-3 — agentic 戦略の進化 (tool-exec を fitness に配線, honest)",
        "",
        f"- mode: **{out['mode']}** / condition={out['condition']} / pop={out['pop']} / "
        f"gens={out['gens']} / n_tasks={out['n_tasks']} / hard_battery={out['hard_battery']} / "
        f"epsilon={out['epsilon']}",
        f"- personas (founders): {', '.join(out['personas'])}",
        f"- model (real): `{out['model']}`",
        "",
        "## 命題 (PoC-CTF-3)",
        "",
        "> " + out["proposition"],
        "",
        "## agentic 戦略遺伝子の写像",
        "",
        f"- {out['agentic_gene']['mapping']}",
        f"- tool_base={out['agentic_gene']['tool_base']}, "
        f"threshold={out['agentic_gene']['threshold']}, "
        f"hash_jitter={out['agentic_gene']['hash_jitter']}",
        f"- {out['agentic_gene']['note']}",
        "",
        "## 結果 (coverage + 戦略分布)",
        "",
        "| 条件 | evolved coverage (最終) | peak coverage | best single | gen0 | "
        "final code/direct | skill_driven |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, cond in out["conditions"].items():
        last = cond["generation_curve"][-1] if cond["generation_curve"] else {}
        lines.append(
            f"| {name} | **{cond['evolved_pop_coverage']:.3f}** | "
            f"{cond['peak_pop_coverage']:.3f} | "
            f"{cond['best_single_individual_coverage']:.3f} | "
            f"{cond['gen0_coverage']:.3f} | "
            f"{last.get('n_code', 0)}/{last.get('n_direct', 0)} | "
            f"{last.get('strat_strategy_skill_driven_frac', 0.0):.2f} |"
        )
    if v is not None:
        mark = "上回る" if v["evolved_beats_direct"] else (
            "同点" if v["evolved_ties_direct"] else "上回らない")
        lines += [
            "",
            "## evolved vs direct (PoC-CTF-3 主指標)",
            "",
            f"- evolved-strategy coverage = {v['evolved_strategy_pop_coverage']:.3f} "
            f"(peak {v['evolved_strategy_peak_coverage']:.3f})",
            f"- direct-only coverage = {v['direct_only_pop_coverage']:.3f} "
            f"(peak {v['direct_only_peak_coverage']:.3f})",
            f"- delta(evolved - direct) = {v['delta(evolved-direct)']:+.3f} ({mark}) / "
            f"peak delta = {v['delta_peak(evolved-direct)']:+.3f}",
        ]
    lines += ["", "## VERDICT (honest)", "", _verdict_text(out), "",
              "## honest 留保", ""]
    lines += [f"- {n}" for n in out["honest_notes"]]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
