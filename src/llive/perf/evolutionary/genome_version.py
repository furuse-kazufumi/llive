# SPDX-License-Identifier: Apache-2.0
"""GENOME_VERSION 版管理定数 — llive v0.F DIV-03 (genome diversity addendum).

19-dim flat (v0.C) / 38-dim σ-augmented 派生 view (v0.D SR-01) / 40-dim factor
matrix (v0.F) の **3 表現** に版タグを付け、混在集団を許すための定数群。

> **大原則 (addendum §1-2 / premap §5-2): 新 dim を一切足さない。**
> 既存 3 表現に **ラベルを付けるだけ**。本 module は dimensionality を増やさず、
> 既存の不変条件 (flat==19 / σ-augmented==38 / c_factors.flatten==40) を
> assertion ヘルパで守ることに専念する。

# 3 表現の出典 (premap §2.1 / §2.2)

* **19-dim flat (canonical)** — `Genome` / `LIVE_VARIANT_GENOME_BOUNDS`、
  `llive_variant.py:73` の ``assert len(...) == 19``。現行唯一の "flat genome"。
* **38-dim σ-augmented (派生 view)** — 19-dim object に σ を同伴した
  self-adaptive ES 表現。``pack_self_adaptive_bounds`` が任意 n を ``2n`` にする
  汎用関数の「19 を渡したときの結果」(``self_adaptive.py:142``)。**固定 canonical
  ではない**。誤って「38-dim canonical」と再解釈する破綻を防ぐためタグ名で明示する。
* **40-dim factor matrix** — 10 思考因子 × 4 メモリ層の 2D matrix chromosome
  (``ThoughtFactorPerLayerChromosome``)。``Genome3D.c_factors`` に field 統合済。
  CMA-ES (DIV-01) はこの 40-dim flatten のみを対象にする。

# 使い方

```python
from llive.perf.evolutionary.genome_version import (
    GENOME_VERSION, dispatch_target, assert_flat_dim, assert_factor_dim,
)

# 現行 default は 40-dim factor matrix
assert GENOME_VERSION == "v0.F-40"

# CMA-ES (DIV-01) は GENOME_FACTORS タグの個体のみを対象にする operator dispatch
if dispatch_target(tag) == GENOME_FACTORS:
    ...  # CMA-ES operator を適用

# 不変条件を破る変更が混入したら即座に AssertionError
assert_flat_dim(genome.as_array())          # len == 19
assert_factor_dim(chromosome.as_flat())     # 40 (= 10 * 4)
```

References:
* addendum: ``docs/requirements_v0.F_genome_diversity_addendum.md`` §DIV-03.
* premap: ``docs/SPEC_COHERENCE_v0.J_premap.md`` §2.3.
"""
from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------------------
# Version tags (addendum §DIV-03)
# ---------------------------------------------------------------------------

#: 19-dim flat scalar genome (v0.C canonical, ``llive_variant.py:73`` assert==19).
GENOME_V1_FLAT: str = "v0.C-19"

#: 19-dim object + 19 σ の派生 view (v0.D SR-01, ``self_adaptive.py:142``, 2n)。
#: 固定 canonical ではなく「19 を渡したときの self-adaptive 表現」のタグ。
GENOME_V2_SIGMA: str = "v0.D-38-view"

#: 10×4 factor matrix (v0.F, ``thought_factor_per_layer.py``)。
GENOME_FACTORS: str = "v0.F-40"

#: 現行 default。CMA-ES (DIV-01) は ``GENOME_FACTORS`` タグの個体のみを対象にする。
GENOME_VERSION: str = GENOME_FACTORS

#: 認識される全版タグの集合 (順序保持の tuple)。
KNOWN_GENOME_VERSIONS: tuple[str, ...] = (
    GENOME_V1_FLAT,
    GENOME_V2_SIGMA,
    GENOME_FACTORS,
)


# ---------------------------------------------------------------------------
# Canonical dimensionalities (新 dim を足さない — premap §5-2)
# ---------------------------------------------------------------------------

#: flat scalar genome の固定 dim。``llive_variant.py`` の assert と一致させる。
FLAT_GENOME_DIM: int = 19

#: 思考因子数 × メモリ層数 = factor matrix の flatten dim。
NUM_THOUGHT_FACTORS: int = 10
NUM_MEMORY_LAYERS: int = 4
FACTOR_GENOME_DIM: int = NUM_THOUGHT_FACTORS * NUM_MEMORY_LAYERS  # 40

#: 各版タグ → flatten 後の固定 dim (38 は汎用 2n の結果なので「19 を渡した値」)。
GENOME_VERSION_DIMS: dict[str, int] = {
    GENOME_V1_FLAT: FLAT_GENOME_DIM,            # 19
    GENOME_V2_SIGMA: 2 * FLAT_GENOME_DIM,       # 38 (= pack_self_adaptive_bounds(19))
    GENOME_FACTORS: FACTOR_GENOME_DIM,          # 40
}


# ---------------------------------------------------------------------------
# Assertion helpers (不変条件を守る)
# ---------------------------------------------------------------------------


def _flatten_len(arr: np.ndarray | object) -> int:
    """ndarray / flatten 可能オブジェクトの flatten 後要素数を返す。"""
    a = np.asarray(arr)
    return int(a.size)


def assert_flat_dim(arr: np.ndarray | object) -> None:
    """flat scalar genome (v0.C) が **19-dim** であることを検証する。

    Raises:
        AssertionError: flatten 後の要素数が 19 でない場合。
    """
    n = _flatten_len(arr)
    assert n == FLAT_GENOME_DIM, (
        f"flat genome must be {FLAT_GENOME_DIM}-dim (v0.C canonical), got {n}"
    )


def assert_sigma_view_dim(arr: np.ndarray | object) -> None:
    """σ-augmented 派生 view (v0.D) が **38-dim** (= 2 × 19) であることを検証する。

    38 は固定 canonical ではなく ``pack_self_adaptive_bounds(19)`` の結果。
    本ヘルパは「19-dim を渡した self-adaptive 表現」であることを確認する。

    Raises:
        AssertionError: flatten 後の要素数が 38 でない場合。
    """
    n = _flatten_len(arr)
    expected = 2 * FLAT_GENOME_DIM
    assert n == expected, (
        f"sigma-augmented view must be {expected}-dim "
        f"(= 2 x {FLAT_GENOME_DIM}, v0.D SR-01 derived view), got {n}"
    )


def assert_factor_dim(arr: np.ndarray | object) -> None:
    """factor matrix (v0.F) が flatten で **40-dim** (= 10 × 4) であることを検証する。

    CMA-ES (DIV-01) が対象にする continuous サブ空間の dim 不変条件。

    Raises:
        AssertionError: flatten 後の要素数が 40 でない場合。
    """
    n = _flatten_len(arr)
    assert n == FACTOR_GENOME_DIM, (
        f"factor genome must flatten to {FACTOR_GENOME_DIM}-dim "
        f"(= {NUM_THOUGHT_FACTORS} factors x {NUM_MEMORY_LAYERS} layers), got {n}"
    )


def assert_no_fourth_dim() -> None:
    """3 表現以外の独立 dim を導入していないことの不変条件 (premap §5-2)。

    ``GENOME_VERSION_DIMS`` が ``{19, 38, 40}`` の 3 値だけであることを確認する。
    新しい dim を黙って足すと本 assertion が破れる。

    Raises:
        AssertionError: 既知 dim 集合が ``{19, 38, 40}`` から逸脱した場合。
    """
    dims = set(GENOME_VERSION_DIMS.values())
    expected = {FLAT_GENOME_DIM, 2 * FLAT_GENOME_DIM, FACTOR_GENOME_DIM}
    assert dims == expected, (
        f"no fourth independent dim allowed; expected {sorted(expected)}, "
        f"got {sorted(dims)}"
    )


def expected_dim(version: str) -> int:
    """版タグに対応する flatten 後の固定 dim を返す。

    Raises:
        KeyError: 未知の版タグ。
    """
    if version not in GENOME_VERSION_DIMS:
        raise KeyError(
            f"unknown genome version tag: {version!r} "
            f"(known: {KNOWN_GENOME_VERSIONS})"
        )
    return GENOME_VERSION_DIMS[version]


def dispatch_target(version: str) -> str:
    """operator dispatch 用に版タグを正規化して返す (DIV-01 の dispatch 条件)。

    CMA-ES は ``GENOME_FACTORS`` タグの個体のみを対象にする。本ヘルパは
    渡された版タグが既知であることを検証し、そのまま返す。未知タグは拒否
    (fail-closed) する。

    Raises:
        KeyError: 未知の版タグ。
    """
    if version not in KNOWN_GENOME_VERSIONS:
        raise KeyError(
            f"unknown genome version tag: {version!r} "
            f"(known: {KNOWN_GENOME_VERSIONS})"
        )
    return version


__all__ = [
    "FACTOR_GENOME_DIM",
    "FLAT_GENOME_DIM",
    "GENOME_FACTORS",
    "GENOME_V1_FLAT",
    "GENOME_V2_SIGMA",
    "GENOME_VERSION",
    "GENOME_VERSION_DIMS",
    "KNOWN_GENOME_VERSIONS",
    "NUM_MEMORY_LAYERS",
    "NUM_THOUGHT_FACTORS",
    "assert_factor_dim",
    "assert_flat_dim",
    "assert_no_fourth_dim",
    "assert_sigma_view_dim",
    "dispatch_target",
    "expected_dim",
]
