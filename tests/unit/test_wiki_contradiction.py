# SPDX-License-Identifier: Apache-2.0
"""LLW-04 Wiki Contradiction Detector tests."""

from __future__ import annotations

from llive.memory.concept import ConceptPage
from llive.memory.provenance import Provenance
from llive.wiki.contradiction import detect_wiki_contradictions


def test_no_contradiction_on_clean_page():
    page = ConceptPage.from_title("Test")
    assert detect_wiki_contradictions(page) == []


def test_provenance_duplicate_source_detected():
    p = ConceptPage.from_title(
        "X",
        provenance=Provenance(
            source_type="t",
            source_id="t",
            derived_from=["src_a", "src_a", "src_b"],
        ),
    )
    out = detect_wiki_contradictions(p)
    assert len(out) >= 1
    assert out[0].kind == "provenance"
    assert "src_a" in out[0].description


def test_edge_duplicate_slug_detected():
    page = ConceptPage.from_title("X")
    page = page.add_linked_concept("y")
    page = page.add_linked_concept("z")
    # forcibly inject a duplicate to simulate stale merge
    page = page.model_copy(update={"linked_concept_ids": ["y", "z", "y"]})
    out = detect_wiki_contradictions(page)
    assert any(c.kind == "edge" and "y" in c.description for c in out)


def test_statement_annotation_detected():
    page = ConceptPage.from_title(
        "X",
        provenance=None,
        contradicts=[{"description": "X enables Y but also prevents Y", "severity": 0.85}],
    )
    out = detect_wiki_contradictions(page)
    statements = [c for c in out if c.kind == "statement"]
    assert len(statements) == 1
    assert statements[0].severity == 0.85


def test_severity_sorted_descending():
    page = ConceptPage.from_title("X")
    page = page.model_copy(
        update={
            "structured_fields": {
                "contradicts": [
                    {"description": "weak", "severity": 0.2},
                    {"description": "strong", "severity": 0.9},
                ]
            }
        }
    )
    out = detect_wiki_contradictions(page)
    assert out[0].severity >= out[-1].severity


def test_severity_clipped_to_unit_interval():
    page = ConceptPage.from_title(
        "X",
        contradicts=[{"description": "extreme", "severity": 5.0}],
    )
    out = detect_wiki_contradictions(page)
    assert all(0.0 <= c.severity <= 1.0 for c in out)


def test_multiple_contradiction_kinds_detected_simultaneously():
    page = ConceptPage.from_title(
        "X",
        provenance=Provenance(
            source_type="t",
            source_id="t",
            derived_from=["src", "src"],
        ),
        contradicts=[{"description": "explicit", "severity": 0.7}],
    )
    page = page.model_copy(update={"linked_concept_ids": ["a", "a"]})
    out = detect_wiki_contradictions(page)
    kinds = {c.kind for c in out}
    assert kinds == {"provenance", "edge", "statement"}
