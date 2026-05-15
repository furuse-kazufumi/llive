# SPDX-License-Identifier: Apache-2.0
"""LLW-01: ConceptPage + repository."""

from __future__ import annotations

import pytest

from llive.memory.concept import ConceptPage, ConceptPageRepo, _slugify
from llive.memory.provenance import Provenance
from llive.memory.structural import StructuralMemory


@pytest.fixture
def repo(tmp_path):
    sm = StructuralMemory(db_path=tmp_path / "s.kuzu")
    r = ConceptPageRepo(structural=sm, wiki_dir=tmp_path / "wiki")
    yield r
    sm.close()


def _prov():
    return Provenance(source_type="wiki_compiler", source_id="cycle_test")


def test_slugify():
    assert _slugify("Hello World!") == "hello-world"
    assert _slugify("Memory_Read") == "memory-read"
    assert _slugify("") == "concept"
    assert _slugify("___---") == "concept"


def test_from_title_uses_slug():
    p = ConceptPage.from_title("BlockContainer Engine")
    assert p.concept_id == "blockcontainer-engine"
    assert p.title == "BlockContainer Engine"
    assert p.page_type == "domain_concept"


def test_with_summary_creates_new_instance():
    p = ConceptPage.from_title("X")
    p2 = p.with_summary("a new summary")
    assert p.summary == ""
    assert p2.summary == "a new summary"


def test_add_linked_entry_dedup():
    p = ConceptPage.from_title("X")
    p2 = p.add_linked_entry("e1").add_linked_entry("e1").add_linked_entry("e2")
    assert p2.linked_entry_ids == ["e1", "e2"]


def test_add_linked_concept_dedup():
    p = ConceptPage.from_title("X")
    p2 = p.add_linked_concept("c1").add_linked_concept("c1")
    assert p2.linked_concept_ids == ["c1"]


def test_update_surprise_stats():
    p = ConceptPage.from_title("X")
    p = p.update_surprise(0.2).update_surprise(0.4).update_surprise(0.6)
    assert p.surprise_stats["n"] == 3
    assert p.surprise_stats["mean"] > 0.39


def test_markdown_contains_title_and_summary():
    p = ConceptPage.from_title("Hello", summary="World content").add_linked_concept("link-a")
    md = p.to_markdown()
    assert "# Hello" in md
    assert "World content" in md
    assert "[[link-a]]" in md


def test_repo_upsert_and_get(repo):
    p = ConceptPage.from_title("MemoryConcept", summary="x", provenance=_prov())
    repo.upsert(p)
    got = repo.get(p.concept_id)
    assert got is not None
    assert got.title == "MemoryConcept"


def test_repo_upsert_writes_markdown(repo, tmp_path):
    p = ConceptPage.from_title("MemoryConcept", summary="x")
    repo.upsert(p)
    assert (repo.wiki_dir / f"{p.concept_id}.md").exists()


def test_repo_upsert_skip_markdown(repo):
    p = ConceptPage.from_title("NoMd", summary="x")
    repo.upsert(p, export_markdown=False)
    assert not (repo.wiki_dir / f"{p.concept_id}.md").exists()


def test_repo_upsert_overwrites_existing(repo):
    p = ConceptPage.from_title("Same", summary="v1")
    repo.upsert(p)
    p2 = p.with_summary("v2")
    repo.upsert(p2)
    got = repo.get(p.concept_id)
    assert got is not None
    assert got.summary == "v2"


def test_repo_list_filters_to_concept_nodes(repo):
    repo.upsert(ConceptPage.from_title("A"))
    repo.upsert(ConceptPage.from_title("B"))
    # Also create a non-concept node directly
    repo.structural.add_node("semantic", payload={"x": 1})
    pages = repo.list_all()
    assert {p.concept_id for p in pages} == {"a", "b"}


def test_repo_link_concept(repo):
    repo.upsert(ConceptPage.from_title("A"))
    repo.upsert(ConceptPage.from_title("B"))
    repo.link_concept("a", "b", weight=0.7)
    neighbors = repo.structural.query_neighbors("a", rel_type="linked_concept", direction="out")
    assert {n.id for n in neighbors} == {"b"}


def test_repo_link_entry(repo):
    repo.upsert(ConceptPage.from_title("Concept1"))
    repo.link_entry("concept1", "entry_xyz")
    got = repo.get("concept1")
    assert got is not None
    assert "entry_xyz" in got.linked_entry_ids


def test_repo_link_entry_unknown_concept(repo):
    with pytest.raises(KeyError):
        repo.link_entry("does-not-exist", "e1")


def test_repo_get_returns_none_for_unknown(repo):
    assert repo.get("ghost") is None
