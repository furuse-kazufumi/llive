# SPDX-License-Identifier: Apache-2.0
"""F25 (g): LoveBridge writer (route_trace / memory_link / bwt + MCP push).

JSONL writer の動作と、optional な MCP ingest push 経路を fake URL +
``urlopen`` モンキーパッチで検証する。実 llmesh に接続しない。
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from llive.observability.llove_bridge import LoveBridge

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bridge_no_push(tmp_path: Path) -> LoveBridge:
    """Push 無効・logs_dir を tmp に向けた bridge."""
    return LoveBridge(
        node_id="llive-test",
        logs_dir=tmp_path,
        push_enabled=False,
    )


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# ---------------------------------------------------------------------------
# emit_bwt_summary
# ---------------------------------------------------------------------------


def test_emit_bwt_summary_writes_jsonl(
    bridge_no_push: LoveBridge, tmp_path: Path
) -> None:
    payload = bridge_no_push.emit_bwt_summary(
        bwt=-0.008,
        avg_accuracy=0.78,
        n_tasks=5,
        per_task_drop={"t1": -0.01, "t2": -0.006},
        task_order=["t1", "t2"],
    )
    bwt_file = tmp_path / "bwt.jsonl"
    assert bwt_file.exists()
    rows = _read_jsonl(bwt_file)
    assert len(rows) == 1
    row = rows[0]
    assert row["kind"] == "bwt_summary"
    assert row["version"] == 1
    assert row["node_id"] == "llive-test"
    assert row["bwt"] == -0.008
    assert row["per_task_drop"]["t1"] == -0.01
    # 返り値も同等
    assert payload["bwt"] == -0.008


def test_emit_bwt_generates_uuid_v4_task_id_by_default(
    bridge_no_push: LoveBridge,
) -> None:
    payload = bridge_no_push.emit_bwt_summary(
        bwt=0.0, avg_accuracy=0.0, n_tasks=0, per_task_drop={}
    )
    parsed = uuid.UUID(payload["task_id"])
    assert parsed.version == 4


def test_emit_bwt_rejects_non_uuid4_task_id(bridge_no_push: LoveBridge) -> None:
    with pytest.raises(ValueError, match="UUID v4"):
        bridge_no_push.emit_bwt_summary(
            bwt=0.0,
            avg_accuracy=0.0,
            n_tasks=0,
            per_task_drop={},
            task_id="not-a-uuid",
        )


def test_emit_bwt_rejects_uuid_v1_task_id(bridge_no_push: LoveBridge) -> None:
    with pytest.raises(ValueError, match="UUID v4"):
        bridge_no_push.emit_bwt_summary(
            bwt=0.0,
            avg_accuracy=0.0,
            n_tasks=0,
            per_task_drop={},
            task_id=str(uuid.uuid1()),
        )


def test_emit_bwt_appends_multiple_runs(
    bridge_no_push: LoveBridge, tmp_path: Path
) -> None:
    bridge_no_push.emit_bwt_summary(
        bwt=-0.01, avg_accuracy=0.7, n_tasks=3, per_task_drop={}
    )
    bridge_no_push.emit_bwt_summary(
        bwt=-0.005, avg_accuracy=0.75, n_tasks=4, per_task_drop={}
    )
    rows = _read_jsonl(tmp_path / "bwt.jsonl")
    assert len(rows) == 2
    assert rows[0]["bwt"] == -0.01
    assert rows[1]["bwt"] == -0.005


# ---------------------------------------------------------------------------
# emit_route_trace
# ---------------------------------------------------------------------------


def test_emit_route_trace_writes_jsonl(
    bridge_no_push: LoveBridge, tmp_path: Path
) -> None:
    bridge_no_push.emit_route_trace(
        container="adaptive_v1",
        subblocks=[
            {"name": "pre_norm", "type": "pre_norm", "duration_ms": 0.12},
            {"name": "memory_read", "type": "memory_read", "duration_ms": 1.4},
        ],
        memory_accesses=[
            {"op": "read", "layer": "semantic",
             "hits": [{"id": "h1", "score": 0.83}]},
        ],
        metrics={"latency_ms": 2.12, "subblock_count": 2},
    )
    rt_file = tmp_path / "route_trace.jsonl"
    assert rt_file.exists()
    rows = _read_jsonl(rt_file)
    assert len(rows) == 1
    row = rows[0]
    assert row["kind"] == "route_trace"
    assert row["container"] == "adaptive_v1"
    assert len(row["subblocks"]) == 2
    assert row["metrics"]["latency_ms"] == 2.12


def test_emit_route_trace_defaults_for_optionals(
    bridge_no_push: LoveBridge, tmp_path: Path
) -> None:
    bridge_no_push.emit_route_trace(container="x", subblocks=[])
    row = _read_jsonl(tmp_path / "route_trace.jsonl")[0]
    assert row["memory_accesses"] == []
    assert row["metrics"] == {}


def test_emit_route_trace_rejects_invalid_task_id(bridge_no_push: LoveBridge) -> None:
    with pytest.raises(ValueError):
        bridge_no_push.emit_route_trace(
            container="x", subblocks=[], task_id="bad"
        )


# ---------------------------------------------------------------------------
# emit_concept_update
# ---------------------------------------------------------------------------


def test_emit_concept_update_writes_jsonl(
    bridge_no_push: LoveBridge, tmp_path: Path
) -> None:
    bridge_no_push.emit_concept_update(
        concept_id="memory-consolidation",
        title="Memory Consolidation",
        page_type="domain_concept",
        linked_concept_ids=["surprise-gate"],
        surprise_stats={"n": 6, "mean": 0.42, "m2": 0.05},
        summary="When surprise exceeds threshold.",
    )
    rows = _read_jsonl(tmp_path / "memory_link.jsonl")
    assert len(rows) == 1
    row = rows[0]
    assert row["kind"] == "concept_update"
    assert row["concept_id"] == "memory-consolidation"
    assert row["linked_concept_ids"] == ["surprise-gate"]
    assert row["surprise_stats"]["mean"] == 0.42


def test_emit_concept_update_rejects_empty_concept_id(
    bridge_no_push: LoveBridge,
) -> None:
    with pytest.raises(ValueError, match="concept_id is required"):
        bridge_no_push.emit_concept_update(concept_id="")


def test_emit_concept_update_default_title_falls_back_to_concept_id(
    bridge_no_push: LoveBridge, tmp_path: Path
) -> None:
    bridge_no_push.emit_concept_update(concept_id="raw-id")
    row = _read_jsonl(tmp_path / "memory_link.jsonl")[0]
    assert row["title"] == "raw-id"


# ---------------------------------------------------------------------------
# MCP push 経路 (urlopen モンキーパッチ)
# ---------------------------------------------------------------------------


def test_emit_bwt_pushes_to_ingest_when_url_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`LLIVE_MCP_INGEST_URL` が設定されていれば urlopen が呼ばれる."""
    captured: dict[str, object] = {}

    class FakeResp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = req.data
        captured["method"] = req.method
        captured["headers"] = dict(req.headers)
        return FakeResp()

    monkeypatch.setattr(
        "llive.observability.llove_bridge.urllib.request.urlopen",
        fake_urlopen,
    )

    bridge = LoveBridge(
        node_id="llive-pushy",
        logs_dir=tmp_path,
        ingest_url="http://localhost:8000",
        push_enabled=True,
    )
    bridge.emit_bwt_summary(
        bwt=-0.01, avg_accuracy=0.7, n_tasks=2, per_task_drop={"t1": -0.01}
    )

    # JSONL も書かれた
    assert (tmp_path / "bwt.jsonl").exists()
    # POST が発火
    assert captured["url"] == "http://localhost:8000/timeline/ingest"
    assert captured["method"] == "POST"
    body = json.loads(captured["body"].decode("utf-8"))
    assert body["event_type"] == "bwt_summary"
    assert body["node_id"] == "llive-pushy"
    assert body["metadata"]["bwt"] == -0.01
    assert bridge.last_push_ok is True


def test_push_failure_does_not_break_jsonl_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HTTP error が起きても JSONL は書かれる (fail-closed)."""
    import urllib.error

    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(
        "llive.observability.llove_bridge.urllib.request.urlopen",
        fake_urlopen,
    )

    bridge = LoveBridge(
        node_id="llive-fail",
        logs_dir=tmp_path,
        ingest_url="http://nonexistent:1",
        push_enabled=True,
    )
    bridge.emit_route_trace(container="x", subblocks=[])
    assert (tmp_path / "route_trace.jsonl").exists()
    assert bridge.last_push_ok is False


def test_no_push_when_no_url_and_no_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`LLIVE_MCP_INGEST_URL` も `ingest_url` も無ければ push しない."""
    monkeypatch.delenv("LLIVE_MCP_INGEST_URL", raising=False)
    called = []

    def fake_urlopen(req, timeout=None):
        called.append(True)
        class R:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return R()

    monkeypatch.setattr(
        "llive.observability.llove_bridge.urllib.request.urlopen",
        fake_urlopen,
    )

    bridge = LoveBridge(node_id="x", logs_dir=tmp_path, push_enabled=True)
    bridge.emit_concept_update(concept_id="c1")
    # URL 未設定なので urlopen は呼ばれていない
    assert called == []
    assert bridge.last_push_ok is False


def test_push_disabled_explicitly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`push_enabled=False` なら URL があっても push しない."""
    called = []
    monkeypatch.setattr(
        "llive.observability.llove_bridge.urllib.request.urlopen",
        lambda req, timeout=None: called.append(True) or None,
    )
    bridge = LoveBridge(
        node_id="x",
        logs_dir=tmp_path,
        ingest_url="http://localhost:8000",
        push_enabled=False,
    )
    bridge.emit_bwt_summary(
        bwt=0.0, avg_accuracy=0.0, n_tasks=0, per_task_drop={}
    )
    assert called == []


def test_env_var_provides_ingest_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ingest_url=None` でも `LLIVE_MCP_INGEST_URL` から取れる."""
    captured: dict[str, str] = {}

    class FakeResp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return FakeResp()

    monkeypatch.setenv("LLIVE_MCP_INGEST_URL", "http://from-env:9000")
    monkeypatch.setattr(
        "llive.observability.llove_bridge.urllib.request.urlopen",
        fake_urlopen,
    )

    bridge = LoveBridge(
        node_id="x", logs_dir=tmp_path, ingest_url=None, push_enabled=True
    )
    bridge.emit_concept_update(concept_id="c1")
    assert captured.get("url") == "http://from-env:9000/timeline/ingest"
