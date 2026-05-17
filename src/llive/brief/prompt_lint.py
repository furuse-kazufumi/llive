# SPDX-License-Identifier: Apache-2.0
"""VRB-02 — Prompt / Requirement Lint.

Brief.goal / constraints / success_criteria を走査し、Local LLM 研究で
代表的な「設計自由度の欠落」を deterministic に検出する。

検出カテゴリ (5):

* ``vague_term`` — 「高性能」「堅牢」「使いやすく」など曖昧語
* ``unmeasurable_claim`` — 「最適」「十分」など測れない主張
* ``missing_audience`` — 「使いやすく」等を含むが対象読者未定義
* ``missing_comparison`` — 「より良い」「比較して優秀」等で比較軸未定義
* ``undefined_constraint`` — 「考慮」「適切に」等で制約条件未定義

ガバナンス (COG-02) や PerspectiveLens (COG-04) との責務分離:

* **Governance** = 採点 (scoring)
* **Perspectives** = 視点別観察 (multi-track observation)
* **PromptLint** = 入力設計の欠落検出 (input-time lint)

3 つは独立に走り、いずれも blocking はせず audit に積むだけ。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterable, Sequence

if TYPE_CHECKING:
    from llive.brief.ledger import BriefLedger
    from llive.brief.types import Brief


# Closed category set — kept small so cross-Brief stats stay clean.
_CATEGORIES: tuple[str, ...] = (
    "vague_term",
    "unmeasurable_claim",
    "missing_audience",
    "missing_comparison",
    "undefined_constraint",
)


# Lexical pattern → category. Designed to catch common Brief writing slips
# without being overly noisy. LLM-driven lint lens can replace these later
# via Strategy injection (same pattern as MathVerifier / EssenceLens).

_VAGUE_TERMS: tuple[str, ...] = (
    "高性能", "高速", "堅牢", "頑健", "使いやすく", "シンプルに",
    "適切な", "ちょうどよい", "良い感じ", "なるべく",
    "high performance", "robust", "user friendly", "fast", "simple",
    "good", "appropriate", "as needed",
)

_UNMEASURABLE_TERMS: tuple[str, ...] = (
    "最適", "十分", "効率的", "効果的", "本格的", "ベスト",
    "optimal", "sufficient", "efficient", "effective", "best",
)

_COMPARATIVE_TERMS: tuple[str, ...] = (
    "より", "優秀", "良い方", "ベター", "better", "superior", "preferable",
)

_AUDIENCE_HINTS: tuple[str, ...] = (
    "user", "ユーザー", "利用者", "顧客", "operator", "developer", "researcher",
    "engineer", "経営", "管理者", "学習者", "auditor",
)

_CONSTRAINT_HINTS: tuple[str, ...] = (
    "考慮", "配慮", "気を付け", "注意",
    "consider", "be careful", "mind",
)


@dataclass(frozen=True)
class LintFinding:
    """A single lint hit — replay-friendly JSON dataclass."""

    category: str
    field_name: str  # "goal" / "constraints[1]" / "success_criteria[0]"
    excerpt: str
    rationale: str
    source_id: str = ""

    def __post_init__(self) -> None:
        if self.category not in _CATEGORIES:
            raise ValueError(
                f"category must be one of {_CATEGORIES}, got {self.category!r}"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "category": self.category,
            "field_name": self.field_name,
            "excerpt": self.excerpt,
            "rationale": self.rationale,
            "source_id": self.source_id,
        }


@dataclass(frozen=True)
class LintReport:
    """All findings for one Brief lint pass."""

    brief_id: str
    findings: tuple[LintFinding, ...] = ()

    @property
    def is_clean(self) -> bool:
        return not self.findings

    def by_category(self) -> dict[str, int]:
        out: dict[str, int] = {c: 0 for c in _CATEGORIES}
        for f in self.findings:
            out[f.category] += 1
        return out

    def to_payload(self) -> dict[str, object]:
        return {
            "brief_id": self.brief_id,
            "findings": [f.to_payload() for f in self.findings],
            "summary": self.by_category(),
        }


# ---------------------------------------------------------------------------
# Scanning helpers
# ---------------------------------------------------------------------------


def _scan_terms(text: str, terms: Iterable[str]) -> list[str]:
    """Return matched terms (preserving original casing of input)."""
    low = text.lower()
    return [t for t in terms if t.lower() in low]


def _has_any(text: str, terms: Iterable[str]) -> bool:
    low = text.lower()
    return any(t.lower() in low for t in terms)


# ---------------------------------------------------------------------------
# Linter
# ---------------------------------------------------------------------------


class PromptLinter:
    """Deterministic lint pass over a Brief.

    The linter never blocks — it only surfaces structured findings the
    operator (or downstream Governance) can act on. Strategy injection:
    swap heuristics for an LLM-driven lens by subclassing and overriding
    :meth:`_scan_field`.
    """

    def __init__(self, *, ledger: "BriefLedger | None" = None) -> None:
        self._ledger = ledger

    def bind_ledger(self, ledger: "BriefLedger | None") -> None:
        self._ledger = ledger

    def lint(self, brief: "Brief") -> LintReport:
        findings: list[LintFinding] = []
        # goal
        findings.extend(self._scan_field("goal", brief.goal, brief))
        # constraints
        for idx, c in enumerate(brief.constraints):
            findings.extend(self._scan_field(f"constraints[{idx}]", c, brief))
        # success_criteria
        for idx, c in enumerate(brief.success_criteria):
            findings.extend(self._scan_field(f"success_criteria[{idx}]", c, brief))
        report = LintReport(brief_id=brief.brief_id, findings=tuple(findings))
        if self._ledger is not None:
            self._ledger.append("lint_findings_recorded", report.to_payload())
        return report

    # -- internals ----------------------------------------------------------

    def _scan_field(self, field_name: str, text: str, brief: "Brief") -> list[LintFinding]:
        if not text:
            return []
        out: list[LintFinding] = []
        # vague_term
        for hit in _scan_terms(text, _VAGUE_TERMS):
            out.append(LintFinding(
                category="vague_term",
                field_name=field_name,
                excerpt=hit,
                rationale=f"曖昧語 {hit!r} を含む — 測定可能な指標に置換推奨",
                source_id=brief.brief_id,
            ))
        # unmeasurable_claim
        for hit in _scan_terms(text, _UNMEASURABLE_TERMS):
            out.append(LintFinding(
                category="unmeasurable_claim",
                field_name=field_name,
                excerpt=hit,
                rationale=f"測れない主張 {hit!r} — 基準値/閾値/比較対象が必要",
                source_id=brief.brief_id,
            ))
        # missing_audience: vague_term と並んで現れがちな「ユーザー軸不明」
        if _has_any(text, ("使いやすく", "user friendly", "シンプルに", "simple")):
            if not _has_any(text, _AUDIENCE_HINTS):
                # 全 Brief を見渡しても audience hint が一つもなければ警告
                global_text = " ".join(
                    (brief.goal, *brief.constraints, *brief.success_criteria)
                )
                if not _has_any(global_text, _AUDIENCE_HINTS):
                    out.append(LintFinding(
                        category="missing_audience",
                        field_name=field_name,
                        excerpt=text,
                        rationale="使いやすさ系の語があるが対象読者 (audience) の宣言が無い",
                        source_id=brief.brief_id,
                    ))
        # missing_comparison
        for hit in _scan_terms(text, _COMPARATIVE_TERMS):
            # 比較先 (vs / against / 比較対象) が同テキストに無ければ flag
            low = text.lower()
            has_baseline = any(t in low for t in ("vs", "against", "対比", "比較対象", "baseline"))
            if not has_baseline:
                out.append(LintFinding(
                    category="missing_comparison",
                    field_name=field_name,
                    excerpt=hit,
                    rationale=f"比較語 {hit!r} があるが比較対象 (baseline) が明示されていない",
                    source_id=brief.brief_id,
                ))
        # undefined_constraint
        for hit in _scan_terms(text, _CONSTRAINT_HINTS):
            out.append(LintFinding(
                category="undefined_constraint",
                field_name=field_name,
                excerpt=hit,
                rationale=f"曖昧な配慮表現 {hit!r} — 具体的な制約条件 (許容値) に書き換え推奨",
                source_id=brief.brief_id,
            ))
        return out


__all__ = [
    "LintFinding",
    "LintReport",
    "PromptLinter",
]
