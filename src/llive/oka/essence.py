# SPDX-License-Identifier: Apache-2.0
"""OKA-01 / OKA-02 — Problem Framing Layer & Core Essence Extractor.

岡潔の「数学は情緒である」を実装に置き換えるための最初の層。
解答生成に入る前に、問題から:

* **何が不思議か** (mystery) — surface-level の「驚き」
* **保存量は何か** (invariants) — 変換しても変わらないもの
* **対称性はどこにあるか** (symmetries) — 入れ替え可能な構造
* **核心メモ** (essence) — 上 3 つを統合した 1〜3 文の本質記述

を deterministic に抽出する。実装は 4 つの :class:`EssenceLens` を直列に
走らせ、結果を :class:`CoreEssence` に集約する。LLM での豊かな抽出は
後段で :class:`EssenceLens` の Strategy 差し替えで対応可能 (MathVerifier
/ RoleBasedMultiTrack と同じ Strategy パターン)。

トレーサビリティ:

* ``extractor.bind_ledger(ledger)`` で BriefLedger に attach → 各抽出で
  ``oka_essence_extracted`` event が記録される
* COG-03 trace_graph の evidence_chain に ``kind="oka_essence"`` として
  ledger.py 側で統合される
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from llive.brief.ledger import BriefLedger


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CoreEssence:
    """Output of a single :class:`CoreEssenceExtractor.extract` call.

    Designed to be JSON-serialisable trivially (only str / tuple).
    """

    problem_text: str
    mystery: str          # 何が不思議か
    invariants: tuple[str, ...]   # 保存量候補
    symmetries: tuple[str, ...]   # 対称性候補
    essence_summary: str  # 核心メモ (1〜3 文)
    source_id: str = ""

    def to_payload(self) -> dict[str, object]:
        return {
            "problem_text": self.problem_text,
            "mystery": self.mystery,
            "invariants": list(self.invariants),
            "symmetries": list(self.symmetries),
            "essence_summary": self.essence_summary,
            "source_id": self.source_id,
        }


class EssenceLens(Protocol):
    """1 つの観点で問題テキストを読む lens.

    deterministic な heuristic で初期実装するが、LLM 駆動 lens に差し替えれば
    そのまま :class:`CoreEssenceExtractor` に取り込める。
    """

    name: str

    def observe(self, problem_text: str) -> str | tuple[str, ...]:  # pragma: no cover - Protocol
        ...


# ---------------------------------------------------------------------------
# Deterministic heuristic lenses
# ---------------------------------------------------------------------------


_MYSTERY_TRIGGERS = (
    "なぜ", "why", "どうして", "不思議", "意外", "なんで", "paradox",
    "矛盾", "驚", "surprising",
)


_INVARIANT_TRIGGERS = (
    "保存", "invariant", "conserve", "preserve", "総和", "総量",
    "constant", "一定", "不変",
)


_SYMMETRY_TRIGGERS = (
    "対称", "symmetry", "rotation", "回転", "swap", "入れ替え",
    "可換", "permutation", "鏡", "mirror",
)


_TOKEN_RE = re.compile(r"[A-Za-z0-9_ぁ-ゟ゠-ヿ一-鿿]+", re.UNICODE)


def _find_trigger_sentence(text: str, triggers: tuple[str, ...]) -> str:
    """Return the first sentence containing any trigger, or empty string."""
    sentences = re.split(r"[。．.!?\n]", text)
    for sent in sentences:
        low = sent.lower()
        for t in triggers:
            if t.lower() in low:
                return sent.strip()
    return ""


def _list_candidates(text: str, triggers: tuple[str, ...], limit: int = 3) -> tuple[str, ...]:
    """For each matched trigger, capture a short context window as a candidate."""
    out: list[str] = []
    low = text.lower()
    for trigger in triggers:
        idx = low.find(trigger.lower())
        if idx < 0:
            continue
        start = max(0, idx - 12)
        end = min(len(text), idx + len(trigger) + 24)
        snippet = text[start:end].strip()
        if snippet and snippet not in out:
            out.append(snippet)
        if len(out) >= limit:
            break
    return tuple(out)


@dataclass(frozen=True)
class MysteryLens:
    """「何が不思議か」を抽出。"""

    name: str = "mystery"

    def observe(self, problem_text: str) -> str:
        sent = _find_trigger_sentence(problem_text, _MYSTERY_TRIGGERS)
        if sent:
            return sent
        # Fallback: take first non-trivial sentence as the surface puzzle.
        sentences = [s.strip() for s in re.split(r"[。．.!?\n]", problem_text) if s.strip()]
        return sentences[0] if sentences else ""


@dataclass(frozen=True)
class InvariantLens:
    """保存量候補を列挙。"""

    name: str = "invariants"

    def observe(self, problem_text: str) -> tuple[str, ...]:
        return _list_candidates(problem_text, _INVARIANT_TRIGGERS)


@dataclass(frozen=True)
class SymmetryLens:
    """対称性候補を列挙。"""

    name: str = "symmetries"

    def observe(self, problem_text: str) -> tuple[str, ...]:
        return _list_candidates(problem_text, _SYMMETRY_TRIGGERS)


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------


def _default_lenses() -> dict[str, EssenceLens]:
    return {
        "mystery": MysteryLens(),
        "invariants": InvariantLens(),
        "symmetries": SymmetryLens(),
    }


class CoreEssenceExtractor:
    """OKA-02 — 問題文から :class:`CoreEssence` を抽出。

    deterministic mode では Strategy lens の集合を直列に呼ぶだけ。LLM mode に
    差し替えるときは lens を 1 つの async sub-Brief lens にして同じ Protocol で
    返せばよい。
    """

    def __init__(
        self,
        *,
        lenses: dict[str, EssenceLens] | None = None,
        source_id: str = "",
        ledger: "BriefLedger | None" = None,
    ) -> None:
        self._lenses: dict[str, EssenceLens] = lenses or _default_lenses()
        self._source_id = source_id
        self._ledger = ledger

    def bind_ledger(self, ledger: "BriefLedger | None") -> None:
        """Re-target the auto-record sink (mirrors MathVerifier.bind_ledger)."""
        self._ledger = ledger

    def extract(self, problem_text: str, *, source_id: str | None = None) -> CoreEssence:
        sid = source_id if source_id is not None else self._source_id
        mystery = str(self._lenses["mystery"].observe(problem_text) or "")
        invariants = tuple(self._lenses["invariants"].observe(problem_text) or ())
        symmetries = tuple(self._lenses["symmetries"].observe(problem_text) or ())
        essence = self._compose_essence(problem_text, mystery, invariants, symmetries)
        result = CoreEssence(
            problem_text=problem_text,
            mystery=mystery,
            invariants=invariants,
            symmetries=symmetries,
            essence_summary=essence,
            source_id=sid,
        )
        if self._ledger is not None:
            self._ledger.append("oka_essence_extracted", result.to_payload())
        return result

    @staticmethod
    def _compose_essence(
        problem_text: str,
        mystery: str,
        invariants: tuple[str, ...],
        symmetries: tuple[str, ...],
    ) -> str:
        """1〜3 文に詰める — deterministic, audit-safe."""
        parts: list[str] = []
        if mystery:
            parts.append(f"核心の問い: {mystery}.")
        if invariants:
            parts.append(f"保存量候補: {invariants[0]}.")
        if symmetries:
            parts.append(f"対称性候補: {symmetries[0]}.")
        if not parts:
            # fallback essence: first 80 chars of the input
            head = problem_text.strip().replace("\n", " ")[:80]
            parts.append(f"核心未抽出 (heuristic fallback): {head}.")
        return " ".join(parts)
