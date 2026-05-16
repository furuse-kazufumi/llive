# SPDX-License-Identifier: Apache-2.0
"""BriefGrounder — TRIZ × RAD grounding layer for the Brief API (L1).

Before a Brief is converted to a Stimulus and handed to the loop, this
module enriches it with:

* relevant TRIZ principles (by lexical trigger match against the loop's
  built-in trigger map plus the principle index) — each candidate is
  reported with **principle id + name**, so the ledger contains a stable
  citation that can be verified after the fact.
* top-N RAD corpus hits scored by the existing `query()` function. Each
  hit carries **domain + doc_path + excerpt**, again so the citation is
  auditable.

The grounded `augmented_goal` is the original goal followed by two
optional blocks: ``[TRIZ principles considered]`` and ``[RAD grounding
hits]``. Empty blocks are omitted so a Brief that needs no grounding
isn't padded with empty sections.

**Precision-first design choice (2026-05-17, per user direction):** we
never silently substitute an alternate principle or doc; the ledger
records *exactly* what was injected, so the operator can later check
whether the LLM cited the supplied sources faithfully (vs hallucinating).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from llive.brief.types import Brief
from llive.memory.rad import RadCorpusIndex
from llive.memory.rad.query import query as rad_query
from llive.triz.loader import load_principles

# Lightweight TRIZ trigger map — kept lexical because the structured
# ContradictionDetector wants timeseries metrics, not free-text Briefs.
# Same triggers FullSenseLoop uses internally, plus a few common
# domain-specific aliases. Trigger -> principle id.
_TRIZ_TRIGGERS: dict[str, int] = {
    "vs": 1,
    "versus": 1,
    "trade-off": 1,
    "tradeoff": 1,
    "contradiction": 1,
    "矛盾": 1,
    "両立": 1,
    "static": 15,
    "dynamic": 15,
    "動かない": 15,
    "動的": 15,
    "via": 24,
    "mediator": 24,
    "ground": 24,
    "grounding": 24,
    "idle": 19,
    "periodic": 19,
    "繰り返": 19,
    "parameter": 35,
    "knob": 35,
    "high precision": 3,
    "local quality": 3,
    "specialist": 3,
    "領域別": 3,
    "speed": 35,
    "quality": 35,
    "高品質": 35,
    "高速": 15,
    "compose": 40,
    "composite": 40,
    "composition": 40,
}


_TOKEN_RE = re.compile(r"[A-Za-z0-9_぀-ゟ゠-ヿ一-鿿]+", re.UNICODE)


@dataclass(frozen=True)
class TrizCitation:
    """One TRIZ principle considered relevant for a Brief."""

    principle_id: int
    name: str
    description: str = ""
    trigger: str = ""  # the substring in the Brief that surfaced this principle


@dataclass(frozen=True)
class RadCitation:
    """One RAD corpus hit injected as grounding evidence."""

    domain: str
    doc_path: str
    score: float
    excerpt: str
    matched_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class CalcCitation:
    """One inlined calculation injected by SafeCalculator (MATH-08).

    Recorded in the ledger so an auditor can verify that the value the LLM
    consumed in the prompt is the value llive's deterministic engine
    produced — not a number the LLM imagined.
    """

    expression: str
    value: float
    operation_count: int = 0
    used_functions: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class GroundedBrief:
    """Result of running a Brief through :class:`BriefGrounder`.

    ``augmented_goal`` is what should replace ``brief.goal`` when building
    the Stimulus. The ``triz`` and ``rad`` and ``calc`` fields are kept
    separate so the ledger can record them as structured citations rather
    than re-parsing text.
    """

    augmented_goal: str
    triz: tuple[TrizCitation, ...] = ()
    rad: tuple[RadCitation, ...] = ()
    calc: tuple[CalcCitation, ...] = ()


@dataclass
class GroundingConfig:
    """Knobs for :class:`BriefGrounder`.

    Defaults err on the side of *less* injection — precision over recall —
    so a noisy Brief doesn't drown the LLM in tangential context.
    """

    max_triz: int = 3
    max_rad: int = 3
    rad_domains: tuple[str, ...] | None = None  # None = all domains
    rad_max_bytes_per_file: int = 32_768
    include_learned: bool = True


def _extract_keywords(text: str, *, max_terms: int = 8) -> list[str]:
    """Pull the most likely informative tokens out of free-text Brief content.

    Heuristic — short stopwords removed, dedupe order-preserving, capped.
    The RAD scorer is already term-set-based, so quality beats recall.
    """
    stop = {
        "the", "a", "an", "and", "or", "but", "of", "for", "to", "in", "on",
        "at", "by", "from", "with", "is", "are", "was", "be", "this", "that",
        "it", "as", "do", "does", "did", "have", "has", "had",
        "の", "を", "に", "は", "が", "と", "で", "も", "から",
    }
    seen: list[str] = []
    for tok in _TOKEN_RE.findall(text or ""):
        low = tok.lower()
        if low in stop or len(low) < 2:
            continue
        if low in seen:
            continue
        seen.append(low)
        if len(seen) >= max_terms:
            break
    return seen


class BriefGrounder:
    """Augments a :class:`Brief` with TRIZ + RAD citations before loop entry.

    Construction is cheap (no IO); :meth:`ground` triggers the actual
    lookups. The RAD index and the TRIZ principle index are both lazy-
    instantiated and can be injected for tests.
    """

    def __init__(
        self,
        *,
        rad_index: RadCorpusIndex | None = None,
        principles: dict[int, Any] | None = None,
        config: GroundingConfig | None = None,
    ) -> None:
        self._rad_index = rad_index
        self._principles = principles  # None → lazy load
        self.config = config or GroundingConfig()

    def ground(self, brief: Brief) -> GroundedBrief:
        triz = self._lookup_triz(brief)
        rad = self._lookup_rad(brief)
        augmented = self._build_augmented_goal(brief, triz, rad)
        return GroundedBrief(augmented_goal=augmented, triz=triz, rad=rad)

    # -- internals -----------------------------------------------------------

    def _lookup_triz(self, brief: Brief) -> tuple[TrizCitation, ...]:
        text = self._brief_text(brief).lower()
        principles = self._principles or load_principles()
        seen: dict[int, TrizCitation] = {}
        for trigger, pid in _TRIZ_TRIGGERS.items():
            if trigger not in text:
                continue
            if pid in seen:
                continue
            principle = principles.get(pid)
            if principle is None:
                continue
            seen[pid] = TrizCitation(
                principle_id=pid,
                name=getattr(principle, "name", ""),
                description=getattr(principle, "description", "") or "",
                trigger=trigger,
            )
            if len(seen) >= self.config.max_triz:
                break
        return tuple(seen.values())

    def _lookup_rad(self, brief: Brief) -> tuple[RadCitation, ...]:
        # Env opt-out — CI / unit tests that don't need the real corpus avoid
        # the slow RadCorpusIndex bootstrap entirely.
        import os

        if os.environ.get("LLIVE_DISABLE_RAD_GROUNDING") == "1":
            return ()
        if self._rad_index is None:
            try:
                self._rad_index = RadCorpusIndex()
            except Exception:
                # RAD corpus may be absent (CI / minimal install) — silently
                # return no citations rather than failing the Brief.
                return ()
        keywords = _extract_keywords(self._brief_text(brief))
        if not keywords:
            return ()
        try:
            hits = rad_query(
                self._rad_index,
                keywords,
                domain=list(self.config.rad_domains) if self.config.rad_domains else None,
                limit=self.config.max_rad,
                include_learned=self.config.include_learned,
                max_bytes_per_file=self.config.rad_max_bytes_per_file,
            )
        except Exception:
            return ()
        out: list[RadCitation] = []
        for h in hits:
            doc_path = h.doc_path if isinstance(h.doc_path, Path) else Path(str(h.doc_path))
            out.append(
                RadCitation(
                    domain=h.domain,
                    doc_path=doc_path.as_posix(),
                    score=float(h.score),
                    excerpt=h.excerpt,
                    matched_terms=tuple(h.matched_terms),
                )
            )
        return tuple(out)

    @staticmethod
    def _brief_text(brief: Brief) -> str:
        parts = [brief.goal]
        if brief.constraints:
            parts.extend(brief.constraints)
        if brief.success_criteria:
            parts.extend(brief.success_criteria)
        return "\n".join(parts)

    @staticmethod
    def _build_augmented_goal(
        brief: Brief,
        triz: tuple[TrizCitation, ...],
        rad: tuple[RadCitation, ...],
    ) -> str:
        sections: list[str] = [brief.goal]
        if triz:
            block = ["", "[TRIZ principles considered]"]
            for c in triz:
                block.append(
                    f"- #{c.principle_id} {c.name} — surfaced by '{c.trigger}'"
                    + (f": {c.description}" if c.description else "")
                )
            sections.append("\n".join(block))
        if rad:
            block = ["", "[RAD grounding hits]"]
            for r in rad:
                block.append(
                    f"- {r.domain} :: {r.doc_path} (score {r.score:.2f})"
                )
                if r.excerpt:
                    truncated = r.excerpt.strip().splitlines()[0][:240]
                    block.append(f"  > {truncated}")
            sections.append("\n".join(block))
        return "\n".join(sections)
