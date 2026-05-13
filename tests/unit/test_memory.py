"""MEM-01..04: semantic + episodic + provenance + surprise gate."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np

from llive.memory import (
    EpisodicEvent,
    EpisodicMemory,
    MemoryEncoder,
    Provenance,
    SemanticMemory,
    SurpriseGate,
)


def test_provenance_roundtrip():
    p = Provenance(
        source_type="user_input",
        source_id="abc",
        confidence=0.85,
        derived_from=["seed-1"],
    )
    txt = p.to_json()
    back = Provenance.from_json(txt)
    assert back.source_type == "user_input"
    assert back.confidence == 0.85
    assert back.derived_from == ["seed-1"]


def test_provenance_phase1_empty_signature_allowed():
    p = Provenance(source_type="t", source_id="i")
    assert p.signed_by == ""
    assert p.signature == ""


def test_semantic_memory_write_and_query():
    enc = MemoryEncoder(prefer_fallback=True)
    sm = SemanticMemory(dim=enc.dim, use_faiss=False)
    prov = Provenance(source_type="test", source_id="t1")

    sm.write("the quick brown fox", enc.encode("the quick brown fox"), prov)
    sm.write("hello world", enc.encode("hello world"), prov)
    sm.write("lazy dog jumps", enc.encode("lazy dog jumps"), prov)
    assert len(sm) == 3

    hits = sm.query(enc.encode("quick brown fox"), top_k=1)
    assert len(hits) == 1
    assert hits[0].content == "the quick brown fox"
    assert hits[0].provenance.source_type == "test"


def test_semantic_memory_persistence(tmp_path):
    enc = MemoryEncoder(prefer_fallback=True)
    sm = SemanticMemory(dim=enc.dim, data_dir=tmp_path / "sem", use_faiss=False)
    prov = Provenance(source_type="test", source_id="t1")
    sm.write("alpha beta", enc.encode("alpha beta"), prov)
    sm.write("gamma delta", enc.encode("gamma delta"), prov)
    sm.save()

    sm2 = SemanticMemory(dim=enc.dim, data_dir=tmp_path / "sem", use_faiss=False)
    sm2.load()
    assert len(sm2) == 2
    hits = sm2.query(enc.encode("alpha beta"), top_k=1)
    assert hits[0].content == "alpha beta"


def test_episodic_memory_write_and_recent(tmp_path):
    ep = EpisodicMemory(db_path=tmp_path / "ep.duckdb")
    try:
        prov = Provenance(source_type="test", source_id="t1")
        t_early = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        t_late = datetime(2026, 1, 2, 0, 0, 0, tzinfo=UTC)
        ep.write(EpisodicEvent(content="event A", provenance=prov, ts=t_early))
        ep.write(EpisodicEvent(content="event B", provenance=prov, ts=t_late))
        assert ep.count() == 2
        recent = ep.query_recent(limit=1)
        assert recent[0].content == "event B"
    finally:
        ep.close()


def test_episodic_memory_range(tmp_path):
    ep = EpisodicMemory(db_path=tmp_path / "ep.duckdb")
    try:
        prov = Provenance(source_type="test", source_id="t1")
        t0 = datetime(2026, 1, 1, tzinfo=UTC)
        t1 = datetime(2026, 1, 2, tzinfo=UTC)
        t2 = datetime(2026, 1, 3, tzinfo=UTC)
        ep.write(EpisodicEvent(content="A", provenance=prov, ts=t0))
        ep.write(EpisodicEvent(content="B", provenance=prov, ts=t1))
        ep.write(EpisodicEvent(content="C", provenance=prov, ts=t2))
        out = ep.query_range(start=t1, end=t2, limit=10)
        assert [e.content for e in out] == ["B", "C"]
    finally:
        ep.close()


def test_surprise_gate_empty_memory_writes():
    g = SurpriseGate(theta=0.3)
    new = np.array([1.0, 0.0, 0.0])
    s = g.compute_surprise(new, np.zeros((0, 3)))
    assert s == 1.0
    assert g.should_write(s)


def test_surprise_gate_near_duplicate_skips():
    g = SurpriseGate(theta=0.3)
    new = np.array([1.0, 0.0, 0.0])
    existing = np.array([[1.0, 0.0, 0.0]])
    s = g.compute_surprise(new, existing)
    assert s == 0.0
    assert not g.should_write(s)


def test_surprise_gate_distinct_writes():
    g = SurpriseGate(theta=0.3)
    new = np.array([0.0, 1.0, 0.0])
    existing = np.array([[1.0, 0.0, 0.0]])
    s = g.compute_surprise(new, existing)
    assert s == 1.0
    assert g.should_write(s)
