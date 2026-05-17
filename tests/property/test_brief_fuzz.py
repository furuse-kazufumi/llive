# SPDX-License-Identifier: Apache-2.0
"""Property-based fuzzing for Brief / PromptLinter / Annotation round-trip.

hypothesis で randomized 入力を投げ、crash や invariant violation を発見する。
"""

from __future__ import annotations

import string

import pytest
from hypothesis import given, settings, strategies as st

from llive.annotations import Annotation, AnnotationBundle, AnnotationEmitter
from llive.brief import (
    Brief,
    BriefValidationError,
    PremortemGenerator,
    PromptLinter,
)


# Brief ID は ascii word + dash + dot のみ許可 — generator も合わせる
_BRIEF_ID = st.text(
    alphabet=st.sampled_from(string.ascii_letters + string.digits + "_-."),
    min_size=1, max_size=64,
).filter(lambda s: s[0].isalnum())


_GOAL_TEXT = st.text(min_size=1, max_size=500)
_CONSTRAINT_LIST = st.lists(st.text(min_size=0, max_size=80), min_size=0, max_size=10)


@given(brief_id=_BRIEF_ID, goal=_GOAL_TEXT)
@settings(max_examples=80, deadline=None)
def test_brief_construction_invariants(brief_id: str, goal: str) -> None:
    """Construction must either succeed or raise BriefValidationError, never crash."""
    if not goal.strip():
        with pytest.raises(BriefValidationError):
            Brief(brief_id=brief_id, goal=goal)
        return
    b = Brief(brief_id=brief_id, goal=goal)
    assert b.brief_id == brief_id


@given(goal=_GOAL_TEXT, constraints=_CONSTRAINT_LIST)
@settings(max_examples=60, deadline=None)
def test_prompt_linter_never_crashes(goal: str, constraints: list[str]) -> None:
    if not goal.strip():
        return
    brief = Brief(brief_id="fuzz-pl", goal=goal, constraints=tuple(constraints))
    report = PromptLinter().lint(brief)
    # Findings must reference valid categories
    valid_cats = {"vague_term", "unmeasurable_claim", "missing_audience", "missing_comparison", "undefined_constraint"}
    for f in report.findings:
        assert f.category in valid_cats


@given(goal=_GOAL_TEXT, constraints=_CONSTRAINT_LIST)
@settings(max_examples=60, deadline=None)
def test_premortem_never_crashes(goal: str, constraints: list[str]) -> None:
    if not goal.strip():
        return
    brief = Brief(brief_id="fuzz-pm", goal=goal, constraints=tuple(constraints))
    report = PremortemGenerator().generate(brief)
    # has_high_impact must be a bool
    assert isinstance(report.has_high_impact, bool)


# Annotation value generator — JSON-friendly recursive
_JSON_PRIMITIVE = st.one_of(
    st.none(), st.booleans(),
    st.integers(min_value=-(10**9), max_value=10**9),
    st.floats(allow_nan=False, allow_infinity=False, width=32),
    st.text(min_size=0, max_size=40),
)
_JSON_VALUE = st.recursive(
    _JSON_PRIMITIVE,
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(st.text(min_size=1, max_size=10), children, max_size=5),
    ),
    max_leaves=10,
)


@given(
    namespace=st.sampled_from(["cog", "vrb", "oka", "math", "creat", "core"]),
    key=st.text(alphabet=string.ascii_letters + string.digits + "_", min_size=1, max_size=20),
    value=_JSON_VALUE,
)
@settings(max_examples=60, deadline=None)
def test_annotation_round_trip(namespace: str, key: str, value) -> None:
    """Single annotation round-trips through to_html_comments/from_html_comments."""
    a = Annotation(namespace=namespace, key=key, value=value)
    bundle = AnnotationBundle.of(a)
    encoded = bundle.to_html_comments()
    decoded = AnnotationBundle.from_html_comments(encoded)
    assert len(decoded) == 1
    parsed = decoded.items[0]
    assert parsed.namespace == namespace
    assert parsed.key == key
    # JSON round-trip preserves value
    assert parsed.value == value
