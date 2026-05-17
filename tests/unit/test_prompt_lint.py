# SPDX-License-Identifier: Apache-2.0
"""VRB-02 — PromptLinter tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from llive.brief import Brief, BriefLedger, LintFinding, LintReport, PromptLinter


def _brief(**overrides) -> Brief:
    fields: dict = dict(
        brief_id="lint-1",
        goal="高性能なログ収集を実装",
        constraints=("使いやすく",),
        success_criteria=("十分なスループット",),
    )
    fields.update(overrides)
    return Brief(**fields)


def test_lint_detects_vague_term_in_goal() -> None:
    linter = PromptLinter()
    report = linter.lint(_brief(goal="高性能で堅牢なシステム", constraints=(), success_criteria=()))
    assert any(f.category == "vague_term" for f in report.findings)


def test_lint_detects_unmeasurable_claim() -> None:
    linter = PromptLinter()
    report = linter.lint(_brief(success_criteria=("最適なレスポンス",)))
    assert any(f.category == "unmeasurable_claim" for f in report.findings)


def test_lint_detects_missing_audience() -> None:
    linter = PromptLinter()
    report = linter.lint(_brief(
        goal="使いやすく",
        constraints=(),
        success_criteria=(),
    ))
    assert any(f.category == "missing_audience" for f in report.findings)


def test_lint_audience_satisfied_when_constraints_mention_users() -> None:
    linter = PromptLinter()
    report = linter.lint(_brief(
        goal="使いやすく",
        constraints=("対象ユーザーは researcher",),
        success_criteria=(),
    ))
    assert not any(f.category == "missing_audience" for f in report.findings)


def test_lint_detects_missing_comparison() -> None:
    linter = PromptLinter()
    report = linter.lint(_brief(
        goal="既存手法より優秀な実装",
        constraints=(),
        success_criteria=(),
    ))
    assert any(f.category == "missing_comparison" for f in report.findings)


def test_lint_comparison_satisfied_with_baseline() -> None:
    linter = PromptLinter()
    report = linter.lint(_brief(
        goal="既存手法より優秀 (vs qwen2.5:7b)",
        constraints=(),
        success_criteria=(),
    ))
    assert not any(f.category == "missing_comparison" for f in report.findings)


def test_lint_detects_undefined_constraint() -> None:
    linter = PromptLinter()
    report = linter.lint(_brief(
        goal="x",
        constraints=("メモリを考慮",),
        success_criteria=(),
    ))
    assert any(f.category == "undefined_constraint" for f in report.findings)


def test_lint_clean_brief() -> None:
    linter = PromptLinter()
    report = linter.lint(_brief(
        goal="ingest 10k events/s on a single node",
        constraints=("p99 < 100ms", "memory <= 2GB"),
        success_criteria=("zero data loss",),
    ))
    assert report.is_clean
    assert report.by_category() == {
        "vague_term": 0,
        "unmeasurable_claim": 0,
        "missing_audience": 0,
        "missing_comparison": 0,
        "undefined_constraint": 0,
    }


def test_lint_ledger_integration_and_trace_graph(tmp_path: Path) -> None:
    ledger = BriefLedger(tmp_path / "lint.jsonl")
    linter = PromptLinter(ledger=ledger)
    linter.lint(_brief())
    events = [r for r in ledger.read() if r.event == "lint_findings_recorded"]
    assert events
    tg = ledger.trace_graph()
    assert any(e.get("kind") == "lint" for e in tg.evidence_chain)


def test_lint_finding_rejects_invalid_category() -> None:
    with pytest.raises(ValueError):
        LintFinding(category="bogus", field_name="goal", excerpt="x", rationale="r")


def test_lint_report_summary_counts() -> None:
    f1 = LintFinding(category="vague_term", field_name="goal", excerpt="高性能", rationale="r")
    f2 = LintFinding(category="vague_term", field_name="constraints[0]", excerpt="堅牢", rationale="r")
    f3 = LintFinding(category="unmeasurable_claim", field_name="goal", excerpt="最適", rationale="r")
    rep = LintReport(brief_id="x", findings=(f1, f2, f3))
    summary = rep.by_category()
    assert summary["vague_term"] == 2
    assert summary["unmeasurable_claim"] == 1
