"""KAR ingestor (scripts/import_rad_extended.py) の単体テスト.

importable な module としても扱うため `scripts` を sys.path に追加してテスト.
"""

from __future__ import annotations

import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "import_rad_extended",
        Path(__file__).parent.parent.parent / "scripts" / "import_rad_extended.py",
    )
    if spec is None or spec.loader is None:
        pytest.skip("import_rad_extended.py not loadable")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_list_manifests_has_three_phases() -> None:
    mod = _load_module()
    all_m = mod.list_manifests()
    phases = {m.phase for m in all_m}
    assert phases == {"short", "mid", "long"}


def test_phase_filter() -> None:
    mod = _load_module()
    short = mod.list_manifests("short")
    assert all(m.phase == "short" for m in short)
    assert len(short) >= 2


def test_total_size_estimate() -> None:
    mod = _load_module()
    assert mod.total_size_gb("short") > 0
    assert mod.total_size_gb(None) > mod.total_size_gb("short")


def test_cli_summary_emits_json() -> None:
    mod = _load_module()
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = mod.main(["--summary"])
    assert rc == 0
    out = json.loads(buf.getvalue())
    assert set(out.keys()) == {"short_gb", "mid_gb", "long_gb", "total_gb"}
    assert out["total_gb"] == pytest.approx(out["short_gb"] + out["mid_gb"] + out["long_gb"])


def test_cli_list_emits_array() -> None:
    mod = _load_module()
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = mod.main(["--list"])
    assert rc == 0
    arr = json.loads(buf.getvalue())
    assert isinstance(arr, list)
    assert len(arr) >= 5
    # 各エントリに必須キーがある
    for m in arr:
        for k in ("name", "phase", "description", "license", "fetch_method"):
            assert k in m


def test_cli_plan_short() -> None:
    mod = _load_module()
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = mod.main(["--plan", "short"])
    assert rc == 0
    arr = json.loads(buf.getvalue())
    assert all(m["phase"] == "short" for m in arr)
