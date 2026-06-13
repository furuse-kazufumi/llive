# SPDX-License-Identifier: Apache-2.0
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
    _, summary = session.run_once(bad)
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


# --- ChangeOp sequence logging hook (SPEC-MESH-01) --------------------------


def test_change_op_log_hook_records_applied_ops(tmp_path):
    """A verified diff's materialised action sequence is persisted to the log."""
    from types import SimpleNamespace

    from llive.evolution.change_op_log import ChangeOpSequenceLog

    log = ChangeOpSequenceLog(tmp_path / "ops.jsonl")
    session = SelfReflectionSession(reservoir=None, change_op_log=log)
    container = _container()
    # `_verify` only reads .diff and .candidate_id off the candidate.
    candidate = SimpleNamespace(
        candidate_id="cand_test",
        diff={
            "schema_version": 1,
            "candidate_id": "cand_test",
            "base_candidate": "t_v1",
            "changes": [
                {
                    "action": "remove_subblock",
                    "target_container": "t_v1",
                    "target_subblock": "ffn_swiglu",
                }
            ],
        },
    )
    result = session._verify(container, candidate)
    (rec,) = list(log.iter_records())
    assert rec.actions == ("remove_subblock",)
    assert rec.candidate_id == "cand_test"
    assert rec.container_id == "t_v1"
    assert rec.applied == result.ok  # `applied` mirrors the static gate verdict


def test_change_op_log_hook_skips_when_apply_fails(tmp_path):
    """A diff that cannot apply leaves no row (apply_diff raised before logging)."""
    from types import SimpleNamespace

    from llive.evolution.change_op_log import ChangeOpSequenceLog

    log = ChangeOpSequenceLog(tmp_path / "ops.jsonl")
    session = SelfReflectionSession(reservoir=None, change_op_log=log)
    candidate = SimpleNamespace(
        candidate_id="cand_bad",
        diff={
            "schema_version": 1,
            "candidate_id": "cand_bad",
            "base_candidate": "t_v1",
            "changes": [
                {
                    "action": "remove_subblock",
                    "target_container": "t_v1",
                    "target_subblock": "no_such_subblock",
                }
            ],
        },
    )
    result = session._verify(_container(), candidate)
    assert result.ok is False
    assert list(log.iter_records()) == []


def test_no_change_op_log_by_default(tmp_path):
    """Without a log the session never touches the filesystem for ChangeOps."""
    session = SelfReflectionSession(reservoir=None)
    session.observe_many(_samples())
    proposals, _ = session.run_once(_container())
    assert session.change_op_log is None
    assert len(proposals) >= 1
