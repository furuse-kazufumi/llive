# SPDX-License-Identifier: Apache-2.0
"""Cross-substrate migration (§MI1) の単体テスト."""

from __future__ import annotations

from pathlib import Path

import pytest

from llive.approval import AllowList, ApprovalBus, SqliteLedger, Verdict
from llive.fullsense.sandbox import SandboxOutputBus
from llive.migration import (
    SCHEMA_VERSION,
    IncompatibleBundleError,
    export_state,
    import_state,
)
from llive.migration.bundle import BundleManifest
from llive.migration.importer import load_jsonl
from llive.output import ProductionOutputBus


def test_export_state_produces_tar_gz_with_manifest(tmp_path: Path) -> None:
    db = tmp_path / "approval.db"
    SqliteLedger(db).close()  # 空 ledger を作るだけ
    out = tmp_path / "bundle.tar.gz"

    bundle = export_state(ledger_path=db, sandbox=None, production_bus=None, out_path=out)
    assert out.exists()
    assert bundle.manifest.schema_version == SCHEMA_VERSION
    assert "approval" in bundle.manifest.components
    assert bundle.manifest.exported_at != ""
    assert bundle.manifest.source_substrate.get("python_version", "")


def test_round_trip_preserves_ledger_replay(tmp_path: Path) -> None:
    db = tmp_path / "approval.db"
    request_ids: list[str] = []
    with SqliteLedger(db) as ledger:
        bus = ApprovalBus(ledger=ledger)
        r1 = bus.request("a", {"x": 1})
        r2 = bus.request("b", {"y": 2})
        bus.approve(r1.request_id, by="x")
        bus.deny(r2.request_id, by="y")
        request_ids = [r1.request_id, r2.request_id]

    # Export
    out = tmp_path / "bundle.tar.gz"
    export_state(ledger_path=db, sandbox=None, production_bus=None, out_path=out)

    # Import into a fresh substrate (=新 dest_dir)
    dest = tmp_path / "imported"
    result = import_state(out, dest_dir=dest)
    assert result.ledger_path is not None
    assert result.ledger_path.exists()

    # imported ledger を SqliteLedger で開いて replay が一致することを検証
    with SqliteLedger(result.ledger_path) as imported_ledger:
        bus2 = ApprovalBus(ledger=imported_ledger)
        seq = bus2.replay()
    assert seq == [
        (request_ids[0], Verdict.APPROVED),
        (request_ids[1], Verdict.DENIED),
    ]


def test_round_trip_with_sandbox_denied_emits(tmp_path: Path) -> None:
    db = tmp_path / "approval.db"
    sandbox = SandboxOutputBus()
    with SqliteLedger(db) as ledger:
        bus = ApprovalBus(ledger=ledger)
        from llive.approval import DenyList

        bus._policy = DenyList.of({"file:write"})  # type: ignore[assignment]
        pbus = ProductionOutputBus(approval=bus, sandbox=sandbox)
        pbus.emit_file(tmp_path / "would-not-write.txt", "x")

    out = tmp_path / "bundle.tar.gz"
    export_state(ledger_path=db, sandbox=sandbox, production_bus=pbus, out_path=out)

    dest = tmp_path / "imported"
    result = import_state(out, dest_dir=dest)
    assert result.sandbox_denied_emits_path is not None
    rows = load_jsonl(result.sandbox_denied_emits_path)
    assert any(r["action"] == "file:write" for r in rows)


def test_round_trip_production_records(tmp_path: Path) -> None:
    bus = ApprovalBus(policy=AllowList.of({"counter:inc"}))
    pbus = ProductionOutputBus(approval=bus)
    pbus.emit_raw(action="counter:inc", payload={"step": 1}, on_approved=lambda: None)
    pbus.emit_raw(action="counter:dec", payload={}, on_approved=lambda: None)  # denied

    out = tmp_path / "bundle.tar.gz"
    export_state(ledger_path=None, sandbox=None, production_bus=pbus, out_path=out)

    dest = tmp_path / "imported"
    result = import_state(out, dest_dir=dest)
    assert result.production_records_path is not None
    rows = load_jsonl(result.production_records_path)
    actions = [r["action"] for r in rows]
    assert "counter:inc" in actions
    assert "counter:dec" in actions


def test_no_components_yields_minimal_bundle(tmp_path: Path) -> None:
    out = tmp_path / "empty.tar.gz"
    bundle = export_state(ledger_path=None, sandbox=None, production_bus=None, out_path=out)
    assert bundle.manifest.components == []
    dest = tmp_path / "imported"
    result = import_state(out, dest_dir=dest)
    assert result.ledger_path is None
    assert result.sandbox_records_path is None
    assert result.production_records_path is None


def test_import_rejects_incompatible_schema(tmp_path: Path) -> None:
    # 手で manifest を v999 にした bundle を作る
    import json
    import tarfile

    bad_manifest = BundleManifest(
        schema_version=999,
        llive_version="evil",
        source_substrate={},
        exported_at="2099-01-01T00:00:00+00:00",
        components=[],
    )
    bad_path = tmp_path / "bad.tar.gz"
    manifest_text = bad_manifest.to_json()
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(manifest_text, encoding="utf-8")
    with tarfile.open(bad_path, "w:gz") as tar:
        tar.add(manifest_file, arcname="manifest.json")

    dest = tmp_path / "imported"
    with pytest.raises(IncompatibleBundleError):
        import_state(bad_path, dest_dir=dest)
    # ensure import_state used the json module path correctly
    assert json.loads(manifest_text)["schema_version"] == 999


def test_import_rejects_path_traversal(tmp_path: Path) -> None:
    import tarfile

    bad_path = tmp_path / "evil.tar.gz"
    target = tmp_path / "outside.txt"
    target.write_text("pwn")
    with tarfile.open(bad_path, "w:gz") as tar:
        # arcname に .. を入れて traversal を試みる
        tar.add(target, arcname="../escape.txt")

    dest = tmp_path / "dest"
    with pytest.raises(RuntimeError, match="unsafe tar entry"):
        import_state(bad_path, dest_dir=dest)


def test_manifest_includes_substrate_metadata(tmp_path: Path) -> None:
    out = tmp_path / "bundle.tar.gz"
    bundle = export_state(ledger_path=None, sandbox=None, production_bus=None, out_path=out)
    sub = bundle.manifest.source_substrate
    assert "platform" in sub
    assert "python_version" in sub
    assert "machine" in sub
    assert "hostname" in sub


# ---------------------------------------------------------------------------
# C-4: memory tier bundling
# ---------------------------------------------------------------------------


def test_memory_file_tier_round_trip(tmp_path: Path) -> None:
    """A single-file tier (DuckDB-style) survives round-trip."""
    src = tmp_path / "src" / "episodic.duckdb"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"DUCKDB-LIKE-PAYLOAD\x00\x01\x02")

    out = tmp_path / "bundle.tar.gz"
    bundle = export_state(
        ledger_path=None,
        sandbox=None,
        production_bus=None,
        memory_paths={"episodic": src},
        out_path=out,
    )
    assert "memory" in bundle.manifest.components

    dest = tmp_path / "imported"
    result = import_state(out, dest_dir=dest)
    assert "episodic" in result.memory_paths
    restored = result.memory_paths["episodic"]
    assert restored.exists()
    assert restored.read_bytes() == b"DUCKDB-LIKE-PAYLOAD\x00\x01\x02"


def test_memory_directory_tier_round_trip(tmp_path: Path) -> None:
    """A directory tier (faiss/Kùzu-style) survives round-trip with all children."""
    src = tmp_path / "src" / "semantic"
    src.mkdir(parents=True)
    (src / "index.faiss").write_bytes(b"FAISSBIN")
    (src / "rows.jsonl").write_text('{"id":1}\n{"id":2}\n', encoding="utf-8")

    out = tmp_path / "bundle.tar.gz"
    export_state(
        ledger_path=None,
        sandbox=None,
        production_bus=None,
        memory_paths={"semantic": src},
        out_path=out,
    )

    dest = tmp_path / "imported"
    result = import_state(out, dest_dir=dest)
    assert "semantic" in result.memory_paths
    restored_dir = result.memory_paths["semantic"]
    assert restored_dir.is_dir()
    assert (restored_dir / "index.faiss").read_bytes() == b"FAISSBIN"
    rows = (restored_dir / "rows.jsonl").read_text(encoding="utf-8").splitlines()
    assert rows == ['{"id":1}', '{"id":2}']


def test_multiple_memory_tiers_in_one_bundle(tmp_path: Path) -> None:
    ep = tmp_path / "src" / "episodic.duckdb"
    ep.parent.mkdir(parents=True)
    ep.write_bytes(b"EP")
    sem = tmp_path / "src" / "semantic"
    sem.mkdir(parents=True)
    (sem / "rows.jsonl").write_text("{}\n", encoding="utf-8")
    struct = tmp_path / "src" / "structural.kuzu"
    struct.mkdir()
    (struct / "catalog.kz").write_bytes(b"KZ")

    out = tmp_path / "bundle.tar.gz"
    export_state(
        ledger_path=None,
        sandbox=None,
        production_bus=None,
        memory_paths={"episodic": ep, "semantic": sem, "structural": struct},
        out_path=out,
    )

    dest = tmp_path / "imported"
    result = import_state(out, dest_dir=dest)
    assert sorted(result.memory_paths.keys()) == ["episodic", "semantic", "structural"]


def test_missing_memory_path_silently_skipped(tmp_path: Path) -> None:
    out = tmp_path / "bundle.tar.gz"
    bundle = export_state(
        ledger_path=None,
        sandbox=None,
        production_bus=None,
        memory_paths={"episodic": tmp_path / "does" / "not" / "exist"},
        out_path=out,
    )
    # Nothing was added → "memory" component is NOT listed.
    assert "memory" not in bundle.manifest.components

    dest = tmp_path / "imported"
    result = import_state(out, dest_dir=dest)
    assert result.memory_paths == {}


def test_empty_memory_paths_dict_does_not_create_component(tmp_path: Path) -> None:
    out = tmp_path / "bundle.tar.gz"
    bundle = export_state(
        ledger_path=None,
        sandbox=None,
        production_bus=None,
        memory_paths={},
        out_path=out,
    )
    assert "memory" not in bundle.manifest.components
