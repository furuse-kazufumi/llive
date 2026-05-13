"""Extra coverage for memory/semantic.py persistence and edge paths."""

from __future__ import annotations

import numpy as np
import pytest

from llive.memory.encoder import MemoryEncoder
from llive.memory.provenance import Provenance
from llive.memory.semantic import SemanticHit, SemanticMemory


def test_write_wrong_dim_raises():
    sm = SemanticMemory(dim=8, use_faiss=False)
    with pytest.raises(ValueError):
        sm.write("x", np.zeros(7), Provenance(source_type="t", source_id="1"))


def test_query_wrong_dim_raises():
    sm = SemanticMemory(dim=8, use_faiss=False)
    sm.write("x", np.zeros(8), Provenance(source_type="t", source_id="1"))
    with pytest.raises(ValueError):
        sm.query(np.zeros(7), top_k=1)


def test_query_on_empty_returns_empty():
    sm = SemanticMemory(dim=4, use_faiss=False)
    assert sm.query(np.zeros(4), top_k=5) == []


def test_clear_resets_state():
    enc = MemoryEncoder(prefer_fallback=True)
    sm = SemanticMemory(dim=enc.dim, use_faiss=False)
    sm.write("alpha", enc.encode("alpha"), Provenance(source_type="t", source_id="1"))
    assert len(sm) == 1
    sm.clear()
    assert len(sm) == 0
    assert sm.query(enc.encode("alpha"), top_k=1) == []


def test_save_and_load_roundtrip(tmp_path):
    enc = MemoryEncoder(prefer_fallback=True)
    sm = SemanticMemory(dim=enc.dim, data_dir=tmp_path / "sem", use_faiss=False)
    prov = Provenance(source_type="t", source_id="1")
    for word in ["alpha", "beta", "gamma"]:
        sm.write(word, enc.encode(word), prov)
    sm.save()

    sm2 = SemanticMemory(dim=enc.dim, data_dir=tmp_path / "sem", use_faiss=False)
    sm2.load()
    assert len(sm2) == 3
    hits = sm2.query(enc.encode("alpha"), top_k=1)
    assert isinstance(hits[0], SemanticHit)
    assert hits[0].content == "alpha"


def test_load_with_no_file_is_noop(tmp_path):
    sm = SemanticMemory(dim=4, data_dir=tmp_path / "nope", use_faiss=False)
    sm.load()  # should silently do nothing
    assert len(sm) == 0


def test_all_embeddings_empty():
    sm = SemanticMemory(dim=4, use_faiss=False)
    arr = sm.all_embeddings()
    assert arr.shape == (0, 4)


def test_all_embeddings_after_writes():
    enc = MemoryEncoder(prefer_fallback=True)
    sm = SemanticMemory(dim=enc.dim, use_faiss=False)
    prov = Provenance(source_type="t", source_id="1")
    sm.write("a", enc.encode("a"), prov)
    sm.write("b", enc.encode("b"), prov)
    arr = sm.all_embeddings()
    assert arr.shape == (2, enc.dim)
