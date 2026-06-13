# SPDX-License-Identifier: Apache-2.0
"""Smoke + contract tests for ``llive.genome.persona_loader``.

Covers Phase 1 sample personas (oka_kiyoshi / grothendieck / feynman / knuth /
kaneko_isamu) and the public Loader API. Will keep passing as Phase 2 adds
more personas via Perplexity (no per-persona assertions baked in).
"""
from __future__ import annotations

import pytest

from llive.genome.persona_loader import (
    PersonaPrompt,
    PersonaPromptLibrary,
    PersonaPromptValidationError,
    parse_persona_file,
)


@pytest.fixture(scope="module")
def lib() -> PersonaPromptLibrary:
    return PersonaPromptLibrary()


class TestDiscovery:
    def test_phase1_samples_discoverable(self, lib):
        ids = set(lib.discover())
        for required in ("oka_kiyoshi", "grothendieck", "feynman",
                         "knuth", "kaneko_isamu"):
            assert required in ids, f"Phase 1 sample missing: {required}"

    def test_len_matches_discover(self, lib):
        assert len(lib) == len(lib.discover())

    def test_contains_operator(self, lib):
        assert "oka_kiyoshi" in lib
        assert "this_persona_does_not_exist" not in lib


class TestGet:
    def test_returns_persona_prompt(self, lib):
        p = lib.get("oka_kiyoshi")
        assert isinstance(p, PersonaPrompt)
        assert p.id == "oka_kiyoshi"
        assert "岡潔" in p.display_name

    def test_caching(self, lib):
        a = lib.get("knuth")
        b = lib.get("knuth")
        assert a is b  # same instance from cache

    def test_unknown_id_raises_keyerror(self, lib):
        with pytest.raises(KeyError):
            lib.get("never_exists_12345")


class TestParsedFields:
    def test_required_fields_populated(self, lib):
        for pid in ("oka_kiyoshi", "grothendieck", "feynman",
                    "knuth", "kaneko_isamu"):
            p = lib.get(pid)
            assert p.display_name
            assert p.era
            assert p.fields, f"{pid}: fields must not be empty"
            assert p.nationality
            assert 100 <= len(p.style_text) <= 5000, \
                f"{pid}: style_text length out of range ({len(p.style_text)})"
            assert p.strengths, f"{pid}: strengths bullets parsed empty"
            assert p.weaknesses, f"{pid}: weaknesses bullets parsed empty"
            assert 30 <= len(p.prompt_text) <= 2000, \
                f"{pid}: prompt_text length out of range ({len(p.prompt_text)})"
            assert len(p.sources) >= 2, f"{pid}: needs >=2 sources"


class TestCompose:
    def test_compose_single(self, lib):
        composed = lib.compose(["feynman"])
        assert "Feynman" in composed or "ファインマン" in composed
        assert len(composed) > 50

    def test_compose_multi(self, lib):
        composed = lib.compose(["oka_kiyoshi", "grothendieck"])
        # Both persona texts should appear
        assert "岡潔" in composed
        assert "グロタンディーク" in composed
        # Markdown structure: 2 ### headers
        assert composed.count("### ") == 2

    def test_density_zero_short_form(self, lib):
        short = lib.compose(["feynman"], density=0.0)
        # density=0 → just display_name + fields list line
        assert len(short) < 100
        assert "Feynman" in short or "ファインマン" in short

    def test_density_partial_shorter_than_full(self, lib):
        full = lib.compose(["knuth"], density=1.0)
        partial = lib.compose(["knuth"], density=0.5)
        assert len(partial) < len(full)

    def test_max_chars_truncation(self, lib):
        composed = lib.compose(
            ["oka_kiyoshi", "grothendieck", "feynman"],
            max_chars=200,
        )
        assert len(composed) <= 200


class TestByField:
    def test_mathematics_field(self, lib):
        maths = lib.by_field("mathematics")
        ids = {p.id for p in maths}
        assert "oka_kiyoshi" in ids
        assert "grothendieck" in ids

    def test_unknown_field_empty(self, lib):
        assert lib.by_field("astrology_not_a_field") == []


class TestRandomSample:
    def test_n_capped_by_pool(self, lib):
        # asking for more than exists returns the full pool size
        sample = lib.random_sample(10_000)
        assert len(sample) == len(lib)

    def test_field_filter(self, lib):
        sample = lib.random_sample(5, fields=["mathematics"])
        for p in sample:
            assert "mathematics" in p.fields

    def test_deterministic_with_seeded_rng(self, lib):
        import random
        seed = 42
        a = [p.id for p in lib.random_sample(3, rng=random.Random(seed))]
        b = [p.id for p in lib.random_sample(3, rng=random.Random(seed))]
        assert a == b


class TestValidation:
    def test_phase1_samples_valid(self, lib):
        # Re-parsing via parse_persona_file directly should not raise
        for pid in ("oka_kiyoshi", "grothendieck", "feynman",
                    "knuth", "kaneko_isamu"):
            path = lib._paths[pid]  # noqa: SLF001 — test
            parsed = parse_persona_file(path)
            assert parsed.id == pid

    def test_validation_error_class(self):
        # PersonaPromptValidationError should be ValueError-derived
        assert issubclass(PersonaPromptValidationError, ValueError)
