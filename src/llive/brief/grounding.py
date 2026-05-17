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
from llive.math import (
    CalculationError,
    ConstantNotFoundError,
    Dimensions,
    SafeCalculator,
    UnitMismatchError,
    extract_expressions,
    get_constant,
    list_constants,
    parse_unit,
)
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

# 否定文脈 — trigger が含まれていても、これらフレーズの一部として現れた
# 場合は発火させない。2026-05-17-grounding-observation で
# "the speed of light" が #35 (Parameter Changes) を誤発火していた対応。
_TRIZ_NEGATIVE_CONTEXTS: dict[str, tuple[str, ...]] = {
    "speed": ("speed of light", "lightspeed"),
    "via":   ("via point", "via the api"),
}

# 単一文字 / 短い English trigger は word boundary を要求 (substring の
# 偽陽性が多すぎる)。日本語語彙には word boundary は適用しない (CJK は
# regex \b と相性が悪いため)。
_WORD_BOUNDARY_TRIGGERS: frozenset[str] = frozenset({
    "vs", "via", "ground", "speed", "quality", "static", "dynamic",
    "idle", "compose", "composite", "knob",
})


_TOKEN_RE = re.compile(r"[A-Za-z0-9_぀-ゟ゠-ヿ一-鿿]+", re.UNICODE)


def _trigger_matches(trigger: str, text_lower: str) -> bool:
    """Return True if trigger applies to the (lower-cased) Brief text.

    Two refinements on plain substring match (2026-05-17-grounding-observation):

    1. **Word-boundary** for short / ambiguous English triggers (see
       ``_WORD_BOUNDARY_TRIGGERS``) — prevents ``speedy`` from firing the
       ``speed`` trigger.
    2. **Negative context** — even when the trigger is present, suppress
       firing if any phrase in ``_TRIZ_NEGATIVE_CONTEXTS[trigger]`` is also
       present (e.g. ``speed of light``). Lets the ``speed`` trigger fire
       on ``speed vs accuracy`` while staying quiet on
       ``the speed of light``.
    """
    if trigger in _WORD_BOUNDARY_TRIGGERS:
        if not re.search(rf"\b{re.escape(trigger)}\b", text_lower):
            return False
    elif trigger not in text_lower:
        return False
    for neg in _TRIZ_NEGATIVE_CONTEXTS.get(trigger, ()):
        if neg in text_lower:
            return False
    return True

# MATH-01 minimal: 数値 + 単位 を抽出 (例: "5 m/s", "9.81 m/s^2", "100 kg").
# 偽陽性 (e.g. "5 days") は parse_unit で UnitMismatchError → citation.error
# に格納する。完全に正しい NER ではなく「Brief 中の単位候補を漏らさず拾う」
# 緩い抽出器。
_QUANTITY_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s+([A-Za-z][A-Za-z0-9*/\^·]{0,15})\b"
)

# 「数値の後ろに来るがどう見ても単位ではない」ドメイン語のブラックリスト。
# 2026-05-17-grounding-observation で `1 email` `30 pages` が citation
# に大量に残っていた対応。これらは silently skip して error citation の
# 価値 (= 未知単位の自動収集) を守る。
_NON_UNIT_WORDS: frozenset[str] = frozenset({
    "email", "emails", "user", "users", "page", "pages", "item", "items",
    "request", "requests", "point", "points", "slide", "slides",
    "chapter", "chapters", "widget", "widgets", "ticket", "tickets",
    "comment", "comments", "issue", "issues", "story", "stories",
    "row", "rows", "column", "columns", "record", "records",
    "people", "person", "customer", "customers", "step", "steps",
    "task", "tasks", "milestone", "milestones",
})


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
class ConstantCitation:
    """One CODATA / NIST constant the Brief mentions (MATH-05 minimal grounding).

    Recorded so the LLM consumes the grounded value (e.g. light speed =
    2.99792458e8 m/s) rather than re-deriving it from memory and likely
    getting the last few digits wrong.
    """

    matched_alias: str         # e.g. "planck"
    name: str                  # canonical name, e.g. "planck_constant"
    symbol: str
    value: float
    dimensions: str
    relative_uncertainty: float
    source: str


@dataclass(frozen=True)
class UnitCitation:
    """One value+unit pair recognised in a Brief (MATH-01 minimal grounding).

    Recorded so the LLM (and later, the auditor) can see exactly how each
    quantity in the Brief mapped to an SI dimension vector. Unknown unit
    symbols are surfaced as ``error`` rather than silently dropped — both
    so the auditor sees what was tried, and so we collect failure modes
    for refining the parser.
    """

    raw_text: str         # e.g. "5 m/s"
    value: float          # numeric magnitude as parsed
    unit_text: str        # e.g. "m/s"
    dimensions: str       # str(Dimensions), e.g. "m·s^-1"
    error: str | None = None


@dataclass(frozen=True)
class GroundedBrief:
    """Result of running a Brief through :class:`BriefGrounder`.

    ``augmented_goal`` is what should replace ``brief.goal`` when building
    the Stimulus. The citation fields are kept separate so the ledger can
    record them as structured citations rather than re-parsing text.
    """

    augmented_goal: str
    triz: tuple[TrizCitation, ...] = ()
    rad: tuple[RadCitation, ...] = ()
    calc: tuple[CalcCitation, ...] = ()
    units: tuple[UnitCitation, ...] = ()
    constants: tuple[ConstantCitation, ...] = ()


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
    max_calc: int = 5
    # MATH-08: 内蔵計算結果の上限。大きい数を扱う Brief で prompt が膨れないよう抑制。
    max_units: int = 6
    # MATH-01 minimal grounding: 「数値+単位」の citation 数上限。Brief 文中の
    # 単位を 1 件ずつ Dimensions に焼き付ける。最小実装、次元演算チェックは
    # 後段イテレーションで追加 (実装→課題発見→厚み増しの原則)。
    max_constants: int = 4
    # MATH-05 minimal grounding: 物理定数 (CODATA/NIST) を Brief から検出し
    # 値を grounded に注入する citation 数上限。短い symbol (c, h, e, G) は
    # 偽陽性が多いので、長さ 3 文字以上の alias / name のみ match させる。


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
        calc = self._lookup_calc(brief)
        units = self._lookup_units(brief)
        constants = self._lookup_constants(brief)
        augmented = self._build_augmented_goal(
            brief, triz, rad, calc, units, constants
        )
        return GroundedBrief(
            augmented_goal=augmented,
            triz=triz,
            rad=rad,
            calc=calc,
            units=units,
            constants=constants,
        )

    # -- internals -----------------------------------------------------------

    def _lookup_triz(self, brief: Brief) -> tuple[TrizCitation, ...]:
        text = self._brief_text(brief).lower()
        principles = self._principles or load_principles()
        seen: dict[int, TrizCitation] = {}
        for trigger, pid in _TRIZ_TRIGGERS.items():
            if not _trigger_matches(trigger, text):
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

    def _lookup_constants(self, brief: Brief) -> tuple[ConstantCitation, ...]:
        """MATH-05 minimal — recognise mentions of CODATA/NIST constants.

        Strategy: walk every alias/name registered in :func:`list_constants`,
        skip aliases shorter than 3 chars (those trigger far too many false
        positives in natural language), and surface a citation when the
        Brief text contains the alias as a whole word (case-insensitive).

        Like the unit layer, this is **deliberately minimal** — we are
        collecting which constants actually surface in real Briefs before
        investing in a smarter NER pass.
        """
        if self.config.max_constants <= 0:
            return ()
        text = self._brief_text(brief).lower()
        seen_canonical: set[str] = set()
        out: list[ConstantCitation] = []
        for const in list_constants():
            candidates = (const.name, const.symbol) + tuple(const.aliases)
            for alias in candidates:
                key = alias.lower()
                if len(key) < 3:
                    # Too noisy (c, h, e, G — common natural-language words)
                    continue
                # Try the alias as-is and with underscores swapped for spaces
                # (so e.g. "elementary_charge" can match "elementary charge").
                key_spaced = key.replace("_", " ")
                pattern = rf"\b{re.escape(key)}\b"
                if key_spaced != key:
                    pattern = rf"(?:\b{re.escape(key)}\b|\b{re.escape(key_spaced)}\b)"
                if not re.search(pattern, text):
                    continue
                if const.name in seen_canonical:
                    break
                try:
                    resolved = get_constant(alias)
                except ConstantNotFoundError:
                    break
                seen_canonical.add(resolved.name)
                out.append(
                    ConstantCitation(
                        matched_alias=alias,
                        name=resolved.name,
                        symbol=resolved.symbol,
                        value=resolved.quantity.value,
                        dimensions=str(resolved.quantity.dimensions),
                        relative_uncertainty=resolved.relative_uncertainty,
                        source=resolved.source,
                    )
                )
                break
            if len(out) >= self.config.max_constants:
                break
        return tuple(out)

    def _lookup_units(self, brief: Brief) -> tuple[UnitCitation, ...]:
        """MATH-01 minimal — recognise value+unit pairs in the Brief.

        Each match is parsed via ``parse_unit``; unknown symbols are kept as
        citations with ``error`` set so the auditor can see what was tried
        (e.g. ``5 days`` will surface as an error citation, alerting the
        operator that the parser doesn't yet know about that unit).

        This is intentionally a **minimal** layer — dimensional arithmetic
        checks across multiple quantities (``5 m/s + 3 s``) are deferred to
        the next iteration once we collect real-world Brief samples and see
        what shapes of mismatch actually need surfacing.
        """
        if self.config.max_units <= 0:
            return ()
        text = self._brief_text(brief)
        seen: set[tuple[str, str]] = set()
        out: list[UnitCitation] = []
        for m in _QUANTITY_RE.finditer(text):
            value_s, unit_text = m.group(1), m.group(2)
            key = (value_s, unit_text)
            if key in seen:
                continue
            seen.add(key)
            raw = f"{value_s} {unit_text}"
            try:
                value = float(value_s)
            except ValueError:
                continue
            try:
                dims = parse_unit(unit_text)
            except UnitMismatchError as e:
                out.append(
                    UnitCitation(
                        raw_text=raw,
                        value=value,
                        unit_text=unit_text,
                        dimensions="?",
                        error=str(e),
                    )
                )
            else:
                out.append(
                    UnitCitation(
                        raw_text=raw,
                        value=value,
                        unit_text=unit_text,
                        dimensions=str(dims),
                        error=None,
                    )
                )
            if len(out) >= self.config.max_units:
                break
        return tuple(out)

    def _lookup_calc(self, brief: Brief) -> tuple[CalcCitation, ...]:
        """MATH-08 — extract arithmetic expressions and evaluate deterministically.

        LLM is never asked to compute the arithmetic; instead we evaluate
        every expression locally and inject the result as grounded evidence.
        Failures (zero division, malformed) are kept as citations with
        ``error`` set so the auditor can see exactly what was rejected.
        """
        if self.config.max_calc <= 0:
            return ()
        text = self._brief_text(brief)
        expressions = extract_expressions(text)
        if not expressions:
            return ()
        calc = SafeCalculator()
        out: list[CalcCitation] = []
        for expr in expressions:
            try:
                r = calc.evaluate(expr)
            except CalculationError as e:
                out.append(
                    CalcCitation(
                        expression=expr,
                        value=float("nan"),
                        operation_count=0,
                        used_functions=(),
                        error=str(e),
                    )
                )
            else:
                out.append(
                    CalcCitation(
                        expression=r.expression,
                        value=r.value,
                        operation_count=r.operation_count,
                        used_functions=r.used_functions,
                        error=None,
                    )
                )
            if len(out) >= self.config.max_calc:
                break
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
        calc: tuple[CalcCitation, ...] = (),
        units: tuple[UnitCitation, ...] = (),
        constants: tuple[ConstantCitation, ...] = (),
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
        if calc:
            block = ["", "[Inlined calculations (MATH-08)]"]
            for c in calc:
                if c.error is not None:
                    block.append(f"- {c.expression} = ERROR: {c.error}")
                else:
                    fn_note = (
                        f" [uses: {', '.join(c.used_functions)}]"
                        if c.used_functions
                        else ""
                    )
                    block.append(
                        f"- {c.expression} = {c.value!r} (ops={c.operation_count}){fn_note}"
                    )
            sections.append("\n".join(block))
        if units:
            block = ["", "[Quantities recognised (MATH-01)]"]
            for u in units:
                if u.error is not None:
                    block.append(f"- {u.raw_text} → UNKNOWN UNIT ({u.error})")
                else:
                    block.append(
                        f"- {u.raw_text} → value={u.value}, dimensions={u.dimensions}"
                    )
            sections.append("\n".join(block))
        if constants:
            block = ["", "[Physical constants grounded (MATH-05)]"]
            for c in constants:
                rel_u = (
                    f", rel.unc.={c.relative_uncertainty:.1e}"
                    if c.relative_uncertainty
                    else ""
                )
                block.append(
                    f"- {c.matched_alias} → {c.symbol} = {c.value!r} [{c.dimensions}]{rel_u} ({c.source})"
                )
            sections.append("\n".join(block))
        return "\n".join(sections)
