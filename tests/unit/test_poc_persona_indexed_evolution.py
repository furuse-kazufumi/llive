# SPDX-License-Identifier: Apache-2.0
"""Unit tests for scripts/poc_persona_indexed_evolution.py.

実 Genome3D 個体 + 進化ループによる persona_index ON vs OFF ablation の
決定論 verdict を固定。proxy・CPU・LLM/Docker ゼロ。

[[project_persona_genome_integration]] / 段階1 persona-indexed genome の
production 採用後のフィジビリティを大 PoC で gate する。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import poc_persona_indexed_evolution as pie  # noqa: E402


def test_affinity_matrix_and_mosaic_target_shape() -> None:
    A, ids = pie._affinity_matrix()
    assert A.shape == (len(ids), pie.NUM_THOUGHT_FACTORS)
    assert len(ids) >= 10
    target = pie._mosaic_target(A)
    assert target.shape == (pie.NUM_THOUGHT_FACTORS,)
    # envelope は各列の max なので各 persona 行以上
    assert np.all(target >= A.max(axis=0) - 1e-12)


def test_single_structural_floor_positive_for_mosaic() -> None:
    """mosaic target には単一ペルソナで届かない (floor > eps)."""
    A, _ids = pie._affinity_matrix()
    target = pie._mosaic_target(A)
    floor = pie._single_structural_floor(A, target)
    assert floor > 0.05


def test_phenotype_off_is_layer_mean_10dim() -> None:
    from llive.perf.evolutionary.thought_factor_per_layer import (
        ThoughtFactorPerLayerChromosome as C,
    )

    g = pie._base_genome(C.default())
    pheno = pie.phenotype_off(g)
    assert pheno.shape == (pie.NUM_THOUGHT_FACTORS,)
    # default は全 cell 0.5 → 層平均も 0.5
    assert np.allclose(pheno, 0.5)


def test_phenotype_on_requires_persona_index() -> None:
    from llive.perf.evolutionary.thought_factor_per_layer import (
        ThoughtFactorPerLayerChromosome as C,
    )

    import pytest

    g_none = pie._base_genome(C.default())
    with pytest.raises(ValueError):
        pie.phenotype_on(g_none)


def test_verdict_persona_index_contributes_deterministic() -> None:
    """決定論 verdict: ON はモザイク target で OFF を寄与で上回り floor を埋める."""
    out = pie.run(pop=30, gens=60, seed=0, eps=0.05)
    v = out["verdict"]
    # ON は eps 到達, OFF は未到達
    assert v["on_reaches_eps"] is True
    assert v["off_reaches_eps"] is False
    # ON が OFF より近い (off - on > eps)
    assert v["on_minus_off(off - on, >0 = on closer)"] > 0.05
    # ON が single 構造 floor を埋めた
    assert v["headroom_filled_by_on(floor - on)"] > 0.05
    assert v["persona_index_contributes"] is True
    # ON best individual は persona_index を保持
    assert out["results"]["persona_index_on"]["best_persona_index"] is not None
    # OFF best individual は persona_index を持たない
    assert out["results"]["persona_index_off"]["best_persona_index"] is None


def test_run_is_reproducible_under_same_seed() -> None:
    o1 = pie.run(pop=20, gens=30, seed=7, eps=0.05)
    o2 = pie.run(pop=20, gens=30, seed=7, eps=0.05)
    assert (
        o1["results"]["persona_index_on"]["best_dist"]
        == o2["results"]["persona_index_on"]["best_dist"]
    )
    assert (
        o1["results"]["persona_index_off"]["best_dist"]
        == o2["results"]["persona_index_off"]["best_dist"]
    )


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
