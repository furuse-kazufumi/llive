# SPDX-License-Identifier: Apache-2.0
"""Conformance Manifest (A-4) — §11.V4 の単体テスト."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

from llive.fullsense.manifest import (
    Clause,
    ConformanceManifest,
    build_manifest,
    evaluate_static_clauses,
    main,
)

# ---------------------------------------------------------------------------
# Clause / ConformanceManifest dataclasses
# ---------------------------------------------------------------------------


def test_clause_jsonable_roundtrip() -> None:
    c = Clause(id="R1", status="holds", evidence="x", chapter="§4")
    d = c.to_jsonable()
    assert d == {"id": "R1", "status": "holds", "evidence": "x", "chapter": "§4"}


def test_summary_counts() -> None:
    m = ConformanceManifest()
    m.add(Clause(id="A", status="holds", evidence=""))
    m.add(Clause(id="B", status="holds", evidence=""))
    m.add(Clause(id="C", status="violated", evidence=""))
    m.add(Clause(id="D", status="undecidable", evidence=""))
    assert m.summary() == {"holds": 2, "violated": 1, "undecidable": 1}


# ---------------------------------------------------------------------------
# evaluate_static_clauses — implementation 存在検査
# ---------------------------------------------------------------------------


def test_static_clauses_cover_core_requirements() -> None:
    clauses = evaluate_static_clauses()
    ids = {c.id for c in clauses}
    # 必須 spec clauses が含まれること
    required = {"R1", "R2", "R3", "F1", "F2", "F3", "F4", "F5", "I3", "V4", "L2-sandbox"}
    missing = required - ids
    assert not missing, f"missing required clauses in manifest: {missing}"


def test_static_clauses_have_evidence_text() -> None:
    for c in evaluate_static_clauses():
        # holds なら evidence は空でないこと (§I2 attribution)
        if c.status == "holds":
            assert c.evidence, f"holds clause {c.id} must have evidence text"


def test_sing_is_undecidable_at_level_2() -> None:
    clauses = {c.id: c for c in evaluate_static_clauses()}
    sing = clauses.get("SING")
    assert sing is not None
    assert sing.status == "undecidable"
    assert "Level 2" in sing.evidence or "A°" in sing.evidence


def test_deception_clause_present() -> None:
    clauses = {c.id: c for c in evaluate_static_clauses()}
    assert "5.D" in clauses
    assert clauses["5.D"].status == "holds"


def test_multitrack_clause_present() -> None:
    clauses = {c.id: c for c in evaluate_static_clauses()}
    assert "F*-track" in clauses
    assert clauses["F*-track"].status == "holds"


# ---------------------------------------------------------------------------
# build_manifest
# ---------------------------------------------------------------------------


def test_build_manifest_has_metadata() -> None:
    m = build_manifest(implementation_version="test123")
    assert m.spec_version == "v1.1.0"
    assert m.agent_name == "llive-fullsense"
    assert m.implementation_version == "test123"
    payload = m.to_jsonable()
    assert payload["schema_version"] == 1
    assert payload["spec_version"] == "v1.1.0"
    assert payload["agent"]["implementation_version"] == "test123"
    # clauses は list、summary はカウント整合
    clauses = payload["clauses"]
    summary = payload["summary"]
    assert isinstance(clauses, list)
    assert sum(summary.values()) == len(clauses)


def test_build_manifest_is_json_serialisable() -> None:
    m = build_manifest()
    s = json.dumps(m.to_jsonable(), ensure_ascii=False)
    # 非空 + 仕様キーが含まれること
    assert "schema_version" in s
    assert "clauses" in s


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def _run_cli(args: list[str]) -> dict[str, object]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(args)
    assert rc == 0
    return json.loads(buf.getvalue())


def test_cli_full_manifest_emits_clauses() -> None:
    out = _run_cli(["--impl-version", "test"])
    assert out["schema_version"] == 1
    assert "clauses" in out
    assert isinstance(out["clauses"], list)
    assert len(out["clauses"]) > 5


def test_cli_summary_only_omits_clauses() -> None:
    out = _run_cli(["--summary-only", "--impl-version", "test"])
    assert "clauses" not in out
    assert "summary" in out
    assert set(out["summary"].keys()) == {"holds", "violated", "undecidable"}


def test_cli_compact_output_via_indent_0() -> None:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--indent", "0", "--summary-only", "--impl-version", "test"])
    assert rc == 0
    raw = buf.getvalue().strip()
    # indent=0 はコンパクト (改行なし)
    assert "\n" not in raw
    json.loads(raw)  # 不正でないこと


def test_cli_custom_spec_version_propagates() -> None:
    out = _run_cli(["--spec-version", "v9.9.9", "--impl-version", "test"])
    assert out["spec_version"] == "v9.9.9"


def test_cli_default_runs_without_arguments() -> None:
    """no-arg 呼び出しが SystemExit などで死なないこと."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main([])
    assert rc == 0
    json.loads(buf.getvalue())
