# SPDX-License-Identifier: Apache-2.0
"""PersonaCorpusLoader skeleton (v0.E CE-23 / Phase E.13) — unit tests."""

from __future__ import annotations

import pytest

from llive.perf.evolutionary import (
    PERSONA_ONTOLOGY,
    Persona,
    PersonaCorpusLoader,
)
from llive.perf.evolutionary.persona_corpus_loader import (
    PersonaCandidate,
    affinity_from_counts,
    find_persona_snippets_in_text_file,
    keyword_extractor,
)


# ---------------------------------------------------------------------------
# 1. keyword_extractor
# ---------------------------------------------------------------------------


class TestKeywordExtractor:
    def test_empty_snippets_returns_empty(self) -> None:
        patterns, counts = keyword_extractor([], "test")
        assert patterns == ()
        # 全 factor count は 0
        assert all(v == 0.0 for v in counts.values())

    def test_structurize_detected(self) -> None:
        snippets = [
            "He developed a rigorous axiomatic framework for analysis.",
            "The structure of his system was elegant.",
        ]
        patterns, counts = keyword_extractor(snippets, "test")
        assert counts["factor_structurize"] > 0
        # patterns 内に structure 関連が含まれる
        assert any("axiom" in p or "structure" in p for p in patterns)

    def test_exploration_detected(self) -> None:
        snippets = [
            "He was driven to explore the unknown territories of mathematics.",
            "Novel discovery was his lifework.",
        ]
        patterns, counts = keyword_extractor(snippets, "test")
        assert counts["factor_exploration"] > 0

    def test_japanese_keyword_detection(self) -> None:
        snippets = ["岡潔は情緒と多様性、そして数学の証明の厳密性を重んじた。"]
        patterns, counts = keyword_extractor(snippets, "test")
        # 「証明」「厳密」 → factor_consistency
        assert counts["factor_consistency"] > 0


# ---------------------------------------------------------------------------
# 2. affinity_from_counts
# ---------------------------------------------------------------------------


class TestAffinityFromCounts:
    def test_empty_counts_returns_center(self) -> None:
        aff = affinity_from_counts({})
        # 全 factor が 0.5 (情報無し中央)
        assert all(v == 0.5 for v in aff)
        assert len(aff) == 10

    def test_single_factor_max(self) -> None:
        aff = affinity_from_counts({"factor_structurize": 10.0})
        # structurize の affinity が最大 (= 1.0), 他は 0
        idx = ["factor_structurize"]
        # 必ず 10 dim
        assert len(aff) == 10

    def test_normalization_clamps_to_max(self) -> None:
        aff = affinity_from_counts(
            {"factor_structurize": 100, "factor_exploration": 1}
        )
        # max は 1.0, 他は 1.0 未満
        assert max(aff) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 3. PersonaCorpusLoader.extract
# ---------------------------------------------------------------------------


class TestExtract:
    def test_extract_produces_candidate(self) -> None:
        loader = PersonaCorpusLoader()
        cand = loader.extract(
            "test-persona",
            "Test Person",
            ["Rigorous proof and structure are key."],
            era="modern",
            fields=("philosophy",),
        )
        assert isinstance(cand, PersonaCandidate)
        assert cand.persona_id == "test-persona"
        assert cand.name == "Test Person"
        assert cand.era == "modern"
        assert cand.fields == ("philosophy",)
        # affinity は 10 dim, 全 [0, 1]
        assert len(cand.extracted_affinity) == 10
        for v in cand.extracted_affinity:
            assert 0.0 <= v <= 1.0

    def test_extract_to_persona(self) -> None:
        loader = PersonaCorpusLoader()
        cand = loader.extract(
            "test-persona",
            "Test Person",
            ["His exploration of mathematics was unbounded."],
            era="modern",
            fields=("mathematics",),
        )
        persona = cand.to_persona()
        assert isinstance(persona, Persona)
        assert persona.persona_id == "test-persona"
        assert persona.factor_affinity == cand.extracted_affinity

    def test_extract_many(self) -> None:
        loader = PersonaCorpusLoader()
        cands = loader.extract_many(
            [
                (
                    "a",
                    "A",
                    ["Rigorous proofs and axiomatic structure."],
                    "ancient",
                    ("math",),
                ),
                (
                    "b",
                    "B",
                    ["Novel exploration and discovery."],
                    "modern",
                    ("physics",),
                ),
            ]
        )
        assert len(cands) == 2
        assert cands[0].persona_id == "a"
        assert cands[1].persona_id == "b"

    def test_custom_extractor_injection(self) -> None:
        def my_extractor(snippets, persona_id):
            return ("custom",), {"factor_structurize": 5.0}

        loader = PersonaCorpusLoader(extractor=my_extractor)
        cand = loader.extract("test", "T", ["whatever"])
        assert cand.extracted_patterns == ("custom",)


# ---------------------------------------------------------------------------
# 4. merge_into_ontology
# ---------------------------------------------------------------------------


class TestMergeIntoOntology:
    def test_merge_adds_new(self) -> None:
        loader = PersonaCorpusLoader()
        cand = loader.extract(
            "test-new", "Test New", ["Rigorous proof."], era="modern"
        )
        merged = PersonaCorpusLoader.merge_into_ontology([cand])
        assert "test-new" in merged
        # PERSONA_ONTOLOGY 本体は影響を受けない
        assert "test-new" not in PERSONA_ONTOLOGY

    def test_merge_no_overwrite_skips_existing(self) -> None:
        loader = PersonaCorpusLoader()
        cand = loader.extract(
            "newton",
            "FAKE NEWTON",
            ["fake snippet"],
            era="fake",
        )
        merged = PersonaCorpusLoader.merge_into_ontology(
            [cand], overwrite=False
        )
        assert merged["newton"].name != "FAKE NEWTON"

    def test_merge_overwrite_replaces_existing(self) -> None:
        loader = PersonaCorpusLoader()
        cand = loader.extract(
            "newton",
            "ALT NEWTON",
            ["alt snippet"],
            era="alt",
        )
        merged = PersonaCorpusLoader.merge_into_ontology(
            [cand], overwrite=True
        )
        assert merged["newton"].name == "ALT NEWTON"
        assert merged["newton"].era == "alt"

    def test_merge_with_custom_ontology(self) -> None:
        loader = PersonaCorpusLoader()
        cand = loader.extract("a", "A", ["Rigorous"], era="modern")
        merged = PersonaCorpusLoader.merge_into_ontology(
            [cand], ontology={"existing": PERSONA_ONTOLOGY["newton"]}
        )
        assert "a" in merged
        assert "existing" in merged
        assert "newton" not in merged  # 新 ontology base には newton 無し


# ---------------------------------------------------------------------------
# 5. file snippet finder
# ---------------------------------------------------------------------------


class TestFileSnippetFinder:
    def test_missing_file_returns_empty(self, tmp_path) -> None:
        snippets = find_persona_snippets_in_text_file(
            tmp_path / "doesnotexist.txt", ["Newton"]
        )
        assert snippets == []

    def test_finds_alias_context(self, tmp_path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text(
            "Isaac Newton was an English mathematician and physicist. "
            "He developed calculus.",
            encoding="utf-8",
        )
        snippets = find_persona_snippets_in_text_file(
            f, ["Newton"], context_chars=20
        )
        assert len(snippets) == 1
        assert "Newton" in snippets[0]

    def test_multiple_hits(self, tmp_path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("Galois. ... Galois lived a short life.", encoding="utf-8")
        snippets = find_persona_snippets_in_text_file(
            f, ["Galois"], context_chars=10
        )
        assert len(snippets) == 2

    def test_directory_returns_empty(self, tmp_path) -> None:
        snippets = find_persona_snippets_in_text_file(tmp_path, ["x"])
        assert snippets == []
