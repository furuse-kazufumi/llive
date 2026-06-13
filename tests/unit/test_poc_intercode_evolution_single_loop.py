# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the single-loop 新主経路 verdict (poc_intercode_evolution).

`build_single_loop_verdict` は、オーケストラ (Phase B 条件付き保留, 2026-05-28) に伴う
新主経路 = 進化チャンピオン=単一個体を 1 ループで deploy したカバレッジを naive 単一と
比較する pure 関数。pop_coverage (orchestra) verdict と独立。
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import poc_intercode_evolution as pie  # noqa: E402


def test_evolved_beats_naive():
    v = pie.build_single_loop_verdict(0.714, 0.429)
    assert v["evolved_champion_single_coverage"] == 0.714
    assert v["naive_champion_single_coverage"] == 0.429
    assert v["delta(evolved-naive)"] == 0.285
    assert v["evolved_champion_beats_naive"] is True
    assert v["evolved_champion_ties_naive"] is False


def test_ties_naive():
    v = pie.build_single_loop_verdict(0.5, 0.5)
    assert v["delta(evolved-naive)"] == 0.0
    assert v["evolved_champion_beats_naive"] is False
    assert v["evolved_champion_ties_naive"] is True


def test_loses_to_naive():
    v = pie.build_single_loop_verdict(0.3, 0.5)
    assert v["delta(evolved-naive)"] == -0.2
    assert v["evolved_champion_beats_naive"] is False
    assert v["evolved_champion_ties_naive"] is False


def test_deploy_cost_advertises_1x_vs_kx():
    """新主経路の核 = deploy=1 ループ (orchestra の 1/k)。"""
    v = pie.build_single_loop_verdict(0.7, 0.5)
    assert "1x" in v["deploy_cost"]
    assert "kx" in v["deploy_cost"] or "k 倍" in v["deploy_cost"]
    assert "1/k" in v["deploy_cost"]


def test_note_references_phase_b_and_orchestra():
    """note は Phase B (オーケストラ) 条件付き保留と pop_coverage 独立を明記。"""
    v = pie.build_single_loop_verdict(0.7, 0.5)
    assert "Phase B" in v["note"]
    assert "pop_coverage" in v["note"] or "orchestra" in v["note"]


def test_eps_within_tolerance_is_tie():
    """eps 以内 (浮動小数誤差レベル) は tie 扱い。"""
    v = pie.build_single_loop_verdict(0.5, 0.5 + 1e-12)
    # |delta| <= eps (1e-9) → ties_naive=True、beats_naive=False
    assert v["evolved_champion_ties_naive"] is True
    assert v["evolved_champion_beats_naive"] is False


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
