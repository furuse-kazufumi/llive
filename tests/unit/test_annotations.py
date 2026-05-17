# SPDX-License-Identifier: Apache-2.0
"""IND-04 — Annotation channel tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from llive.annotations import (
    Annotation,
    AnnotationBundle,
    AnnotationEmitter,
    KNOWN_NAMESPACES,
)
from llive.brief import (
    Brief,
    BriefRunner,
    DualSpecWriter,
    PromptLinter,
    RenderMode,
    RoleBasedMultiTrack,
)
from llive.fullsense.loop import FullSenseLoop
from llive.oka import CoreEssenceExtractor


# ---------------------------------------------------------------------------
# Annotation contract
# ---------------------------------------------------------------------------


def test_annotation_requires_non_empty_ns_and_key() -> None:
    with pytest.raises(ValueError):
        Annotation(namespace="", key="x")
    with pytest.raises(ValueError):
        Annotation(namespace="x", key="")


def test_annotation_rejects_non_json_value() -> None:
    class _NotJsonable:
        pass

    with pytest.raises(TypeError):
        Annotation(namespace="x", key="y", value=_NotJsonable())


def test_annotation_accepts_nested_json_value() -> None:
    a = Annotation(namespace="x", key="y", value={"k": [1, 2, {"a": True}]})
    assert a.to_payload()["value"]["k"][2]["a"] is True


def test_known_namespaces_present() -> None:
    for ns in ("core", "oka", "cog", "vrb", "math", "creat"):
        assert ns in KNOWN_NAMESPACES


# ---------------------------------------------------------------------------
# Bundle helpers
# ---------------------------------------------------------------------------


def test_bundle_for_layer_filters_targets() -> None:
    b = AnnotationBundle.of(
        Annotation(namespace="vrb", key="a", value=1, target_layer="llove"),
        Annotation(namespace="cog", key="b", value=2, target_layer=None),
        Annotation(namespace="math", key="c", value=3, target_layer="llmesh"),
    )
    llove = b.for_layer("llove")
    assert len(llove) == 2  # llove-targeted + any
    assert all(a.target_layer in ("llove", None) for a in llove)


def test_bundle_get_returns_value_or_default() -> None:
    b = AnnotationBundle.of(Annotation(namespace="x", key="y", value=42))
    assert b.get("x", "y") == 42
    assert b.get("x", "missing", default="fallback") == "fallback"


def test_emitter_freeze_returns_immutable_bundle() -> None:
    em = AnnotationEmitter()
    em.add("cog", "consensus", value="proceed")
    em.add("vrb", "lint_score", value=0.8, target_layer="llove")
    b = em.freeze()
    assert isinstance(b, AnnotationBundle)
    assert len(b) == 2


# ---------------------------------------------------------------------------
# HTML comment encoding — must be invisible in rendered Markdown/HTML
# ---------------------------------------------------------------------------


def test_to_html_comments_uses_comment_syntax() -> None:
    b = AnnotationBundle.of(
        Annotation(namespace="cog", key="consensus", value="proceed"),
        Annotation(namespace="vrb", key="lint_findings_count", value=3, target_layer="llove"),
    )
    out = b.to_html_comments()
    assert "<!--" in out and "-->" in out
    assert "llive:cog.consensus=" in out
    assert 'target=llove' in out


def test_html_comments_round_trip() -> None:
    b = AnnotationBundle.of(
        Annotation(namespace="cog", key="consensus", value="hold"),
        Annotation(namespace="oka", key="essence_card", value={"summary": "x"}, target_layer="llove"),
    )
    encoded = b.to_html_comments()
    parsed = AnnotationBundle.from_html_comments(encoded)
    assert len(parsed) == 2
    assert parsed.get("cog", "consensus") == "hold"
    assert parsed.get("oka", "essence_card") == {"summary": "x"}


def test_empty_bundle_renders_empty_string() -> None:
    assert AnnotationBundle.empty().to_html_comments() == ""


def test_from_html_comments_skips_malformed_lines() -> None:
    text = (
        "<!-- llive:cog.consensus=\"proceed\" -->\n"
        "<!-- malformed comment here -->\n"
        "regular markdown text\n"
    )
    parsed = AnnotationBundle.from_html_comments(text)
    assert len(parsed) == 1
    assert parsed.get("cog", "consensus") == "proceed"


# ---------------------------------------------------------------------------
# BriefRunner emits annotations + independence
# ---------------------------------------------------------------------------


def test_runner_emits_core_annotation_always(tmp_path: Path) -> None:
    runner = BriefRunner(loop=FullSenseLoop(sandbox=True, salience_threshold=0.0))
    brief = Brief(brief_id="ann-1", goal="x", approval_required=False, ledger_path=tmp_path / "1.jsonl")
    result = runner.submit(brief)
    # core.brief_completed should always be present once the Brief completes
    ann_bundle = AnnotationBundle.of(*[Annotation(**dict(a)) for a in result.annotations])
    assert ann_bundle.get("core", "brief_completed") is True


def test_runner_emits_cog_consensus_when_perspectives_attached(tmp_path: Path) -> None:
    runner = BriefRunner(
        loop=FullSenseLoop(sandbox=True, salience_threshold=0.0),
        perspectives=RoleBasedMultiTrack(),
    )
    brief = Brief(brief_id="ann-2", goal="x", approval_required=False, ledger_path=tmp_path / "2.jsonl")
    result = runner.submit(brief)
    ann_bundle = AnnotationBundle.of(*[Annotation(**dict(a)) for a in result.annotations])
    assert ann_bundle.get("cog", "consensus") in {"proceed", "review", "hold"}


def test_runner_independence_no_annotations_used(tmp_path: Path) -> None:
    """consumer 不在でも runner / result は壊れない."""
    runner = BriefRunner(
        loop=FullSenseLoop(sandbox=True, salience_threshold=0.0),
        essence_extractor=CoreEssenceExtractor(),
        perspectives=RoleBasedMultiTrack(),
    )
    brief = Brief(brief_id="ann-3", goal="independence check", approval_required=False, ledger_path=tmp_path / "3.jsonl")
    result = runner.submit(brief)
    # 結果は annotations を一切読まなくても完結
    assert result.brief_id == "ann-3"
    assert result.essence is not None
    # annotations はあるが consumer は無視できる
    assert isinstance(result.annotations, tuple)


def test_render_embeds_annotations_as_html_comments() -> None:
    brief = Brief(brief_id="ann-4", goal="render test")
    bundle = AnnotationBundle.of(
        Annotation(namespace="cog", key="consensus", value="proceed", target_layer="llove"),
    )
    out = DualSpecWriter().render(brief, RenderMode.HUMAN_BRIEF, annotations=bundle)
    assert "<!--" in out.body
    # 本体 (heading) は無傷
    assert "# Brief: ann-4" in out.body


def test_render_without_annotations_has_no_comments() -> None:
    brief = Brief(brief_id="ann-5", goal="no comments here")
    out = DualSpecWriter().render(brief, RenderMode.HUMAN_BRIEF)
    assert "<!--" not in out.body
