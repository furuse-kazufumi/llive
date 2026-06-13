# SPDX-License-Identifier: Apache-2.0
"""GENOME_VERSION 版管理定数 — DIV-03 pytest.

addendum §DIV-03: 19/38/40 の 3 表現に版タグを付け、新 dim を足さないことを
assertion ヘルパで守る。
"""
from __future__ import annotations

import numpy as np
import pytest

from llive.perf.evolutionary.genome_version import (
    FACTOR_GENOME_DIM,
    FLAT_GENOME_DIM,
    GENOME_FACTORS,
    GENOME_V1_FLAT,
    GENOME_V2_SIGMA,
    GENOME_VERSION,
    GENOME_VERSION_DIMS,
    KNOWN_GENOME_VERSIONS,
    assert_factor_dim,
    assert_flat_dim,
    assert_no_fourth_dim,
    assert_sigma_view_dim,
    dispatch_target,
    expected_dim,
)


# ---------------------------------------------------------------------------
# 定数値 (addendum §DIV-03 の正典)
# ---------------------------------------------------------------------------


def test_version_tag_values() -> None:
    assert GENOME_V1_FLAT == "v0.C-19"
    assert GENOME_V2_SIGMA == "v0.D-38-view"
    assert GENOME_FACTORS == "v0.F-40"


def test_current_default_is_factors() -> None:
    """現行 default は 40-dim factor matrix。"""
    assert GENOME_VERSION == GENOME_FACTORS
    assert GENOME_VERSION == "v0.F-40"


def test_known_versions_are_three() -> None:
    assert KNOWN_GENOME_VERSIONS == (GENOME_V1_FLAT, GENOME_V2_SIGMA, GENOME_FACTORS)
    assert len(KNOWN_GENOME_VERSIONS) == 3


def test_canonical_dims() -> None:
    assert FLAT_GENOME_DIM == 19
    assert FACTOR_GENOME_DIM == 40  # 10 * 4
    assert GENOME_VERSION_DIMS[GENOME_V1_FLAT] == 19
    assert GENOME_VERSION_DIMS[GENOME_V2_SIGMA] == 38
    assert GENOME_VERSION_DIMS[GENOME_FACTORS] == 40


# ---------------------------------------------------------------------------
# assertion ヘルパ — 不変条件 (len flat==19, c_factors.flatten==40)
# ---------------------------------------------------------------------------


def test_assert_flat_dim_accepts_19() -> None:
    assert_flat_dim(np.zeros(19))  # no raise


def test_assert_flat_dim_rejects_non_19() -> None:
    with pytest.raises(AssertionError):
        assert_flat_dim(np.zeros(20))
    with pytest.raises(AssertionError):
        assert_flat_dim(np.zeros(40))


def test_assert_factor_dim_accepts_40() -> None:
    assert_factor_dim(np.zeros(40))
    # 2D (10, 4) も flatten で 40
    assert_factor_dim(np.zeros((10, 4)))


def test_assert_factor_dim_rejects_non_40() -> None:
    with pytest.raises(AssertionError):
        assert_factor_dim(np.zeros(38))
    with pytest.raises(AssertionError):
        assert_factor_dim(np.zeros((10, 5)))  # 50-dim 拡張は禁止


def test_assert_sigma_view_dim_accepts_38() -> None:
    assert_sigma_view_dim(np.zeros(38))  # = 2 * 19


def test_assert_sigma_view_dim_rejects_non_38() -> None:
    with pytest.raises(AssertionError):
        assert_sigma_view_dim(np.zeros(40))


def test_assert_no_fourth_dim_holds() -> None:
    """既知 dim 集合は {19, 38, 40} の 3 値のみ — 4 つ目を足していない。"""
    assert_no_fourth_dim()  # no raise
    assert set(GENOME_VERSION_DIMS.values()) == {19, 38, 40}


# ---------------------------------------------------------------------------
# dispatch / expected_dim
# ---------------------------------------------------------------------------


def test_expected_dim_per_version() -> None:
    assert expected_dim(GENOME_V1_FLAT) == 19
    assert expected_dim(GENOME_V2_SIGMA) == 38
    assert expected_dim(GENOME_FACTORS) == 40


def test_expected_dim_unknown_raises() -> None:
    with pytest.raises(KeyError):
        expected_dim("v9.Z-99")


def test_dispatch_target_known_passthrough() -> None:
    """CMA-ES (DIV-01) は GENOME_FACTORS タグの個体のみ対象 — dispatch は fail-closed。"""
    assert dispatch_target(GENOME_FACTORS) == GENOME_FACTORS
    assert dispatch_target(GENOME_V1_FLAT) == GENOME_V1_FLAT


def test_dispatch_target_unknown_rejected() -> None:
    with pytest.raises(KeyError):
        dispatch_target("unknown-tag")
