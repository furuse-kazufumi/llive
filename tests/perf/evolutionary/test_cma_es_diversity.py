# SPDX-License-Identifier: Apache-2.0
"""CMA-ES diversity loop 配線 — DIV-01 pytest.

addendum §DIV-01: CMA-ES の ask() 候補を NoveltyScorer / novelty_lane で評価、
fitness+novelty を MultiObjectiveSelector で合成して tell()、候補を MAPElitesGrid に
behavior descriptor 化して投入。frozen index は固定 clip し mutate しない。
"""
from __future__ import annotations

import numpy as np
import pytest

from llive.perf.evolutionary.cma_es import CMAESAdapter
from llive.perf.evolutionary.cma_es_diversity import (
    CMAESDiversityDriver,
    CMAESDiversityGenerationResult,
    candidate_to_map_elites_features,
    candidate_to_thought_features,
    parse_frozen_factor_indices,
)
from llive.perf.evolutionary.frozen_gene import FreezeReason, FrozenGene
from llive.perf.evolutionary.genome_version import FACTOR_GENOME_DIM

_SIG = b"\x11" * 32


def _sphere(x: np.ndarray) -> float:
    return float(np.sum((x - 0.5) ** 2))


def _frozen(path: str, expiry: str = "2099-01-01T00:00:00Z") -> FrozenGene:
    return FrozenGene(
        gene_path=path,
        reason=FreezeReason.ETHICS,
        signature=_SIG,
        expiry_iso=expiry,
    )


# ---------------------------------------------------------------------------
# Construction & 40-dim 専用 guard
# ---------------------------------------------------------------------------


def test_driver_defaults_to_40dim() -> None:
    d = CMAESDiversityDriver(rng=np.random.default_rng(0))
    assert d.adapter is not None
    assert d.adapter.dim == FACTOR_GENOME_DIM == 40


def test_driver_rejects_non_40dim_adapter() -> None:
    """c_factors 40-dim 専用 — 別 dim の adapter は拒否 (新 dim を足さない)。"""
    bad = CMAESAdapter(dim=19)
    with pytest.raises(ValueError, match="40-dim only"):
        CMAESDiversityDriver(adapter=bad)


def test_driver_negative_novelty_weight_rejected() -> None:
    with pytest.raises(ValueError):
        CMAESDiversityDriver(novelty_weight=-0.1)


# ---------------------------------------------------------------------------
# step / run — loop が candidates を回す
# ---------------------------------------------------------------------------


def test_step_returns_result_with_lambda_candidates() -> None:
    d = CMAESDiversityDriver(rng=np.random.default_rng(1))
    res = d.step(_sphere)
    assert isinstance(res, CMAESDiversityGenerationResult)
    lam = d.adapter.population_size  # type: ignore[union-attr]
    assert res.candidates.shape == (lam, 40)
    assert res.fitnesses.shape == (lam,)
    assert res.novelty_scores.shape == (lam,)


def test_run_advances_generation() -> None:
    d = CMAESDiversityDriver(rng=np.random.default_rng(2))
    results = d.run(_sphere, generations=4)
    assert len(results) == 4
    assert [r.generation for r in results] == [0, 1, 2, 3]
    assert d.generation == 4


def test_run_requires_positive_generations() -> None:
    d = CMAESDiversityDriver(rng=np.random.default_rng(3))
    with pytest.raises(ValueError):
        d.run(_sphere, generations=0)


# ---------------------------------------------------------------------------
# MAP-Elites grid に cell が増える
# ---------------------------------------------------------------------------


def test_grid_cells_grow_over_generations() -> None:
    """CMA-ES 候補を behavior descriptor 化して投入 → grid cell が増える。"""
    d = CMAESDiversityDriver(rng=np.random.default_rng(4))
    cov0 = d.grid.coverage  # type: ignore[union-attr]
    assert cov0 == 0.0
    d.run(_sphere, generations=8)
    assert d.grid.n_filled >= 1  # type: ignore[union-attr]
    assert d.grid.coverage > 0.0  # type: ignore[union-attr]


def test_grid_uses_existing_grid_instance() -> None:
    """渡した既存 MAPElitesGrid を再定義せず使う (extend-only)。"""
    from llive.perf.evolutionary.quality_diversity import MAPElitesGrid

    grid = MAPElitesGrid(n_bins_per_axis=3)
    d = CMAESDiversityDriver(grid=grid, rng=np.random.default_rng(5))
    d.run(_sphere, generations=5)
    assert d.grid is grid
    assert grid.n_filled >= 1


# ---------------------------------------------------------------------------
# novelty + fitness が回る (selector / archive)
# ---------------------------------------------------------------------------


def test_novelty_archive_accumulates() -> None:
    d = CMAESDiversityDriver(rng=np.random.default_rng(6))
    assert len(d.novelty_scorer.archive) == 0  # type: ignore[union-attr]
    d.run(_sphere, generations=3)
    lam = d.adapter.population_size  # type: ignore[union-attr]
    assert len(d.novelty_scorer.archive) == 3 * lam  # type: ignore[union-attr]


def test_selected_ids_nonempty_and_subset() -> None:
    d = CMAESDiversityDriver(rng=np.random.default_rng(7))
    res = d.step(_sphere)
    lam = d.adapter.population_size  # type: ignore[union-attr]
    valid_ids = {f"g0_c{i}" for i in range(lam)}
    assert len(res.selected_ids) > 0
    assert set(res.selected_ids).issubset(valid_ids)


def test_sigma_updates_via_tell() -> None:
    """tell() が呼ばれ step-size が初期値から変化する (loop が回っている証跡)。"""
    d = CMAESDiversityDriver(rng=np.random.default_rng(8))
    sigma0 = d.adapter.sigma  # type: ignore[union-attr]
    results = d.run(_sphere, generations=6)
    assert results[-1].sigma != pytest.approx(sigma0)


# ---------------------------------------------------------------------------
# frozen gene ガード — 固定 clip / mutate しない
# ---------------------------------------------------------------------------


def test_parse_frozen_cell_index() -> None:
    idx = parse_frozen_factor_indices([_frozen("c_factors[0][0]")])
    assert idx == [0]


def test_parse_frozen_row_expands_all_layers() -> None:
    # factor 1 row -> flat indices 4,5,6,7 (n_layers=4)
    idx = parse_frozen_factor_indices([_frozen("c_factors[1]")])
    assert idx == [4, 5, 6, 7]


def test_parse_frozen_ignores_non_cfactors_and_expired() -> None:
    genes = [
        _frozen("C-prompt.persona_set[7]"),  # 別 chromosome → 無視
        _frozen("c_factors[2][1]", expiry="2000-01-01T00:00:00Z"),  # 期限切れ → 無視
    ]
    assert parse_frozen_factor_indices(genes, now_iso="2026-01-01T00:00:00Z") == []


def test_parse_frozen_out_of_range_dropped() -> None:
    # factor 99 / layer 99 は範囲外 → drop
    assert parse_frozen_factor_indices([_frozen("c_factors[99][0]")]) == []
    assert parse_frozen_factor_indices([_frozen("c_factors[0][99]")]) == []


def test_frozen_indices_held_constant_across_candidates() -> None:
    """frozen index は全候補で同一値に固定され mutate されない。"""
    genes = [_frozen("c_factors[0][0]"), _frozen("c_factors[3]")]
    d = CMAESDiversityDriver(frozen_genes=genes, rng=np.random.default_rng(9))
    frozen = d.frozen_indices
    assert frozen == [0, 12, 13, 14, 15]  # factor3 row = 12..15
    for _ in range(4):
        res = d.step(_sphere)
        sub = res.candidates[:, frozen]
        # 各列の全行が等しい (= 固定)
        for j in range(sub.shape[1]):
            assert np.allclose(sub[:, j], sub[0, j])


def test_frozen_value_stable_over_generations() -> None:
    """frozen 値は世代を跨いでも anchor から動かない。"""
    genes = [_frozen("c_factors[5][2]")]  # flat index 22
    d = CMAESDiversityDriver(frozen_genes=genes, rng=np.random.default_rng(10))
    idx = d.frozen_indices[0]
    vals = []
    for _ in range(5):
        res = d.step(_sphere)
        vals.append(res.candidates[0, idx])
    assert np.allclose(vals, vals[0])


def test_no_frozen_genes_no_clip() -> None:
    """frozen 無しなら通常 CMA-ES 候補 (候補間でばらつく)。"""
    d = CMAESDiversityDriver(rng=np.random.default_rng(11))
    assert d.frozen_indices == []
    res = d.step(_sphere)
    # 少なくともいくつかの列は候補間でばらついている
    col_unique = [len(np.unique(np.round(res.candidates[:, j], 8))) for j in range(40)]
    assert max(col_unique) > 1


# ---------------------------------------------------------------------------
# behavior descriptor helpers
# ---------------------------------------------------------------------------


def test_thought_features_shape_and_range() -> None:
    x = np.full(40, 0.7)
    feats = candidate_to_thought_features(x)
    assert len(feats) == 2
    assert all(0.0 <= f <= 1.0 for f in feats)
    assert feats == pytest.approx((0.7, 0.7))


def test_map_elites_features_4axis() -> None:
    x = np.linspace(0.0, 1.0, 40)
    feats = candidate_to_map_elites_features(x)
    assert len(feats) == 4
    # persona axis 0 = flatten mean
    assert feats[0] == pytest.approx(float(x.mean()))


def test_minimize_vs_maximize_both_run() -> None:
    d_min = CMAESDiversityDriver(rng=np.random.default_rng(12))
    d_max = CMAESDiversityDriver(rng=np.random.default_rng(12))
    r_min = d_min.run(_sphere, generations=3, minimize=True)
    r_max = d_max.run(lambda x: -_sphere(x), generations=3, minimize=False)
    assert len(r_min) == 3 and len(r_max) == 3
