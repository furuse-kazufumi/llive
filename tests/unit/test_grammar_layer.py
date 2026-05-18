# SPDX-License-Identifier: Apache-2.0
"""Tests for COG-MESH-09 GrammarLayer (Phase 7 skeleton API)."""

from __future__ import annotations

import pytest

from llive.cognitive_mesh.grammar_layer import (
    GrammarChangeStatus,
    GrammarLayer,
    GrammarSnapshot,
    ProposedChange,
    UsageEvidence,
)


def _make() -> GrammarLayer:
    return GrammarLayer()


def test_add_and_get_snapshot() -> None:
    g = _make()
    snap = GrammarSnapshot(language="ja", version="grammar_v_2020", rules={"r1": "v1"})
    g.add_snapshot(snap)
    got = g.get("ja", "grammar_v_2020")
    assert got is snap


def test_add_duplicate_version_rejected() -> None:
    g = _make()
    snap = GrammarSnapshot(language="ja", version="v1", rules={})
    g.add_snapshot(snap)
    with pytest.raises(ValueError, match="already"):
        g.add_snapshot(GrammarSnapshot(language="ja", version="v1", rules={}))


def test_versions_and_languages() -> None:
    g = _make()
    g.add_snapshot(GrammarSnapshot(language="ja", version="v1", rules={}))
    g.add_snapshot(GrammarSnapshot(language="ja", version="v2", rules={}))
    g.add_snapshot(GrammarSnapshot(language="en", version="v1", rules={}))
    assert g.languages() == ["en", "ja"]
    assert g.versions("ja") == ["v1", "v2"]


def test_propose_change_requires_base_version() -> None:
    g = _make()
    with pytest.raises(KeyError, match="base_version"):
        g.propose_change(
            language="ja",
            base_version="missing",
            pattern="new_pattern",
            evidence=UsageEvidence(pattern="x", samples=["a", "b"]),
        )


def test_propose_and_promote() -> None:
    g = _make()
    g.add_snapshot(GrammarSnapshot(language="ja", version="v1", rules={"base": True}))
    proposal = g.propose_change(
        language="ja",
        base_version="v1",
        pattern="np_attr_doubled",
        evidence=UsageEvidence(pattern="np→np", samples=["A の B", "X の Y"]),
    )
    assert proposal.status == GrammarChangeStatus.PROPOSED
    new_snap = g.promote(proposal, new_version="v2")
    assert new_snap.version == "v2"
    assert "np_attr_doubled" in new_snap.rules
    assert proposal.status == GrammarChangeStatus.PROMOTED


def test_promote_only_once() -> None:
    g = _make()
    g.add_snapshot(GrammarSnapshot(language="ja", version="v1", rules={}))
    p = g.propose_change(
        language="ja",
        base_version="v1",
        pattern="x",
        evidence=UsageEvidence(pattern="p", samples=[]),
    )
    g.promote(p, new_version="v2")
    with pytest.raises(ValueError, match="PROPOSED"):
        g.promote(p, new_version="v3")


def test_pending_proposals_filter_by_language() -> None:
    g = _make()
    g.add_snapshot(GrammarSnapshot(language="ja", version="v1", rules={}))
    g.add_snapshot(GrammarSnapshot(language="en", version="v1", rules={}))
    g.propose_change("ja", "v1", "p_ja", UsageEvidence(pattern="x", samples=[]))
    g.propose_change("en", "v1", "p_en", UsageEvidence(pattern="x", samples=[]))
    ja = g.pending_proposals(language="ja")
    en = g.pending_proposals(language="en")
    assert len(ja) == 1
    assert len(en) == 1
    assert ja[0].language == "ja"


def test_reject_marks_status() -> None:
    g = _make()
    g.add_snapshot(GrammarSnapshot(language="ja", version="v1", rules={}))
    p = g.propose_change("ja", "v1", "p", UsageEvidence(pattern="x", samples=[]))
    g.reject(p)
    assert p.status == GrammarChangeStatus.REJECTED
    # 拒否後は pending に出ない
    assert g.pending_proposals(language="ja") == []
