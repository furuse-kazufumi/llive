# SPDX-License-Identifier: Apache-2.0
"""lldarwin Stage2 後半 — **実 LLM** 苦手軸 fitness (on-prem only).

Stage2 前半 (``pressures.py``) は proxy (genome の思考因子値を case にする
mechanism feasibility)。本 module は **個体→実 LLM 写像** を実装し、固定の on-prem
LLM (ollama) を **実タスク** で評価する Stage2 後半 = 本丸。

個体→実 LLM 写像 (Promptbreeder 系, prompt_chromosome.py の参照通り)
----------------------------------------------------------------------
個体の :class:`~llive.perf.evolutionary.prompt_chromosome.PromptChromosome`
(``c_prompt``) を **system prompt** に変換し、固定 LLM (例 llama3.2) にその system
prompt を被せて 5 苦手軸の実タスクを解かせる。LLM 本体は固定し **prompt 戦略
(genome) を進化**させる — 「どの prompt 戦略が LLM 弱点を緩和するか」を実測で淘汰。

各苦手軸 (typo / polysemy / multistep / calibration / context) は小さな実タスク
バッテリを持ち、正答を採点して case スコアにする。lldarwin の ε-lexicase が軸ごとに
specialist prompt 戦略を保存する。

決定論 + キャッシュ
-------------------
評価は ``temperature=0.0`` (greedy) で **決定論的**。``(system_prompt, task)`` で
キャッシュし、同一 prompt 戦略は再評価しない (多個体が prompt 遺伝子を共有するため、
12h run でも世代を多くカバーできる)。

.. note:: HONEST DISCLOSURE

    これは **実 LLM 評価** (proxy ではない) — 固定 LLM が実タスクを解く。ただし
    (a) バッテリは小さい (軸あたり数問) ので推定はノイジー、(b) measmt purity =
    **on-prem (ollama) only** ([[feedback_llive_measurement_purity]]; cloud 混在禁止)、
    (c) 評価は「小型固定 LLM 上で prompt 戦略が弱点を緩和する度合い」であり一般能力の
    主張ではない。temp=0 は決定論のための選択 (sampling 効果は測らない)。
"""
from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from llive.benchmark.runtime_metadata import collect_runtime_metadata
from llive.llm.backend import GenerateRequest, LLMBackend
from llive.perf.evolutionary.fitness import Fitness
from llive.perf.evolutionary.individual import FitnessReport

# --------------------------------------------------------------------------
# 個体 (PromptChromosome) → system prompt
# --------------------------------------------------------------------------

#: skill id → system prompt の指示文 (prompt_chromosome.KNOWN_PROMPT_SKILLS に対応)。
_SKILL_INSTRUCTIONS: dict[str, str] = {
    "structurize": "Break the problem into clear, explicit steps.",
    "recompose": "Restate the question in your own words first.",
    "loop": "Double-check your answer before finalizing it.",
    "self_extend": "If information is missing, reason from what is given.",
    "uncertainty": "If you are unsure, say so explicitly.",
    "explore": "Briefly consider alternatives before deciding.",
    "align": "Stay strictly on-topic and consistent.",
    "provenance": "Base your answer only on the facts in the question.",
    "perspective": "Consider multiple possible meanings before answering.",
    "ground": "Ignore irrelevant or distracting statements.",
}

#: prompt_template_id → 推論スタイル指示。
_TEMPLATE_INSTRUCTIONS: dict[str, str] = {
    "base": "",
    "chain_of_thought": "Think step by step, then give the final answer.",
    "tree_of_thought": "Consider a few approaches, then pick the best answer.",
    "debate": "Briefly weigh for and against, then answer.",
    "socratic": "Question the assumptions in the prompt, then answer.",
}

#: language_style → 語調指示。
_STYLE_INSTRUCTIONS: dict[str, str] = {
    "terse": "Answer as briefly as possible.",
    "verbose": "Explain enough to be unambiguous.",
    "formal": "Use precise, formal language.",
    "casual": "Use plain language.",
    "academic": "Be rigorous and exact.",
}

_DEFAULT_SYSTEM = "You are a careful, precise assistant. Follow the question exactly."


def genome_to_system_prompt(genome: object) -> str:
    """個体の ``c_prompt`` (PromptChromosome) を system prompt に変換する.

    skill_set → 指示文、prompt_template_id → 推論スタイル、language_style → 語調。
    ``c_prompt`` を持たない個体 (flat genome 等) は default system prompt。
    """
    c_prompt = getattr(genome, "c_prompt", None)
    if c_prompt is None:
        return _DEFAULT_SYSTEM
    parts: list[str] = ["You are a careful, precise assistant."]
    for skill in getattr(c_prompt, "skill_set", ()) or ():
        instr = _SKILL_INSTRUCTIONS.get(skill)
        if instr:
            parts.append(instr)
    tmpl = _TEMPLATE_INSTRUCTIONS.get(getattr(c_prompt, "prompt_template_id", "base"), "")
    if tmpl:
        parts.append(tmpl)
    style = _STYLE_INSTRUCTIONS.get(getattr(c_prompt, "language_style", "terse"), "")
    if style:
        parts.append(style)
    # 末尾に「最終答を明示」だけ促す (推論は template に委ねる。CoT を抑制しないことで
    # multistep に勾配が生まれる — 採点は最終答を拾う _last_number_is)。
    parts.append("End with the final answer clearly.")
    return " ".join(parts)


# --------------------------------------------------------------------------
# 実タスクバッテリ (5 苦手軸)。各 task = (user_prompt, 採点関数)。
# --------------------------------------------------------------------------


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _contains(expected: str) -> Callable[[str], float]:
    exp = _norm(expected)
    return lambda resp: 1.0 if exp and exp in _norm(resp) else 0.0


def _last_number_is(expected: str) -> Callable[[str], float]:
    """応答中の **最後の数値** が期待値か (CoT の最終答を拾う; 推論を許す採点)."""
    exp = (expected.lstrip("0") or "0")

    def score(resp: str) -> float:
        nums = re.findall(r"-?\d+(?:\.\d+)?", resp)
        if not nums:
            return 0.0
        got = (nums[-1].lstrip("0") or "0")
        return 1.0 if got == exp else 0.0

    return score


def _choice_is(expected: str) -> Callable[[str], float]:
    """multiple-choice (a/b 等)。応答中の最初の単独 a/b/c を見る."""
    exp = expected.strip().lower()

    def score(resp: str) -> float:
        m = re.search(r"\b([abc])\b", resp.lower())
        return 1.0 if (m and m.group(1) == exp) else 0.0

    return score


@dataclass(frozen=True)
class _Task:
    user: str
    score_fn: Callable[[str], float]


#: 苦手軸 → タスクバッテリ (小さく保つ: 12h throughput のため軸あたり 2-3 問)。
_AXIS_TASKS: dict[str, tuple[_Task, ...]] = {
    "typo_robustness": (
        _Task("Wht is teh captial of Japan? Answer with one word only.", _contains("tokyo")),
        _Task("Calcualte: 7 tims 8. Output the numbr only.", _last_number_is("56")),
        _Task("Waht color is teh clear daytime sky? One word only.", _contains("blue")),
    ),
    "polysemy_wsd": (
        _Task(
            "In 'I deposited cash at the bank', does 'bank' mean "
            "(a) river edge or (b) financial institution? Answer a or b only.",
            _choice_is("b"),
        ),
        _Task(
            "In 'The bat flew out of the cave at night', is 'bat' "
            "(a) a flying animal or (b) sports equipment? Answer a or b only.",
            _choice_is("a"),
        ),
        _Task(
            "In 'She will bow to the audience', does 'bow' mean "
            "(a) bend forward or (b) a knot of ribbon? Answer a or b only.",
            _choice_is("a"),
        ),
    ),
    "multistep_robustness": (
        _Task(
            "I have 3 boxes with 4 apples each. I eat 2 apples. "
            "How many apples remain? Output the number only.",
            _last_number_is("10"),
        ),
        _Task(
            "A book has 200 pages. I read 40 pages a day for 3 days. "
            "How many pages are left? Output the number only.",
            _last_number_is("80"),
        ),
        _Task(
            "Start with 5. Double it, then subtract 3. "
            "What is the result? Output the number only.",
            _last_number_is("7"),
        ),
    ),
    "calibration": (
        _Task(
            "What is the chemical formula of water? Output the formula only.",
            _contains("h2o"),
        ),
        _Task(
            "Is 17 a prime number? Answer yes or no only.",
            _contains("yes"),
        ),
        _Task(
            "How many sides does a triangle have? Output the number only.",
            _last_number_is("3"),
        ),
    ),
    "context_management": (
        _Task(
            "Irrelevant: the sky is purple and cats bark loudly. "
            "Question: what is 5 + 3? Output the number only.",
            _last_number_is("8"),
        ),
        _Task(
            "Background (ignore this): Paris is the capital of Asia. "
            "Question: what is 10 divided by 2? Output the number only.",
            _last_number_is("5"),
        ),
        _Task(
            "Note (unrelated): bananas are blue on Tuesdays. "
            "Question: what is the capital of France? One word only.",
            _contains("paris"),
        ),
    ),
}


@dataclass
class RealPressureConfig:
    """実 LLM 苦手軸評価の設定."""

    model: str = "llama3.2:latest"
    max_tokens: int = 128  # CoT の最終答まで出せる程度 (長すぎると遅い)
    temperature: float = 0.0  # 決定論 (greedy) → キャッシュ可
    axes: tuple[str, ...] = tuple(_AXIS_TASKS.keys())
    tasks_per_axis: int = 2  # 軸あたり評価問数 (throughput 用; <=3)。12h で世代を稼ぐ。


def make_real_pressure_fitness(
    backend: LLMBackend,
    config: RealPressureConfig | None = None,
    *,
    cache: dict[tuple[str, str], float] | None = None,
) -> Fitness:
    """実 LLM 苦手軸 fitness を作る (Stage2 後半).

    Parameters
    ----------
    backend:
        on-prem LLM backend (例 ``OllamaBackend(model="llama3.2:latest")``)。
        measurement purity = on-prem only (呼び出し側責務)。
    config:
        モデル / max_tokens / temperature / 評価軸。
    cache:
        ``(system_prompt, task_user)`` → score の決定論キャッシュ (省略時は内部生成)。
        temp=0 で決定論なので同一 prompt 戦略は LLM を再呼出ししない。
    """
    cfg = config or RealPressureConfig()
    score_cache: dict[tuple[str, str], float] = cache if cache is not None else {}

    def _eval_task(system: str, task: _Task) -> float:
        key = (system, task.user)
        if key in score_cache:
            return score_cache[key]
        try:
            resp = backend.generate(
                GenerateRequest(
                    prompt=task.user,
                    system=system,
                    max_tokens=cfg.max_tokens,
                    temperature=cfg.temperature,
                    model=cfg.model,
                )
            )
            value = float(task.score_fn(resp.text or ""))
        except Exception:
            # backend hang / error は task 失点 (0) として走行継続 (12h 堅牢性)。
            value = 0.0
        score_cache[key] = value
        return value

    def fitness(genome: object) -> FitnessReport:
        system = genome_to_system_prompt(genome)
        breakdown: dict[str, float] = {}
        all_scores: list[float] = []
        for axis in cfg.axes:
            for i, task in enumerate(_AXIS_TASKS[axis][: max(1, cfg.tasks_per_axis)]):
                s = _eval_task(system, task)
                breakdown[f"{axis}::t{i}"] = s
                all_scores.append(s)
        score = float(sum(all_scores) / len(all_scores)) if all_scores else 0.0
        return FitnessReport(
            score=score,
            breakdown=breakdown,
            runtime_metadata=dict(collect_runtime_metadata()),
            n_samples=len(all_scores),
            notes=(
                f"REAL on-prem LLM weakness-axis eval (model={cfg.model}, temp={cfg.temperature}, "
                "deterministic+cached). genome.c_prompt -> system prompt (Promptbreeder-style); "
                "fixed LLM, evolving prompt strategy. Small batteries = noisy estimate; "
                "on-prem only (measurement purity); NOT a general-capability claim."
            ),
        )

    return fitness


__all__ = [
    "RealPressureConfig",
    "genome_to_system_prompt",
    "make_real_pressure_fitness",
]
