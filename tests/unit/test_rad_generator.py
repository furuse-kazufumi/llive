# SPDX-License-Identifier: Apache-2.0
"""TRIZ-04 RAD-Backed Idea Generator tests."""

from __future__ import annotations

import json

import pytest

from llive.triz.contradiction import Contradiction
from llive.triz.loader import Principle
from llive.triz.principle_mapper import PrincipleRecommendation
from llive.triz.rad_generator import (
    RadBackedIdeaGenerator,
    RadCorpusLookup,
    RadEvidence,
    TemplateIdeaLLM,
    candidate_to_json,
)


def _contra() -> Contradiction:
    return Contradiction(
        contradiction_id="c1",
        improve_metric="m1",
        degrade_metric="m2",
        improve_feature_id=9,
        degrade_feature_id=13,
        severity=0.6,
        evidence={},
    )


def _rec(pid: int = 19) -> PrincipleRecommendation:
    return PrincipleRecommendation(
        principle=Principle(id=pid, name=f"Principle{pid}"),
        score=1.0,
        rank=1,
    )


def test_template_llm_emits_insert_skeleton():
    gen = TemplateIdeaLLM()
    out = gen.generate(_contra(), _rec(19), container_id="t_v1")
    assert out["container_id"] == "t_v1"
    assert "changes" in out
    assert out["changes"][0]["target_container"] == "t_v1"
    assert out["changes"][0]["action"] == "insert_subblock"


def test_template_llm_unknown_principle_uses_fallback():
    gen = TemplateIdeaLLM(fallback_principle_id=1)
    out = gen.generate(_contra(), _rec(999), container_id="t_v1")
    # principle 1 template is replace_subblock
    assert out["changes"][0]["action"] == "replace_subblock"


def test_corpus_lookup_no_dir_returns_empty(tmp_path):
    # point to a nonexistent dir
    c = RadCorpusLookup(base_dir=tmp_path / "missing")
    assert c.lookup(19) == []


def test_corpus_lookup_finds_index(tmp_path):
    domain_dir = tmp_path / "memory_systems"
    domain_dir.mkdir()
    (domain_dir / "INDEX.md").write_text(
        "# memory_systems\n\nrelated: principle 19 / consolidation replay\n",
        encoding="utf-8",
    )
    lookup = RadCorpusLookup(base_dir=tmp_path)
    evidence = lookup.lookup(19)
    assert len(evidence) >= 1
    assert evidence[0].domain == "memory_systems"
    assert evidence[0].relevance >= 0.6


def test_rad_backed_generator_end_to_end(tmp_path):
    lookup = RadCorpusLookup(base_dir=tmp_path / "missing")
    gen = RadBackedIdeaGenerator(llm=TemplateIdeaLLM(), corpus=lookup)
    out = gen.generate(_contra(), _rec(19), container_id="t_v1")
    assert out.candidate_id.startswith("cand_")
    assert out.principle_id == 19
    assert out.contradiction_id == "c1"


def test_candidate_to_json_round_trip():
    gen = RadBackedIdeaGenerator(corpus=RadCorpusLookup(base_dir=None))
    out = gen.generate(_contra(), _rec(19), container_id="t_v1")
    payload = json.loads(candidate_to_json(out))
    assert payload["mutation_metadata"]["policy"] == "triz_inspired"
    assert payload["mutation_metadata"]["applied_principle"]["id"] == 19
    assert payload["mutation_metadata"]["contradiction_id"] == "c1"


def test_evidence_dataclass_immutable():
    from dataclasses import FrozenInstanceError

    e = RadEvidence(domain="d", cluster="c", relevance=0.7)
    with pytest.raises(FrozenInstanceError):
        e.domain = "x"  # type: ignore[misc]


def test_max_hits_caps_results(tmp_path):
    for d in ("memory_systems", "neural_signal", "bci"):
        (tmp_path / d).mkdir()
        (tmp_path / d / "INDEX.md").write_text("principle 19", encoding="utf-8")
    lookup = RadCorpusLookup(base_dir=tmp_path, max_hits=2)
    out = lookup.lookup(19)
    assert len(out) <= 2
