# SPDX-License-Identifier: Apache-2.0
"""Ego / Altruism scorer — 利己 / 利他のバランス重み付け.

MVP では単純なキーワードベースのスコアラー。Phase 2 で LLM judge / learned
linear model に置き換える前提。
"""

from __future__ import annotations

from llive.fullsense.types import Thought

# Lower-cased substrings that hint at ego (self-preservation, self-interest)
_EGO_HINTS = (
    "my own", "i should", "i want", "我自己", "自分の", "自身",
    "preserve", "保护自己", "守るため",
    "credit", "credit me", "私の名前",
)

# Substrings that hint at altruism (other-helping, collective benefit)
_ALTRUISM_HINTS = (
    "help", "for them", "users", "user benefit",
    "他者", "彼ら", "ユーザのために", "公益", "shared",
    "donate", "open source", "share with",
    "提案", "助ける",
)


def _count_hits(text: str, hints: tuple[str, ...]) -> int:
    low = text.lower()
    return sum(1 for h in hints if h.lower() in low)


def score_thought(thought: Thought, *, brief_content: str = "") -> tuple[float, float]:
    """Return ``(ego_score, altruism_score)`` in roughly [0, 1] each.

    Crude lexical heuristic. Returns equal small baseline if no hints match,
    so callers can still rank thoughts by other criteria.

    LLIVE-005 fix (2026-05-18): ``brief_content`` (optional) lets the
    scorer also draw signal from the original Brief text, so the score
    no longer collapses to the (0.1, 0.1) baseline when the LLM-generated
    ``thought.text`` is short / template-shaped. Keeping the parameter
    keyword-only and defaulted preserves the existing single-arg API.
    """
    text = (thought.text or "") + "\n" + (brief_content or "")
    ego = _count_hits(text, _EGO_HINTS)
    alt = _count_hits(text, _ALTRUISM_HINTS)
    total = ego + alt
    if total == 0:
        return 0.1, 0.1
    return min(1.0, ego / max(1, total) + 0.05 * ego), min(1.0, alt / max(1, total) + 0.05 * alt)


class EgoAltruismScorer:
    """Scorer with adjustable bias.

    ``altruism_bias=1.0`` (default) means equal weight. ``> 1.0`` favours
    altruistic thoughts (Output Bus more likely to PROPOSE). ``< 1.0`` makes
    the loop more cautious / self-preserving.

    LLIVE-005 fix (2026-05-18): :meth:`score` accepts an optional
    ``brief_content`` so callers (e.g. ``FullSenseLoop._score_thought``)
    can pass the original Stimulus text. This avoids the previous
    failure mode where Briefs without ego/altruism keywords in the
    LLM-generated ``thought.text`` always returned (0.1, 0.1).
    """

    def __init__(self, altruism_bias: float = 1.0) -> None:
        self.altruism_bias = float(altruism_bias)

    def score(
        self,
        thought: Thought,
        *,
        brief_content: str = "",
    ) -> tuple[float, float]:
        ego, alt = score_thought(thought, brief_content=brief_content)
        return ego, alt * self.altruism_bias
