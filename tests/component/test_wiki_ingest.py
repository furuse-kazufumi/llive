"""LLW-06: WikiIngestor."""

from __future__ import annotations

import pytest

from llive.memory.episodic import EpisodicMemory
from llive.wiki.ingest import WikiIngestor, _chunk_markdown, _chunk_text


@pytest.fixture
def ep(tmp_path):
    e = EpisodicMemory(db_path=tmp_path / "ep.duckdb")
    yield e
    e.close()


def test_chunk_text_single():
    chunks = _chunk_text("short text")
    assert chunks == ["short text"]


def test_chunk_text_paragraph_split():
    text = "para 1\n\npara 2\n\npara 3"
    chunks = _chunk_text(text, max_chars=10)
    assert len(chunks) == 3


def test_chunk_text_empty():
    assert _chunk_text("") == []
    assert _chunk_text("   \n   ") == []


def test_chunk_text_oversize_hard_split():
    text = "a" * 2500
    chunks = _chunk_text(text, max_chars=1000)
    assert all(len(c) <= 1000 for c in chunks)
    assert sum(len(c) for c in chunks) == 2500


def test_chunk_markdown_heading_split():
    md = "# Intro\n\nbody\n\n## A\n\nsec a\n\n## B\n\nsec b"
    chunks = _chunk_markdown(md)
    assert len(chunks) == 3
    assert all("#" in c for c in chunks)


def test_ingest_text_writes_to_episodic(ep, tmp_path):
    f = tmp_path / "doc.txt"
    f.write_text("a paragraph\n\nanother", encoding="utf-8")
    r = WikiIngestor(ep).ingest(str(f), "text", chunk_chars=10)
    assert r.n_chunks >= 1
    assert ep.count() == r.n_chunks


def test_ingest_markdown(ep, tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("# Title\n\nbody\n\n## Sub\n\nsubbody", encoding="utf-8")
    r = WikiIngestor(ep).ingest(str(md), "markdown")
    assert r.n_chunks >= 1
    events = ep.query_recent(limit=10)
    # provenance.source_id should be set
    assert events[0].provenance.source_type == "imported"


def test_ingest_unknown_type(ep, tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        WikiIngestor(ep).ingest(str(f), "no-such-type")
