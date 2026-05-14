"""Phase B integration: Consolidator mirrors ConceptPages into RAD write layer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from llive.memory.concept import ConceptPage
from llive.memory.consolidation import Consolidator, ConsolidatorConfig
from llive.memory.episodic import EpisodicEvent, EpisodicMemory
from llive.memory.provenance import Provenance
from llive.memory.rad import RadCorpusIndex
from llive.memory.structural import StructuralMemory


@pytest.fixture(autouse=True)
def _force_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLIVE_CONSOLIDATOR_MOCK", "1")


@pytest.fixture
def synth_rad(tmp_path: Path) -> RadCorpusIndex:
    root = tmp_path / "rad"
    root.mkdir()
    return RadCorpusIndex(root=root)


@pytest.fixture
def cons_with_rad(tmp_path: Path, synth_rad: RadCorpusIndex) -> Consolidator:
    ep = EpisodicMemory(db_path=tmp_path / "ep.duckdb")
    sm = StructuralMemory(db_path=tmp_path / "s.kuzu")
    c = Consolidator(
        episodic=ep,
        structural=sm,
        config=ConsolidatorConfig(
            sample_size=20,
            cluster_min_size=2,
            cluster_similarity_threshold=0.22,
        ),
        rad_index=synth_rad,
    )
    yield c
    ep.close()
    sm.close()


def _write_event(ep: EpisodicMemory, content: str) -> None:
    ep.write(
        EpisodicEvent(
            content=content,
            provenance=Provenance(source_type="test", source_id="t"),
        )
    )


def test_rad_domain_default_mapping() -> None:
    # Default mapping uses page_type, sanitised to [a-z0-9_]
    page = ConceptPage.from_title("Test", page_type="Security Concept")
    # We can't instantiate a full Consolidator without DBs, so test the helper via subclass
    from llive.memory.consolidation import Consolidator as _Cons

    class _Stub(_Cons):
        def __init__(self) -> None:  # noqa: PLE0249 — intentional no-op constructor for unit test
            pass

    stub = _Stub.__new__(_Stub)
    assert stub._rad_domain_for(page) == "security_concept"
    page2 = ConceptPage.from_title("Test", page_type="domain_concept")
    assert stub._rad_domain_for(page2) == "domain_concept"
    page3 = ConceptPage.from_title("Test", page_type="")
    assert stub._rad_domain_for(page3) == "concept"


def test_cycle_writes_to_rad_learned(cons_with_rad: Consolidator, synth_rad: RadCorpusIndex) -> None:
    # Add a cluster of similar events
    for content in [
        "buffer overflow attack against memory layout",
        "buffer overflow exploits in C programs",
        "exploiting buffer overflows on the stack",
    ]:
        _write_event(cons_with_rad.episodic, content)

    result = cons_with_rad.run_once(limit=10)
    assert result.pages_created >= 1, f"expected at least one page; errors={result.errors}"

    # The default page_type is "domain_concept" → _learned/domain_concept/
    learned_dir = synth_rad.learned_root / "domain_concept"
    assert learned_dir.exists(), f"learned dir not created; rad root={synth_rad.root}"
    files = sorted(p.name for p in learned_dir.iterdir())
    md_files = [f for f in files if f.endswith(".md")]
    prov_files = [f for f in files if f.endswith(".provenance.json")]
    assert md_files, "no .md learned files written"
    assert prov_files, "no .provenance.json sidecars written"

    # Verify provenance contents
    prov_data = json.loads((learned_dir / prov_files[0]).read_text(encoding="utf-8"))
    assert prov_data["source_type"] == "consolidator"
    assert prov_data["confidence"] == 0.8
    assert prov_data["derived_from"], "derived_from must include raw event ids"


def test_cycle_without_rad_unchanged(tmp_path: Path) -> None:
    """Smoke test: rad_index=None keeps the original behaviour."""
    ep = EpisodicMemory(db_path=tmp_path / "ep.duckdb")
    sm = StructuralMemory(db_path=tmp_path / "s.kuzu")
    cons = Consolidator(
        episodic=ep,
        structural=sm,
        config=ConsolidatorConfig(
            sample_size=20,
            cluster_min_size=2,
            cluster_similarity_threshold=0.22,
        ),
    )
    try:
        for content in [
            "novel concept alpha",
            "novel concept alpha variation",
            "novel concept alpha again",
        ]:
            _write_event(ep, content)
        result = cons.run_once(limit=10)
        # No rad-mirror errors should be present
        assert not any(e.startswith("rad_mirror:") for e in result.errors)
    finally:
        ep.close()
        sm.close()


def test_rad_mirror_failure_is_non_fatal(tmp_path: Path) -> None:
    """If RAD write fails (e.g. unwritable dir), consolidation still completes."""
    ep = EpisodicMemory(db_path=tmp_path / "ep.duckdb")
    sm = StructuralMemory(db_path=tmp_path / "s.kuzu")

    # Use a bogus rad_index that always raises on append_learning
    class _BoomRad:
        @property
        def learned_root(self) -> Path:
            raise RuntimeError("boom")

        def reload(self) -> None:
            pass

    cons = Consolidator(
        episodic=ep,
        structural=sm,
        config=ConsolidatorConfig(
            sample_size=20,
            cluster_min_size=2,
            cluster_similarity_threshold=0.22,
        ),
        rad_index=_BoomRad(),
    )
    try:
        for content in [
            "rad boom test alpha",
            "rad boom test alpha variant",
            "rad boom test alpha again",
        ]:
            _write_event(ep, content)
        result = cons.run_once(limit=10)
        # Cycle completes; failure is captured as an "info" / error string
        assert result.pages_created >= 1
        assert any(e.startswith("rad_mirror:") for e in result.errors)
    finally:
        ep.close()
        sm.close()
