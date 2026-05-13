"""Extra coverage for consolidation.py — _apply_decision branches + mock LLM."""

from __future__ import annotations

import pytest

from llive.memory.concept import ConceptPage, ConceptPageRepo
from llive.memory.consolidation import (
    CompileDecision,
    Consolidator,
    ConsolidatorConfig,
    MockCompileLLM,
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
    c = Consolidator(
        episodic=ep, structural=sm,
        config=ConsolidatorConfig(sample_size=20, cluster_min_size=2, cluster_similarity_threshold=0.22),
    )
    yield c
    ep.close()
    sm.close()


def _ev(ep, content):
    ep.write(EpisodicEvent(content=content, provenance=Provenance(source_type="test", source_id="t")))


def test_mock_llm_picks_update_when_slug_matches():
    page = ConceptPage.from_title("Hello world greeting", summary="x")
    decision = MockCompileLLM()(["Hello world greeting"], [page])
    assert decision.action == "update"
    assert decision.target_concept_id == page.concept_id


def test_max_calls_per_cycle_short_circuit(cons):
    """When max_calls_per_cycle is 0, the first cluster is skipped."""
    cons.config.max_calls_per_cycle = 0
    for t in ["alpha alpha alpha", "alpha beta gamma", "delta delta delta", "delta epsilon zeta"]:
        _ev(cons.episodic, t)
    result = cons.run_once()
    assert any("max_calls_per_cycle" in e for e in result.errors)


def test_apply_decision_update_path(cons):
    repo: ConceptPageRepo = cons.repo
    existing = ConceptPage.from_title("Update Target", summary="v1")
    repo.upsert(existing)

    class _UpdateLLM(MockCompileLLM):
        def __call__(self, cluster_texts, existing_pages):
            return CompileDecision(
                action="update",
                title="Update Target",
                summary="v2",
                target_concept_id=existing.concept_id,
            )

    cons.llm = _UpdateLLM()
    for t in ["first event content", "second event content"]:
        _ev(cons.episodic, t)
    cons.run_once()
    got = repo.get(existing.concept_id)
    assert got is not None
    assert got.summary == "v2"


def test_apply_decision_merge_path(cons):
    """Merge with high evidence overlap should land in the merge branch."""
    repo: ConceptPageRepo = cons.repo
    existing = ConceptPage.from_title("merge-target", summary="x")
    # high overlap → keep the merge decision
    shared_ids = ["evt_shared_a", "evt_shared_b"]
    existing = existing.model_copy(update={"linked_entry_ids": shared_ids})
    repo.upsert(existing)

    class _MergeLLM(MockCompileLLM):
        def __call__(self, cluster_texts, existing_pages):
            return CompileDecision(
                action="merge",
                title="merge-target",
                summary="merged content",
                target_concept_id="merge-target",
                merged_concept_ids=["merge-target"],
            )

    # Need to seed episodic events with IDs that overlap with the existing page.
    from llive.memory.episodic import EpisodicEvent

    for content, eid in zip(("merge ev a", "merge ev b"), shared_ids, strict=True):
        cons.episodic.write(
            EpisodicEvent(
                content=content,
                provenance=Provenance(source_type="t", source_id="t"),
                event_id=eid,
            )
        )
    cons.llm = _MergeLLM()
    cons.run_once()
    target = repo.get("merge-target")
    assert target is not None
    # summary should be replaced
    assert target.summary == "merged content"


def test_apply_decision_returns_none_when_no_events():
    """_apply_decision is internal but defensive against empty event lists."""
    import os

    # Manually call with no events — should return None
    import tempfile

    from llive.memory.consolidation import Consolidator
    os.environ["LLIVE_DATA_DIR"] = tempfile.mkdtemp()
    ep = EpisodicMemory()
    sm = StructuralMemory()
    try:
        cons = Consolidator(episodic=ep, structural=sm)
        decision = CompileDecision(action="new", title="x", summary="x")
        page = cons._apply_decision(decision, [], existing_pages=[])
        assert page is None
    finally:
        ep.close(); sm.close()


def test_cycle_with_empty_episodic_returns_zero(cons):
    result = cons.run_once()
    assert result.sampled == 0
    assert result.clusters == 0
