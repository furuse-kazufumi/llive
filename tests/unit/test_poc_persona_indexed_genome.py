# SPDX-License-Identifier: Apache-2.0
"""Unit tests for scripts/poc_persona_indexed_genome.py.

persona-indexed(モザイク)ゲノムの効果判定 PoC の決定論的 verdict を固定。
proxy・CPU・LLM/Docker ゼロ。[[goal_surpass_mythos_evolutionary]] 周辺の genome 表現検証。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import poc_persona_indexed_genome as pig  # noqa: E402


def test_affinity_matrix_shape():
    A, ids = pig.affinity_matrix()
    assert A.shape[0] == len(ids) >= 10
    assert A.shape[1] == pig.N_FACTORS == 10
    assert ((A >= 0.0) & (A <= 1.0)).all()


def test_indexed_decode_is_mosaic():
    A, _ids = pig.affinity_matrix()
    encs = pig.make_encodings(A)
    P = A.shape[0]
    # argmax/因子 の index ベクトル → phenotype は per-factor 最大 envelope。
    argmax_genome = A.argmax(axis=0)
    pheno = encs["indexed"].decode(argmax_genome)
    np.testing.assert_allclose(pheno, A.max(axis=0))
    # single decode = その persona の行そのもの。
    assert np.allclose(encs["single"].decode(0), A[0])
    assert 0 <= int(argmax_genome.max()) < P


def test_single_cannot_reach_mosaic_floor_positive():
    """mosaic target には単一ペルソナで届かない (構造的 floor > 0)。"""
    A, _ids = pig.affinity_matrix()
    target_mosaic = A.max(axis=0)
    floor, _idx = pig._single_floor(A, target_mosaic)
    assert floor > 0.05  # eps より大きい構造的頭打ち


def test_verdict_indexed_has_effect():
    """決定論 verdict: indexed はモザイク target で single を構造的に超える。"""
    out = pig.run(pop=24, gens=80, seed=0, eps=0.05)
    v = out["verdict"]
    mt = v["mosaic_target"]
    # single は floor 止まり (未到達)、indexed は到達。
    assert mt["single_reaches"] is False
    assert mt["indexed_reaches"] is True
    assert mt["headroom_filled_by_indexed(floor - indexed)"] > 0.05
    assert v["indexed_has_effect"] is True
    # single で到達可能な target では indexed も到達 (利得は無いが劣後もしない)。
    assert v["single_target"]["indexed_reaches"] is True


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
