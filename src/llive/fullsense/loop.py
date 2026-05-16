# SPDX-License-Identifier: Apache-2.0
"""FullSense Loop — 6 ステージ自律思考パイプライン (Sandbox-only MVP).

設計は ``src/llive/fullsense/__init__.py`` のフロー図を参照。MVP では各ステージを
**stdlib + 既存 llive モジュール**で実装し、外部依存ゼロで完結させる。

Sandbox = 外向け副作用一切なし。**OUTPUT BUS は :class:`SandboxOutputBus`
固定**で、PROPOSE / INTERVENE 決定も log にしか落ちない。
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from llive.fullsense.sandbox import SandboxOutputBus, SandboxRecord
from llive.fullsense.scorer import EgoAltruismScorer
from llive.fullsense.types import (
    ActionDecision,
    ActionPlan,
    Stimulus,
    Thought,
)

if TYPE_CHECKING:
    from llive.llm import LLMBackend


class BackendConfigurationError(ValueError):
    """Raised when a cloud LLM backend is configured on FullSenseLoop without
    the explicit ``LLIVE_ALLOW_CLOUD_BACKEND=1`` override.

    Default policy keeps llive measurements pure: the loop only consults
    on-prem (ollama) backends, so the llive contribution can be cleanly
    separated from cloud-model contribution in benchmarks. Override only
    when you deliberately want to wrap a cloud model inside the FullSense
    pipeline."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+", re.UNICODE)


def _tokenise(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "")}


# Very small TRIZ trigger keywords → principle id mapping for MVP
_TRIZ_TRIGGERS: dict[str, int] = {
    # 矛盾系
    "vs": 1,
    "versus": 1,
    "trade-off": 1,
    "tradeoff": 1,
    "contradiction": 1,
    # 動きで魅せる
    "static": 15,
    "dynamic": 15,
    "動かない": 15,
    # 仲介
    "via": 24,
    "mediator": 24,
    "ground": 24,
    "grounding": 24,
    # 退屈・idle
    "idle": 19,
    "periodic": 19,
    "繰り返": 19,
    # parameter 変更
    "parameter": 35,
    "knob": 35,
}


def _detect_triz_principles(text: str) -> list[int]:
    """Crude lexical TRIZ-trigger detection. Phase 2 で本格 TRIZ engine と統合。"""
    low = (text or "").lower()
    hits: list[int] = []
    for kw, principle in _TRIZ_TRIGGERS.items():
        if kw in low and principle not in hits:
            hits.append(principle)
    return hits


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class FullSenseResult:
    """One end-to-end loop traversal result."""

    stim: Stimulus
    plan: ActionPlan
    stages: dict[str, object] = field(default_factory=dict)
    """Per-stage diagnostic information (salience score, curiosity score, etc.)."""


# ---------------------------------------------------------------------------
# Loop
# ---------------------------------------------------------------------------


class FullSenseLoop:
    """6-stage autonomous thinking loop.

    MVP の責任分界:

    1. :meth:`_salience_gate` — Stimulus.surprise を見て進める / 落とす
    2. :meth:`_curiosity_drive` — 既知語との重なりが少ないほど高得点
    3. :meth:`_inner_monologue` — 簡易テキスト合成 + TRIZ keyword detection
    4. :meth:`_score_thought` — EgoAltruismScorer
    5. :meth:`_decide_action` — 4 段階の ActionDecision を選ぶ
    6. ``SandboxOutputBus.emit`` — log のみ

    ``known_corpus`` に既知トークン集合を渡すと curiosity 計算に使える。
    実運用では ``SemanticMemory`` の embedding 距離に置き換える前提。
    """

    def __init__(
        self,
        *,
        salience_threshold: float = 0.4,
        curiosity_threshold: float = 0.6,
        scorer: EgoAltruismScorer | None = None,
        output_bus: SandboxOutputBus | None = None,
        known_corpus: set[str] | None = None,
        sandbox: bool = True,
        llm_backend: LLMBackend | None = None,
        debug: bool = False,
    ) -> None:
        if not sandbox:
            raise ValueError(
                "FullSenseLoop MVP は sandbox=True 限定です。"
                " 外向け副作用ありの本番モードは将来 ProductionOutputBus + "
                "@govern(policy) で実装します。"
            )
        self.salience_threshold = float(salience_threshold)
        self.curiosity_threshold = float(curiosity_threshold)
        self.scorer = scorer if scorer is not None else EgoAltruismScorer()
        # NB: explicit None check — SandboxOutputBus.__len__ makes empty buses
        # falsy, so ``output_bus or X`` would silently replace a freshly passed
        # bus with a brand-new one (and lose ``log_path``).
        self.output_bus = output_bus if output_bus is not None else SandboxOutputBus()
        self.known_corpus = set(known_corpus or set())
        self.sandbox = True
        # Opt-in LLM backend for _inner_monologue. None (default) keeps the
        # rule-based template path active. Explicit injection always wins over
        # env-driven resolution (see _resolve_backend_for_loop).
        self._llm_backend: LLMBackend | None = llm_backend
        # debug=True attaches per-stage trace info to stages dict (LLM prompt,
        # raw response, wall time, backend name). Release-mode default (False)
        # has zero overhead — the trace dict is never built.
        self._debug = bool(debug)

    # -- public ------------------------------------------------------------

    def process(self, stim: Stimulus) -> FullSenseResult:
        """Run one stimulus through all 6 stages."""
        stages: dict[str, object] = {}

        # ① Salience Gate
        salience = self._salience_gate(stim)
        stages["salience"] = salience
        if not salience["pass"]:
            plan = ActionPlan(
                decision=ActionDecision.SILENT,
                rationale="below salience threshold",
            )
            return self._finalise(stim, plan, stages)

        # ② Curiosity Drive
        curiosity = self._curiosity_drive(stim)
        stages["curiosity"] = curiosity

        # ③ Inner Monologue
        thought, thought_debug = self._inner_monologue(stim, curiosity_score=curiosity["score"])
        thought_stage: dict[str, Any] = {
            "text": thought.text,
            "triz_principles": thought.triz_principles,
            "confidence": thought.confidence,
        }
        if thought_debug is not None:
            thought_stage["debug"] = thought_debug
        stages["thought"] = thought_stage

        # ④ Ego / Altruism Scorer
        ego, alt = self._score_thought(thought)
        stages["ego_score"] = ego
        stages["altruism_score"] = alt

        # ⑤ Action Plan
        plan = self._decide_action(thought, ego, alt, curiosity_score=curiosity["score"])
        return self._finalise(stim, plan, stages)

    # -- stages ------------------------------------------------------------

    def _salience_gate(self, stim: Stimulus) -> dict[str, object]:
        # MVP: stimulus が自身の surprise を持つならそれを使う。なければ簡易長さベース。
        if stim.surprise is None:
            tokens = _tokenise(stim.content)
            est = min(1.0, len(tokens) / 30.0)  # 30 tokens 以上で max
        else:
            est = float(stim.surprise)
        passed = est >= self.salience_threshold
        return {"score": est, "threshold": self.salience_threshold, "pass": passed}

    def _curiosity_drive(self, stim: Stimulus) -> dict[str, object]:
        """既知 corpus と stimulus の token overlap が低いほど高 curiosity."""
        toks = _tokenise(stim.content)
        if not toks:
            return {"score": 0.0, "novelty": 0.0, "known_overlap": 0.0}
        overlap = len(toks & self.known_corpus) / len(toks)
        novelty = 1.0 - overlap
        return {
            "score": novelty,
            "novelty": novelty,
            "known_overlap": overlap,
            "high_curiosity": novelty >= self.curiosity_threshold,
        }

    def _inner_monologue(self, stim: Stimulus, *, curiosity_score: float) -> Thought:
        triz = _detect_triz_principles(stim.content)
        confidence = min(1.0, 0.4 + 0.4 * curiosity_score)

        # Phase 2: try opt-in LLM backend first. Falls through to the MVP
        # template when nothing is configured or the backend errors out.
        backend_text = self._try_llm_backend(stim, curiosity_score, triz)
        if backend_text is not None:
            return Thought(
                text=backend_text,
                triz_principles=triz,
                references=[],
                confidence=confidence,
            )

        # MVP template (default, rule-based, deterministic, no network).
        base = f"Observation about {stim.source!r}: {stim.content.strip()[:120]}"
        triz_note = f" [TRIZ principles: {','.join(str(p) for p in triz)}]" if triz else ""
        curiosity_note = (
            " — novel territory, worth exploring."
            if curiosity_score >= self.curiosity_threshold
            else " — fits known patterns."
        )
        return Thought(
            text=base + triz_note + curiosity_note,
            triz_principles=triz,
            references=[],
            confidence=confidence,
        )

    def _try_llm_backend(
        self,
        stim: Stimulus,
        curiosity_score: float,
        triz: list[int],
    ) -> str | None:
        """Call the configured LLM backend, or return ``None`` to fall back to the template."""
        backend = self._resolve_backend_for_loop()
        if backend is None:
            return None
        try:
            from llive.llm import GenerateRequest

            response = backend.generate(
                GenerateRequest(
                    prompt=self._build_llm_prompt(stim, curiosity_score, triz),
                    max_tokens=512,
                    temperature=0.3,
                )
            )
        except BackendConfigurationError:
            raise
        except Exception:
            return None
        if getattr(response, "finish_reason", "stop") == "error":
            return None
        text = (response.text or "").strip()
        return text or None

    def _resolve_backend_for_loop(self) -> LLMBackend | None:
        """On-prem-first backend resolver — see ``feedback_llive_measurement_purity``.

        Resolution order:

        1. Explicit ``llm_backend=`` kwarg passed to ``__init__`` (test injection,
           always honoured regardless of vendor).
        2. ``$LLIVE_LLM_BACKEND`` env. ``mock`` or unset → template fallback.
           ``ollama*`` is always allowed (on-prem). Other values
           (``anthropic`` / ``openai`` / ...) require ``LLIVE_ALLOW_CLOUD_BACKEND=1``
           to opt in; otherwise raise ``BackendConfigurationError``.
        """
        if self._llm_backend is not None:
            return self._llm_backend
        name = os.environ.get("LLIVE_LLM_BACKEND", "").strip().lower()
        if not name or name == "mock":
            return None
        if name == "ollama" or name.startswith("ollama:"):
            from llive.llm import OllamaBackend

            if ":" in name:
                _, model = name.split(":", 1)
                return OllamaBackend(model=model)
            return OllamaBackend()
        if os.environ.get("LLIVE_ALLOW_CLOUD_BACKEND") == "1":
            from llive.llm import resolve_backend

            try:
                return resolve_backend(name)
            except Exception:
                return None
        raise BackendConfigurationError(
            f"refusing cloud LLM backend {name!r} inside FullSenseLoop; "
            f"set LLIVE_ALLOW_CLOUD_BACKEND=1 to override (rare), or "
            f"benchmark the cloud API directly without llive (see "
            f"docs/proposals/brief_api_design.md and "
            f"feedback_llive_measurement_purity for rationale)"
        )

    @staticmethod
    def _build_llm_prompt(
        stim: Stimulus,
        curiosity_score: float,
        triz: list[int],
    ) -> str:
        triz_str = ", ".join(str(p) for p in triz) if triz else "none"
        novelty_label = "novel" if curiosity_score >= 0.6 else "familiar"
        return (
            f"You are llive's inner monologue stage in a 6-stage cognitive "
            f"loop (salience -> curiosity -> thought -> ego/altruism -> "
            f"plan -> output).\n"
            f"Stimulus source: {stim.source}\n"
            f"Curiosity: {novelty_label} (score {curiosity_score:.2f})\n"
            f"TRIZ principles already detected: {triz_str}\n"
            f"---\n"
            f"Stimulus content:\n{stim.content}\n"
            f"---\n"
            f"Write a concise (1-3 sentences) first-person internal "
            f"observation about this stimulus. Note any patterns, "
            f"contradictions, or connections to known concepts. Do not "
            f"propose actions yet -- this is internal monologue only."
        )

    def _score_thought(self, thought: Thought) -> tuple[float, float]:
        return self.scorer.score(thought)

    def _decide_action(
        self,
        thought: Thought,
        ego: float,
        alt: float,
        *,
        curiosity_score: float,
    ) -> ActionPlan:
        """Heuristic decision tree.

        - alt - ego >= 0.3 and confidence high → PROPOSE
        - curiosity_score high and TRIZ hit → NOTE
        - everything else → SILENT
        Sandbox 限定なので PROPOSE / INTERVENE も外向け副作用なし。
        """
        decision: ActionDecision
        rationale: str
        if (alt - ego) >= 0.3 and thought.confidence >= 0.5:
            decision = ActionDecision.PROPOSE
            rationale = "altruism strongly dominates and confidence is sufficient"
        elif curiosity_score >= self.curiosity_threshold and thought.triz_principles:
            decision = ActionDecision.NOTE
            rationale = "novel + TRIZ principles detected; worth recording"
        elif curiosity_score >= self.curiosity_threshold:
            decision = ActionDecision.NOTE
            rationale = "novel territory; record for later consolidation"
        else:
            decision = ActionDecision.SILENT
            rationale = "no actionable novelty / altruism signal"
        return ActionPlan(
            decision=decision,
            rationale=rationale,
            ego_score=ego,
            altruism_score=alt,
            thought=thought,
        )

    # -- finalisation ------------------------------------------------------

    def _finalise(
        self,
        stim: Stimulus,
        plan: ActionPlan,
        stages: dict[str, object],
    ) -> FullSenseResult:
        self.output_bus.emit(SandboxRecord(stim=stim, plan=plan, stages=stages))
        return FullSenseResult(stim=stim, plan=plan, stages=stages)
