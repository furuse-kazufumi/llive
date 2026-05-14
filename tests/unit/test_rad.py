"""Phase B: RAD knowledge base — loader / query / append / skills."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from llive.memory.provenance import Provenance
from llive.memory.rad import RadCorpusIndex
from llive.memory.rad.append import append_learning
from llive.memory.rad.query import query
from llive.memory.rad.skills import detect_skill_index

# ---------------------------------------------------------------------------
# Fixtures: a synthetic RAD root with two domains + corpus2skill output
# ---------------------------------------------------------------------------


@pytest.fixture
def synth_root(tmp_path: Path) -> Path:
    root = tmp_path / "data" / "rad"
    root.mkdir(parents=True)

    # Domain 1: security_corpus_v2 with two docs
    sec = root / "security_corpus_v2"
    sec.mkdir()
    (sec / "buffer_overflow.md").write_text(
        "# Buffer Overflow\n\nClassic memory-safety bug where a write exceeds buffer bounds.\n",
        encoding="utf-8",
    )
    (sec / "race_conditions.md").write_text(
        "# Race conditions\n\nTOCTOU and similar threading hazards.\n",
        encoding="utf-8",
    )

    # Domain 2: llm_corpus_v2 with one doc + nested doc
    llm = root / "llm_corpus_v2"
    (llm / "papers").mkdir(parents=True)
    (llm / "papers" / "rlhf_overview.md").write_text(
        "# RLHF\n\nReinforcement learning from human feedback.\n",
        encoding="utf-8",
    )

    # corpus2skill output collocated with one domain
    (sec / "INDEX.md").write_text(
        "---\nname: corpus/security_corpus_v2\n---\n\n# security_corpus_v2 -- Skill Index\n\n## Cluster 1\n\n## Cluster 2\n",
        encoding="utf-8",
    )
    (sec / "metadata.json").write_text(
        json.dumps({"corpus_name": "security_corpus_v2", "doc_count": 2}),
        encoding="utf-8",
    )

    # _index.json
    (root / "_index.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source": "synthetic",
                "dest": str(root),
                "imported_at": "2026-05-15T00:00:00+00:00",
                "corpora": {
                    "security_corpus_v2": {
                        "file_count": 2,
                        "bytes": 200,
                        "imported_at": "2026-05-15T00:00:00+00:00",
                    },
                    "llm_corpus_v2": {
                        "file_count": 1,
                        "bytes": 50,
                        "imported_at": "2026-05-15T00:00:00+00:00",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return root


# ---------------------------------------------------------------------------
# loader
# ---------------------------------------------------------------------------


def test_root_resolution_explicit(tmp_path: Path) -> None:
    idx = RadCorpusIndex(root=tmp_path)
    assert idx.root == tmp_path.resolve()


def test_root_resolution_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LLIVE_RAD_DIR", str(tmp_path))
    idx = RadCorpusIndex()
    assert idx.root == tmp_path.resolve()


def test_root_resolution_raptor_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("LLIVE_RAD_DIR", raising=False)
    monkeypatch.setenv("RAPTOR_CORPUS_DIR", str(tmp_path))
    idx = RadCorpusIndex()
    assert idx.root == tmp_path.resolve()


def test_list_domains(synth_root: Path) -> None:
    idx = RadCorpusIndex(root=synth_root)
    domains = idx.list_domains()
    assert "security_corpus_v2" in domains
    assert "llm_corpus_v2" in domains
    # _learned not present yet -> not in the list
    assert not any(d.startswith("_learned/") for d in domains)


def test_has_domain_and_info(synth_root: Path) -> None:
    idx = RadCorpusIndex(root=synth_root)
    assert idx.has_domain("security_corpus_v2")
    info = idx.get_domain_info("security_corpus_v2")
    assert info is not None
    assert info.file_count == 2
    assert info.bytes == 200
    assert info.is_learned is False


def test_iter_documents(synth_root: Path) -> None:
    idx = RadCorpusIndex(root=synth_root)
    sec_docs = idx.iter_documents("security_corpus_v2")
    # 2 markdown + INDEX.md + metadata.json
    names = sorted(p.name for p in sec_docs)
    assert "buffer_overflow.md" in names
    assert "race_conditions.md" in names
    assert "INDEX.md" in names
    assert "metadata.json" in names


def test_read_document(synth_root: Path) -> None:
    idx = RadCorpusIndex(root=synth_root)
    text = idx.read_document("security_corpus_v2", "buffer_overflow.md")
    assert "Buffer Overflow" in text


def test_read_document_path_traversal_blocked(synth_root: Path) -> None:
    idx = RadCorpusIndex(root=synth_root)
    with pytest.raises(PermissionError):
        idx.read_document("security_corpus_v2", "../llm_corpus_v2/papers/rlhf_overview.md")


def test_read_document_unknown_domain(synth_root: Path) -> None:
    idx = RadCorpusIndex(root=synth_root)
    with pytest.raises(FileNotFoundError):
        idx.read_document("ghost_corpus", "x.md")


def test_reload_picks_up_new_dir(synth_root: Path) -> None:
    idx = RadCorpusIndex(root=synth_root)
    _ = idx.list_domains()  # populate cache
    new = synth_root / "fresh_corpus_v2"
    new.mkdir()
    (new / "doc.md").write_text("fresh")
    # cache stale
    assert not idx.has_domain("fresh_corpus_v2")
    idx.reload()
    assert idx.has_domain("fresh_corpus_v2")


# ---------------------------------------------------------------------------
# query
# ---------------------------------------------------------------------------


def test_query_filename_match(synth_root: Path) -> None:
    idx = RadCorpusIndex(root=synth_root)
    hits = query(idx, "buffer overflow")
    assert hits
    top = hits[0]
    assert top.domain == "security_corpus_v2"
    assert top.doc_path.name == "buffer_overflow.md"
    assert "buffer" in top.matched_terms
    assert "overflow" in top.matched_terms


def test_query_content_match(synth_root: Path) -> None:
    idx = RadCorpusIndex(root=synth_root)
    hits = query(idx, "RLHF")
    assert hits
    assert hits[0].doc_path.name == "rlhf_overview.md"


def test_query_domain_filter(synth_root: Path) -> None:
    idx = RadCorpusIndex(root=synth_root)
    hits = query(idx, "Reinforcement", domain="security_corpus_v2")
    assert hits == []
    hits2 = query(idx, "Reinforcement", domain="llm_corpus_v2")
    assert hits2


def test_query_domain_list(synth_root: Path) -> None:
    idx = RadCorpusIndex(root=synth_root)
    hits = query(idx, "race", domain=["security_corpus_v2"])
    assert any(h.doc_path.name == "race_conditions.md" for h in hits)


def test_query_empty_keywords(synth_root: Path) -> None:
    idx = RadCorpusIndex(root=synth_root)
    assert query(idx, "") == []
    assert query(idx, []) == []


def test_query_limit(synth_root: Path) -> None:
    idx = RadCorpusIndex(root=synth_root)
    # "corpus" matches multiple files via metadata.json content
    hits = query(idx, "corpus", limit=1)
    assert len(hits) <= 1


def test_query_excerpt_present(synth_root: Path) -> None:
    idx = RadCorpusIndex(root=synth_root)
    hits = query(idx, "TOCTOU")
    assert hits
    assert "TOCTOU" in hits[0].excerpt.upper() or "TOCTOU" in hits[0].excerpt


# ---------------------------------------------------------------------------
# append (write layer)
# ---------------------------------------------------------------------------


def test_append_learning_writes_both_files(synth_root: Path) -> None:
    idx = RadCorpusIndex(root=synth_root)
    prov = Provenance(source_type="test", source_id="t1", confidence=0.9)
    entry = append_learning(idx, "security_corpus_v2", "learned content", prov)
    assert entry.doc_path.exists()
    assert entry.provenance_path.exists()
    assert entry.doc_path.read_text(encoding="utf-8") == "learned content"
    prov_data = json.loads(entry.provenance_path.read_text(encoding="utf-8"))
    assert prov_data["source_type"] == "test"
    assert prov_data["source_id"] == "t1"


def test_append_learning_shows_up_as_domain(synth_root: Path) -> None:
    idx = RadCorpusIndex(root=synth_root)
    prov = Provenance(source_type="test", source_id="t1")
    append_learning(idx, "novel_topic", "first learned note", prov)
    learned = idx.list_learned_domains()
    assert "_learned/novel_topic" in learned


def test_append_learning_rejects_path_separator(synth_root: Path) -> None:
    idx = RadCorpusIndex(root=synth_root)
    prov = Provenance(source_type="t", source_id="i")
    with pytest.raises(ValueError):
        append_learning(idx, "bad/name", "x", prov)
    with pytest.raises(ValueError):
        append_learning(idx, "..", "x", prov)


def test_append_learning_explicit_doc_id(synth_root: Path) -> None:
    idx = RadCorpusIndex(root=synth_root)
    prov = Provenance(source_type="t", source_id="i")
    entry = append_learning(idx, "x_corpus", "hi", prov, doc_id="custom-001")
    assert entry.doc_id == "custom-001"
    assert entry.doc_path.name == "custom-001.md"


def test_append_then_query_returns_learned(synth_root: Path) -> None:
    idx = RadCorpusIndex(root=synth_root)
    prov = Provenance(source_type="t", source_id="i")
    append_learning(idx, "rlhf_extra", "Brand new RLHF deep-dive on novel rewards", prov)
    hits = query(idx, "novel rewards")
    # The learned write layer is searched by default
    assert any(h.domain == "_learned/rlhf_extra" for h in hits)


def test_append_learning_skipped_when_include_learned_false(synth_root: Path) -> None:
    idx = RadCorpusIndex(root=synth_root)
    prov = Provenance(source_type="t", source_id="i")
    append_learning(idx, "rlhf_extra", "Brand new RLHF deep-dive", prov)
    hits = query(idx, "deep-dive", include_learned=False)
    assert not any(h.domain.startswith("_learned/") for h in hits)


# ---------------------------------------------------------------------------
# skills (corpus2skill detection)
# ---------------------------------------------------------------------------


def test_detect_skill_index_present(synth_root: Path) -> None:
    sec_path = synth_root / "security_corpus_v2"
    skill = detect_skill_index(sec_path, "security_corpus_v2")
    assert skill is not None
    assert skill.domain == "security_corpus_v2"
    assert skill.metadata.get("corpus_name") == "security_corpus_v2"
    assert "Cluster 1" in skill.sections
    assert "Cluster 2" in skill.sections


def test_detect_skill_index_absent(synth_root: Path) -> None:
    llm_path = synth_root / "llm_corpus_v2"
    skill = detect_skill_index(llm_path, "llm_corpus_v2")
    assert skill is None
