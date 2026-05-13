"""MEM-08 / LLW-02: Consolidator end-to-end with mock LLM."""

from __future__ import annotations

import numpy as np
import pytest

from llive.memory.concept import ConceptPageRepo
from llive.memory.consolidation import (
    CompileDecision,
    Consolidator,
    ConsolidatorConfig,
    MockCompileLLM,
    _greedy_clusters,
    _select_llm,
)
from llive.memory.episodic import EpisodicEvent, EpisodicMemory
from llive.memory.provenance import Provenance
from llive.memory.structural import StructuralMemory


@pytest.fixture(autouse=True)
def _force_mock(monkeypatch):
    monkeypatch.setenv("LLIVE_CONSOLIDATOR_MOCK", "1")


@pytest.fixture
def cons(tmp_path):
    ep = EpisodicMemory(db_path=tmp_path / "ep.duckdb")
    sm = StructuralMemory(db_path=tmp_path / "s.kuzu")
    cfg = ConsolidatorConfig(sample_size=20, cluster_min_size=2, cluster_similarity_threshold=0.22)
    c = Consolidator(episodic=ep, structural=sm, config=cfg)
    yield c
    ep.close()
    sm.close()


def _ev(ep, content):
    ep.write(EpisodicEvent(content=content, provenance=Provenance(source_type="test", source_id="t")))


def test_empty_episodic_yields_empty_result(cons):
    result = cons.run_once()
    assert result.sampled == 0
    assert result.clusters == 0


def test_cycle_creates_pages(cons):
    for t in [
        "memory consolidation reduces forgetting through replay",
        "memory consolidation cycles strengthen long-term storage",
        "router selection depends on prompt task tag",
        "router rules in YAML define container selection",
    ]:
        _ev(cons.episodic, t)
    result = cons.run_once()
    assert result.sampled == 4
    assert result.clusters >= 1
    assert result.pages_created >= 1


def test_provenance_anchored_to_raw_events(cons):
    for t in ["alpha alpha alpha", "alpha beta alpha"]:
        _ev(cons.episodic, t)
    cons.run_once()
    pages = cons.repo.list_all()
    for p in pages:
        assert p.provenance is not None
        assert p.provenance.derived_from  # LLW-AC-01 — never empty
        # all derived_from ids must look like UUIDs (32 chars hex)
        for src in p.provenance.derived_from:
            assert len(src) == 32


def test_one_pass_guarantee_no_chain(cons):
    # During a single cycle, new pages should not feed back as input.
    # We test by checking: with 2 clusters, the second cluster's LLM call
    # only sees pre-cycle pages (= 0 in this fresh repo).
    seen_existing_counts: list[int] = []

    class _SpyLLM(MockCompileLLM):
        def __call__(self, cluster_texts, existing_pages):
            seen_existing_counts.append(len(existing_pages))
            return super().__call__(cluster_texts, existing_pages)

    cons.llm = _SpyLLM()
    # Two well-separated topics so the greedy clusterer forms two groups.
    for t in [
        "memory consolidation runs nightly to compress data",
        "memory consolidation reduces forgetting through replay",
        "memory consolidation cycles strengthen long-term storage",
        "router selection depends on prompt task tag",
        "router rules in YAML define container selection",
        "router fallback to adaptive when no rule matches",
    ]:
        _ev(cons.episodic, t)
    cons.run_once()
    # Both clusters should have seen the same (pre-cycle) existing pages count.
    # The cluster count depends on the embedding back-end; require at least 2.
    assert len(seen_existing_counts) >= 2
    assert all(c == seen_existing_counts[0] for c in seen_existing_counts)


def test_enforce_diversity_downgrades_merge(cons):
    page_repo: ConceptPageRepo = cons.repo
    # Pre-create a page with its own entry set
    from llive.memory.concept import ConceptPage

    existing = ConceptPage.from_title("existing", summary="x")
    existing = existing.model_copy(update={"linked_entry_ids": ["old_event_1", "old_event_2"]})
    page_repo.upsert(existing)

    # Force the LLM to want a merge
    class _MergeLLM(MockCompileLLM):
        def __call__(self, cluster_texts, existing_pages):
            return CompileDecision(
                action="merge",
                title="new",
                summary="merged",
                target_concept_id="existing",
                merged_concept_ids=["existing"],
            )

    cons.llm = _MergeLLM()
    for t in ["fresh content one", "fresh content two"]:
        _ev(cons.episodic, t)
    result = cons.run_once()
    # Because the new events have NO overlap with old_event_1/2, merge should be downgraded
    actions = [d.action for d in result.decisions]
    assert "new" in actions  # merge converted to new
    # the existing page should remain untouched apart from its own state
    still = page_repo.get("existing")
    assert still is not None
    assert "old_event_1" in still.linked_entry_ids


def test_select_llm_returns_mock_under_env(monkeypatch):
    monkeypatch.setenv("LLIVE_CONSOLIDATOR_MOCK", "1")
    llm = _select_llm("claude-haiku-foo")
    assert isinstance(llm, MockCompileLLM)


def test_select_llm_without_key_returns_mock(monkeypatch):
    monkeypatch.delenv("LLIVE_CONSOLIDATOR_MOCK", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    llm = _select_llm("any")
    assert isinstance(llm, MockCompileLLM)


def test_greedy_clusters_filters_small():
    emb = np.eye(5, dtype=np.float32)
    clusters = _greedy_clusters(emb, similarity_threshold=0.99, min_size=2)
    assert clusters == []


def test_greedy_clusters_groups_similar():
    base = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    arr = np.stack([base, base + 0.01, base + 0.02, np.array([0.0, 1.0, 0.0])])
    clusters = _greedy_clusters(arr, similarity_threshold=0.95, min_size=2)
    assert len(clusters) == 1
    assert len(clusters[0]) == 3
