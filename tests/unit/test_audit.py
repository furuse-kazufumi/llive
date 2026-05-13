"""SEC-03 Audit Trail (SHA-256 chain) tests."""

from __future__ import annotations

import sqlite3

import pytest

from llive.security.audit import AuditTrail, verify_chain


@pytest.fixture
def trail(tmp_path):
    db = tmp_path / "trail.sqlite3"
    t = AuditTrail(db)
    yield t
    t.close()


def test_append_and_count(trail):
    entry = trail.append("alice", "promote", {"candidate": "c1"})
    assert entry.seq == 1
    assert trail.count() == 1
    assert entry.actor == "alice"
    assert entry.action == "promote"


def test_chain_links_prev_hashes(trail):
    e1 = trail.append("alice", "a", {"x": 1})
    e2 = trail.append("bob", "b", {"x": 2})
    e3 = trail.append("carol", "c", {"x": 3})
    assert e2.prev_hash == e1.entry_hash
    assert e3.prev_hash == e2.entry_hash


def test_verify_chain_passes_when_untouched(trail):
    for i in range(5):
        trail.append("alice", "x", {"i": i})
    res = trail.verify()
    assert res.ok
    assert res.inspected == 5
    assert res.broken_at_seq is None


def test_verify_chain_detects_tampered_payload(trail, tmp_path):
    for i in range(3):
        trail.append("alice", "x", {"i": i})
    trail.close()
    # Tamper directly through sqlite3
    conn = sqlite3.connect(trail.db_path)
    conn.execute("UPDATE audit_trail SET payload = ? WHERE seq = ?", ('{"i": 99}', 2))
    conn.commit()
    conn.close()
    # Reopen and verify
    fresh = AuditTrail(trail.db_path)
    res = verify_chain(fresh)
    fresh.close()
    assert not res.ok
    assert res.broken_at_seq == 2


def test_head_returns_latest(trail):
    assert trail.head() is None
    trail.append("alice", "a", {})
    last = trail.append("bob", "b", {})
    head = trail.head()
    assert head is not None
    assert head.seq == last.seq


def test_list_paginates(trail):
    for i in range(10):
        trail.append("alice", "x", {"i": i})
    rows = trail.list(since_seq=3, limit=2)
    assert [r.seq for r in rows] == [4, 5]


def test_default_payload_is_empty_dict(trail):
    entry = trail.append("alice", "noop")
    assert entry.payload == {}


def test_to_dict_serialisable(trail):
    entry = trail.append("alice", "x", {"k": "v"})
    d = entry.to_dict()
    assert d["actor"] == "alice"
    assert d["payload"]["k"] == "v"
    assert isinstance(d["ts"], str)


def test_context_manager_closes(tmp_path):
    db = tmp_path / "x.sqlite3"
    with AuditTrail(db) as t:
        t.append("alice", "x", {})
        assert t.count() == 1


def test_verify_detects_swapped_rows(trail):
    """Swapping ts values breaks the hash chain."""
    for i in range(3):
        trail.append("alice", "x", {"i": i})
    trail.close()
    conn = sqlite3.connect(trail.db_path)
    rows = conn.execute("SELECT seq, ts FROM audit_trail ORDER BY seq").fetchall()
    conn.execute("UPDATE audit_trail SET ts = ? WHERE seq = ?", (rows[1][1] + "X", rows[1][0]))
    conn.commit()
    conn.close()
    fresh = AuditTrail(trail.db_path)
    assert not fresh.verify().ok
    fresh.close()
