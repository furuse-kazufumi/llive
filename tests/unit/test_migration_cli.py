# SPDX-License-Identifier: Apache-2.0
"""llive.migration CLI の単体テスト."""

from __future__ import annotations

from pathlib import Path

import pytest

from llive.approval import ApprovalBus, SqliteLedger
from llive.migration.__main__ import main


def test_cli_export_creates_bundle(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "approval.db"
    with SqliteLedger(db) as ledger:
        bus = ApprovalBus(ledger=ledger)
        req = bus.request("ping", {})
        bus.approve(req.request_id, by="t")
    out = tmp_path / "bundle.tar.gz"
    rc = main(["export", "--ledger", str(db), "--out", str(out)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "exported:" in captured.out
    assert "approval" in captured.out
    assert out.exists()


def test_cli_import_extracts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # First export
    db = tmp_path / "approval.db"
    SqliteLedger(db).close()
    bundle = tmp_path / "bundle.tar.gz"
    main(["export", "--ledger", str(db), "--out", str(bundle)])

    # Then import
    dest = tmp_path / "dest"
    rc = main(["import", str(bundle), "--dest", str(dest)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "imported to:" in captured.out
    assert (dest / "manifest.json").exists()


def test_cli_inspect_prints_manifest(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "approval.db"
    SqliteLedger(db).close()
    bundle = tmp_path / "bundle.tar.gz"
    main(["export", "--ledger", str(db), "--out", str(bundle)])

    capsys.readouterr()  # clear export output
    rc = main(["inspect", str(bundle)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "schema_version" in captured.out
    assert "Members:" in captured.out
    assert "manifest.json" in captured.out


def test_cli_inspect_missing_manifest_returns_4(tmp_path: Path) -> None:
    """manifest 無し bundle は inspect で exit 4."""
    import tarfile

    bad = tmp_path / "no-manifest.tar.gz"
    other = tmp_path / "other.txt"
    other.write_text("hi")
    with tarfile.open(bad, "w:gz") as tar:
        tar.add(other, arcname="other.txt")
    rc = main(["inspect", str(bad)])
    assert rc == 4


def test_cli_import_incompatible_returns_2(tmp_path: Path) -> None:
    """schema_version 不一致は exit 2."""
    import tarfile

    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"schema_version": 999, "llive_version": "x", "source_substrate": {}, "exported_at": "", "components": []}', encoding="utf-8")
    bundle = tmp_path / "bad.tar.gz"
    with tarfile.open(bundle, "w:gz") as tar:
        tar.add(manifest, arcname="manifest.json")
    dest = tmp_path / "dest"
    rc = main(["import", str(bundle), "--dest", str(dest)])
    assert rc == 2
