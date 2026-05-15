# SPDX-License-Identifier: Apache-2.0
"""Phase C-2: MCP tool functions (transport-independent unit tests)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from llive.mcp.tools import (
    dispatch,
    tool_append_learning,
    tool_describe,
    tool_get_domain_info,
    tool_list_rad_domains,
    tool_query_rad,
    tool_read_document,
)
from llive.memory.rad import RadCorpusIndex


@pytest.fixture
def synth_index(tmp_path: Path) -> RadCorpusIndex:
    root = tmp_path / "rad"
    root.mkdir()
    sec = root / "security_corpus_v2"
    sec.mkdir()
    (sec / "buffer_overflow.md").write_text(
        "Buffer overflow happens when memory writes exceed allocation.",
        encoding="utf-8",
    )
    (sec / "INDEX.md").write_text("# Skill Index\n\n## Cluster A\n", encoding="utf-8")
    (sec / "metadata.json").write_text(
        json.dumps({"corpus_name": "security_corpus_v2"}),
        encoding="utf-8",
    )
    return RadCorpusIndex(root=root)


def test_list_rad_domains(synth_index: RadCorpusIndex) -> None:
    out = tool_list_rad_domains(index=synth_index)
    assert any(d["name"] == "security_corpus_v2" for d in out)
    info = next(d for d in out if d["name"] == "security_corpus_v2")
    assert info["is_learned"] is False


def test_get_domain_info_with_skill(synth_index: RadCorpusIndex) -> None:
    out = tool_get_domain_info("security_corpus_v2", index=synth_index)
    assert out is not None
    assert "skill_index" in out
    assert "Cluster A" in out["skill_index"]["sections"]


def test_get_domain_info_unknown(synth_index: RadCorpusIndex) -> None:
    assert tool_get_domain_info("ghost", index=synth_index) is None


def test_query_rad(synth_index: RadCorpusIndex) -> None:
    out = tool_query_rad("buffer overflow", index=synth_index)
    assert out
    assert out[0]["domain"] == "security_corpus_v2"
    assert "buffer" in out[0]["matched_terms"]


def test_query_rad_limit(synth_index: RadCorpusIndex) -> None:
    out = tool_query_rad("buffer", limit=1, index=synth_index)
    assert len(out) <= 1


def test_read_document(synth_index: RadCorpusIndex) -> None:
    out = tool_read_document("security_corpus_v2", "buffer_overflow.md", index=synth_index)
    assert "Buffer overflow" in out["text"]
    assert out["truncated"] is False


def test_read_document_truncated(synth_index: RadCorpusIndex) -> None:
    out = tool_read_document(
        "security_corpus_v2",
        "buffer_overflow.md",
        max_bytes=5,
        index=synth_index,
    )
    assert out["truncated"] is True
    assert len(out["text"]) == 5


def test_append_learning_via_tool(synth_index: RadCorpusIndex) -> None:
    out = tool_append_learning(
        "novel_domain",
        "A freshly learned concept.",
        source_type="test",
        source_id="t1",
        index=synth_index,
    )
    assert out["domain"] == "_learned/novel_domain"
    assert Path(out["doc_path"]).exists()
    assert Path(out["provenance_path"]).exists()
    prov = json.loads(Path(out["provenance_path"]).read_text(encoding="utf-8"))
    assert prov["source_type"] == "test"


def test_append_then_query_round_trip(synth_index: RadCorpusIndex) -> None:
    tool_append_learning(
        "novel_domain",
        "Specialized knowledge about quantum-safe TLS handshakes.",
        source_type="test",
        source_id="t1",
        index=synth_index,
    )
    out = tool_query_rad("quantum-safe", index=synth_index)
    assert any(h["domain"] == "_learned/novel_domain" for h in out)


def test_describe_returns_schema() -> None:
    schemas = tool_describe()
    names = {t["name"] for t in schemas}
    assert {"list_rad_domains", "get_domain_info", "query_rad", "read_document", "append_learning"} <= names
    for s in schemas:
        assert "description" in s
        assert s["input_schema"]["type"] == "object"


def test_dispatch_routes(synth_index: RadCorpusIndex) -> None:
    out = dispatch("query_rad", {"keywords": "buffer", "index": synth_index})
    assert out
    assert out[0]["domain"] == "security_corpus_v2"


def test_dispatch_unknown_tool() -> None:
    with pytest.raises(KeyError):
        dispatch("ghost_tool", {})
