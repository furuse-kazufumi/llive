# SPDX-License-Identifier: Apache-2.0
"""KAR ingest manifest (llive.kar.manifests) の単体テスト."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

import pytest

from llive.kar.manifests import list_manifests, main, total_size_gb


def test_list_manifests_has_three_phases() -> None:
    all_m = list_manifests()
    phases = {m.phase for m in all_m}
    assert phases == {"short", "mid", "long"}


def test_phase_filter() -> None:
    short = list_manifests("short")
    assert all(m.phase == "short" for m in short)
    assert len(short) >= 2


def test_total_size_estimate() -> None:
    assert total_size_gb("short") > 0
    assert total_size_gb(None) > total_size_gb("short")


def test_cli_summary_emits_json() -> None:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--summary"])
    assert rc == 0
    out = json.loads(buf.getvalue())
    assert set(out.keys()) == {"short_gb", "mid_gb", "long_gb", "total_gb"}
    assert out["total_gb"] == pytest.approx(out["short_gb"] + out["mid_gb"] + out["long_gb"])


def test_cli_list_emits_array() -> None:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--list"])
    assert rc == 0
    arr = json.loads(buf.getvalue())
    assert isinstance(arr, list)
    assert len(arr) >= 5
    for m in arr:
        for k in ("name", "phase", "description", "license", "fetch_method"):
            assert k in m


def test_cli_plan_short() -> None:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--plan", "short"])
    assert rc == 0
    arr = json.loads(buf.getvalue())
    assert all(m["phase"] == "short" for m in arr)
