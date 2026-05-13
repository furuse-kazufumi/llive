"""LLW-05 Wiki diff ChangeOp tests."""

from __future__ import annotations

import pytest

from llive.evolution.wiki_change_op import (
    AddConcept,
    MergeConcept,
    RemoveConcept,
    SplitConcept,
    WikiChangeOpError,
    WikiDiff,
    apply_wiki_diff,
    invert_wiki_diff,
)
from llive.memory.concept import ConceptPage
from llive.memory.provenance import Provenance


def _page(slug: str, summary: str = "") -> ConceptPage:
    return ConceptPage(
        concept_id=slug,
        title=slug.replace("-", " "),
        summary=summary,
        provenance=Provenance(source_type="test", source_id=f"{slug}-prov", derived_from=[slug]),
    )


def test_add_concept_roundtrip():
    op = AddConcept(page=_page("foo"))
    after = op.apply({})
    assert "foo" in after
    inv = op.invert({})
    assert isinstance(inv, RemoveConcept)
    assert inv.apply(after) == {}


def test_add_duplicate_rejected():
    op = AddConcept(page=_page("foo"))
    with pytest.raises(WikiChangeOpError):
        op.apply({"foo": _page("foo")})


def test_remove_missing_rejected():
    with pytest.raises(WikiChangeOpError):
        RemoveConcept(concept_id="ghost").apply({})


def test_merge_concept_consolidates_derived_from():
    pages = {"a": _page("a", "alpha"), "b": _page("b", "beta"), "c": _page("c", "gamma")}
    op = MergeConcept(from_ids=["a", "b"], into_id="c", new_summary="merged")
    after = op.apply(pages)
    assert "a" not in after and "b" not in after
    target = after["c"]
    assert target.summary == "merged"
    assert set(target.provenance.derived_from) == {"a", "b", "c"}


def test_merge_into_self_rejected():
    pages = {"a": _page("a")}
    with pytest.raises(WikiChangeOpError):
        MergeConcept(from_ids=["a"], into_id="a").apply(pages)


def test_merge_missing_source_rejected():
    pages = {"c": _page("c")}
    with pytest.raises(WikiChangeOpError):
        MergeConcept(from_ids=["ghost"], into_id="c").apply(pages)


def test_merge_invert_restores_pre_state():
    pages = {"a": _page("a", "alpha"), "b": _page("b", "beta"), "c": _page("c", "gamma")}
    diff = WikiDiff(ops=[MergeConcept(from_ids=["a", "b"], into_id="c", new_summary="merged")])
    after, _ = apply_wiki_diff(pages, diff)
    inverse = invert_wiki_diff(pages, diff)
    restored, _ = apply_wiki_diff(after, inverse)
    assert set(restored.keys()) == {"a", "b", "c"}
    assert restored["c"].summary == "gamma"


def test_split_concept_creates_new_pages():
    pages = {"big": _page("big", "everything")}
    op = SplitConcept(from_id="big", new_pages=[_page("small1"), _page("small2")])
    after = op.apply(pages)
    assert "big" not in after
    assert {"small1", "small2"} <= set(after.keys())


def test_split_keep_original():
    pages = {"big": _page("big", "everything")}
    op = SplitConcept(from_id="big", new_pages=[_page("small1")], keep_original=True)
    after = op.apply(pages)
    assert "big" in after
    assert "small1" in after


def test_split_invert_restores():
    pages = {"big": _page("big", "everything")}
    diff = WikiDiff(ops=[SplitConcept(from_id="big", new_pages=[_page("small1"), _page("small2")])])
    after, _ = apply_wiki_diff(pages, diff)
    inverse = invert_wiki_diff(pages, diff)
    restored, _ = apply_wiki_diff(after, inverse)
    assert set(restored.keys()) == {"big"}
    assert restored["big"].summary == "everything"


def test_split_missing_source_rejected():
    with pytest.raises(WikiChangeOpError):
        SplitConcept(from_id="ghost", new_pages=[_page("x")]).apply({})


def test_split_no_new_pages_rejected():
    pages = {"big": _page("big")}
    with pytest.raises(WikiChangeOpError):
        SplitConcept(from_id="big", new_pages=[]).apply(pages)


def test_split_target_collision_rejected():
    pages = {"big": _page("big"), "small1": _page("small1")}
    with pytest.raises(WikiChangeOpError):
        SplitConcept(from_id="big", new_pages=[_page("small1")]).apply(pages)


def test_diff_apply_in_order():
    pages = {}
    diff = WikiDiff(
        ops=[
            AddConcept(page=_page("a")),
            AddConcept(page=_page("b")),
            MergeConcept(from_ids=["a"], into_id="b"),
        ]
    )
    after, _ = apply_wiki_diff(pages, diff)
    assert "a" not in after
    assert "b" in after


def test_wikidiff_id_generated():
    d = WikiDiff()
    assert d.diff_id.startswith("wdiff_")
