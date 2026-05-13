"""TRIZ-07 Self-Reflection end-to-end tests."""

from __future__ import annotations

import json
import os

import pytest

from llive.evolution.reservoir import FailedCandidateReservoir
from llive.evolution.verifier import Invariants
from llive.schema.models import ContainerSpec, SubBlockRef
from llive.triz.rad_generator import RadBackedIdeaGenerator, RadCorpusLookup, TemplateIdeaLLM
from llive.triz.self_reflection import SelfReflectionSession, write_session_jsonl


@pytest.fixture(autouse=True)
def _isolate_llive_data(tmp_path, monkeypatch):
    monkeypatch.setenv("LLIVE_DATA_DIR", str(tmp_path))
    yield


def _container() -> ContainerSpec:
    return ContainerSpec(
        schema_version=1,
        container_id="t_v1",
        subblocks=[
            SubBlockRef(type="pre_norm"),
            SubBlockRef(type="causal_attention"),
            SubBlockRef(type="memory_read", name="r_existing"),
            SubBlockRef(type="memory_write", name="w_existing"),
            SubBlockRef(type="ffn_swiglu"),
        ],
    )


def _samples():
    samples = []
    for i in range(20):
        samples.append({
            "pipeline.latency_ms": 100.0 - i * 2.0,
            "evolution.forgetting": 0.10 + i * 0.005,
        })
    return samples


def test_session_run_once_returns_proposals(tmp_path):
    reservoir = FailedCandidateReservoir(tmp_path / "res.duckdb")
    generator = RadBackedIdeaGenerator(
        llm=TemplateIdeaLLM(), corpus=RadCorpusLookup(base_dir=tmp_path / "missing")
    )
    session = SelfReflectionSession(reservoir=reservoir, generator=generator, top_k_principles=2)
    session.observe_many(_samples())
    proposals, summary = session.run_once(_container())
    reservoir.close()
    assert summary.n_contradictions >= 1
    assert len(proposals) >= 1


def test_session_no_contradictions_means_no_proposals(tmp_path):
    session = SelfReflectionSession(reservoir=None)
    flat = [{"pipeline.latency_ms": 100.0, "evolution.forgetting": 0.1} for _ in range(20)]
    session.observe_many(flat)
    proposals, summary = session.run_once(_container())
    assert summary.n_contradictions == 0
    assert proposals == []


def test_failed_proposals_spool_to_reservoir(tmp_path):
    reservoir = FailedCandidateReservoir(tmp_path / "res.duckdb")
    # Use a container that lacks attention so most diffs will fail invariants
    bad = ContainerSpec(
        schema_version=1,
        container_id="bad_v1",
        subblocks=[SubBlockRef(type="pre_norm"), SubBlockRef(type="ffn_swiglu")],
    )
    session = SelfReflectionSession(
        reservoir=reservoir,
        invariants=Invariants(),
        top_k_principles=3,
    )
    session.observe_many(_samples())
    proposals, summary = session.run_once(bad)
    assert summary.n_failed >= 1
    failures = reservoir.list(reason="verifier")
    assert len(failures) >= 1
    reservoir.close()


def test_write_session_jsonl(tmp_path):
    session = SelfReflectionSession(reservoir=None)
    session.observe_many(_samples())
    proposals, summary = session.run_once(_container())
    out = tmp_path / "session.jsonl"
    write_session_jsonl(proposals, summary, out)
    assert out.exists()
    lines = out.read_text(encoding="utf-8").strip().split("\n")
    # last line is the summary row
    last = json.loads(lines[-1])
    assert last["row"] == "summary"
    assert last["n_proposals"] == len(proposals)


def test_use_smt_false_skips_z3(tmp_path):
    session = SelfReflectionSession(reservoir=None, use_smt=False)
    session.observe_many(_samples())
    proposals, _ = session.run_once(_container())
    for p in proposals:
        assert p.verification.smt_used is False


def test_observe_many_returns_count():
    session = SelfReflectionSession(reservoir=None)
    n = session.observe_many(iter(_samples()))
    assert n == len(_samples())


def test_session_isolates_llive_data_dir(tmp_path):
    # Sanity that our fixture redirected LLIVE_DATA_DIR.
    assert os.environ["LLIVE_DATA_DIR"].startswith(str(tmp_path.parent))
