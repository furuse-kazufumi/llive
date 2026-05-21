# SPDX-License-Identifier: Apache-2.0
"""PersonaOverlapPenalty + MAP-Elites grid (v0.E E.17 / CE-25 / CE-26) — unit tests."""

from __future__ import annotations

import numpy as np
import pytest

from llive.perf.evolutionary import (
    Genome,
    GenomeBounds,
    Individual,
    MAPElitesCell,
    MAPElitesGrid,
    PersonaComposition,
    PersonaOverlapPenalty,
    default_map_elites_features,
    default_persona_features,
    default_thought_features,
    persona_dissimilarity,
    random_persona_composition,
)


def _make_individual(seed: int = 0) -> Individual:
    """3-dim Genome を持つ最小 Individual を作る (cell test 用)."""
    bounds = GenomeBounds(lower=(0.0, 0.0, 0.0), upper=(1.0, 1.0, 1.0))
    rng = np.random.default_rng(seed)
    g = Genome.from_values(
        rng.uniform(0.0, 1.0, size=3), bounds=bounds, labels=()
    )
    return Individual.from_genome(g)


# ---------------------------------------------------------------------------
# 1. PersonaOverlapPenalty
# ---------------------------------------------------------------------------


class TestPersonaOverlapPenalty:
    def test_construct_default_lambda(self) -> None:
        p = PersonaOverlapPenalty()
        assert p.lambda_ == 0.5

    def test_negative_lambda_raises(self) -> None:
        with pytest.raises(ValueError):
            PersonaOverlapPenalty(lambda_=-0.1)

    def test_apply_empty_returns_empty(self) -> None:
        p = PersonaOverlapPenalty(lambda_=0.5)
        out = p.apply([], [])
        assert out.shape == (0,)

    def test_apply_size_mismatch_raises(self) -> None:
        rng = np.random.default_rng(0)
        c = random_persona_composition(rng, n=2)
        p = PersonaOverlapPenalty(lambda_=0.5)
        with pytest.raises(ValueError):
            p.apply([c], [1.0, 2.0])

    def test_apply_single_individual_no_bonus(self) -> None:
        rng = np.random.default_rng(0)
        c = random_persona_composition(rng, n=2)
        p = PersonaOverlapPenalty(lambda_=0.5)
        out = p.apply([c], [3.14])
        np.testing.assert_allclose(out, [3.14])

    def test_apply_identical_comps_no_bonus(self) -> None:
        """同じ comp が並ぶと dissimilarity 0 → ボーナス 0."""
        c = PersonaComposition(persona_ids=("oka-kiyoshi",), weights=(1.0,))
        p = PersonaOverlapPenalty(lambda_=1.0)
        out = p.apply([c, c, c], [1.0, 2.0, 3.0])
        np.testing.assert_allclose(out, [1.0, 2.0, 3.0])

    def test_apply_distinct_comps_get_positive_bonus(self) -> None:
        c1 = PersonaComposition(persona_ids=("oka-kiyoshi",), weights=(1.0,))
        c2 = PersonaComposition(persona_ids=("feynman",), weights=(1.0,))
        p = PersonaOverlapPenalty(lambda_=1.0)
        out = p.apply([c1, c2], [0.0, 0.0])
        # どちらも他方との dissimilarity > 0 なので bonus > 0
        assert out[0] > 0.0
        assert out[1] > 0.0
        # symmetric なので 2 個体の bonus は等しいはず
        assert out[0] == pytest.approx(out[1])

    def test_apply_lambda_zero_passthrough(self) -> None:
        rng = np.random.default_rng(0)
        comps = [random_persona_composition(rng, n=2) for _ in range(5)]
        base = [1.0, 2.0, 3.0, 4.0, 5.0]
        p = PersonaOverlapPenalty(lambda_=0.0)
        out = p.apply(comps, base)
        np.testing.assert_allclose(out, base)

    def test_apply_larger_lambda_amplifies_bonus(self) -> None:
        c1 = PersonaComposition(persona_ids=("oka-kiyoshi",), weights=(1.0,))
        c2 = PersonaComposition(persona_ids=("feynman",), weights=(1.0,))
        base = [0.0, 0.0]
        p1 = PersonaOverlapPenalty(lambda_=0.5)
        p2 = PersonaOverlapPenalty(lambda_=2.0)
        out1 = p1.apply([c1, c2], base)
        out2 = p2.apply([c1, c2], base)
        # λ が 4 倍なら bonus も 4 倍
        np.testing.assert_allclose(out2, out1 * 4.0)

    def test_mean_dissimilarity_empty(self) -> None:
        p = PersonaOverlapPenalty(lambda_=0.5)
        out = p.mean_dissimilarity([])
        assert out.shape == (0,)

    def test_mean_dissimilarity_single(self) -> None:
        rng = np.random.default_rng(0)
        c = random_persona_composition(rng, n=2)
        p = PersonaOverlapPenalty(lambda_=0.5)
        out = p.mean_dissimilarity([c])
        np.testing.assert_allclose(out, [0.0])

    def test_mean_dissimilarity_matches_pairwise(self) -> None:
        """3 個体で手計算と一致するか."""
        c1 = PersonaComposition(persona_ids=("oka-kiyoshi",), weights=(1.0,))
        c2 = PersonaComposition(persona_ids=("feynman",), weights=(1.0,))
        c3 = PersonaComposition(persona_ids=("newton",), weights=(1.0,))
        p = PersonaOverlapPenalty(lambda_=0.5)
        out = p.mean_dissimilarity([c1, c2, c3])
        # 各自他 2 名との平均
        d12 = persona_dissimilarity(c1, c2)
        d13 = persona_dissimilarity(c1, c3)
        d23 = persona_dissimilarity(c2, c3)
        expected = [
            (d12 + d13) / 2,
            (d12 + d23) / 2,
            (d13 + d23) / 2,
        ]
        np.testing.assert_allclose(out, expected)


# ---------------------------------------------------------------------------
# 2. MAPElitesGrid — construction / validation
# ---------------------------------------------------------------------------


class TestMAPElitesGridConstruct:
    def test_default_construct(self) -> None:
        g = MAPElitesGrid()
        assert g.n_bins_per_axis == 5
        assert g.n_filled == 0
        assert g.coverage == 0.0
        assert g.best is None
        assert g.n_cells_total == 5 ** 4

    def test_invalid_bins_zero_raises(self) -> None:
        with pytest.raises(ValueError):
            MAPElitesGrid(n_bins_per_axis=0)

    def test_invalid_bins_negative_raises(self) -> None:
        with pytest.raises(ValueError):
            MAPElitesGrid(n_bins_per_axis=-3)

    def test_invalid_feature_ranges_length_raises(self) -> None:
        with pytest.raises(ValueError):
            MAPElitesGrid(feature_ranges=((0.0, 1.0),))

    def test_invalid_feature_range_inverted_raises(self) -> None:
        with pytest.raises(ValueError):
            MAPElitesGrid(
                feature_ranges=(
                    (1.0, 0.0),  # inverted
                    (0.0, 1.0),
                    (0.0, 1.0),
                    (0.0, 1.0),
                )
            )

    def test_invalid_feature_range_equal_raises(self) -> None:
        with pytest.raises(ValueError):
            MAPElitesGrid(
                feature_ranges=(
                    (0.5, 0.5),  # high == low
                    (0.0, 1.0),
                    (0.0, 1.0),
                    (0.0, 1.0),
                )
            )


# ---------------------------------------------------------------------------
# 3. MAPElitesGrid — binning / submit
# ---------------------------------------------------------------------------


class TestMAPElitesGridSubmit:
    def test_bin_clips_below_low(self) -> None:
        g = MAPElitesGrid(n_bins_per_axis=3)
        k = g.key((-5.0, -5.0, -5.0, -5.0))
        assert k == (0, 0, 0, 0)

    def test_bin_clips_above_high(self) -> None:
        g = MAPElitesGrid(n_bins_per_axis=3)
        k = g.key((5.0, 5.0, 5.0, 5.0))
        assert k == (2, 2, 2, 2)

    def test_bin_middle_values(self) -> None:
        g = MAPElitesGrid(n_bins_per_axis=4)
        # value=0.5 over (0,1) range, n=4 → bin = int(0.5*4) = 2
        k = g.key((0.5, 0.5, 0.5, 0.5))
        assert k == (2, 2, 2, 2)

    def test_key_wrong_length_raises(self) -> None:
        g = MAPElitesGrid()
        with pytest.raises(ValueError):
            g.key((0.5, 0.5, 0.5))
        with pytest.raises(ValueError):
            g.key((0.5,) * 5)

    def test_submit_empty_cell_always_accepts(self) -> None:
        g = MAPElitesGrid()
        ind = _make_individual()
        ok = g.submit(ind, fitness=1.0, features=(0.1, 0.2, 0.3, 0.4))
        assert ok is True
        assert g.n_filled == 1

    def test_submit_same_cell_improvement_replaces(self) -> None:
        g = MAPElitesGrid()
        ind1 = _make_individual(seed=1)
        ind2 = _make_individual(seed=2)
        g.submit(ind1, fitness=1.0, features=(0.5, 0.5, 0.5, 0.5))
        ok = g.submit(ind2, fitness=2.0, features=(0.5, 0.5, 0.5, 0.5))
        assert ok is True
        assert g.n_filled == 1
        cell = next(iter(g.cells.values()))
        assert cell.fitness == 2.0
        assert cell.individual is ind2

    def test_submit_same_cell_worse_rejected(self) -> None:
        g = MAPElitesGrid()
        ind1 = _make_individual(seed=1)
        ind2 = _make_individual(seed=2)
        g.submit(ind1, fitness=2.0, features=(0.5, 0.5, 0.5, 0.5))
        ok = g.submit(ind2, fitness=1.0, features=(0.5, 0.5, 0.5, 0.5))
        assert ok is False
        assert g.cells[(2, 2, 2, 2)].fitness == 2.0
        assert g.cells[(2, 2, 2, 2)].individual is ind1

    def test_submit_equal_fitness_keeps_existing(self) -> None:
        """同 fitness では既存を残す (strict greater で更新)."""
        g = MAPElitesGrid()
        ind1 = _make_individual(seed=1)
        ind2 = _make_individual(seed=2)
        g.submit(ind1, fitness=1.0, features=(0.5,) * 4)
        ok = g.submit(ind2, fitness=1.0, features=(0.5,) * 4)
        assert ok is False
        assert g.cells[(2, 2, 2, 2)].individual is ind1

    def test_submit_distinct_cells_all_accepted(self) -> None:
        g = MAPElitesGrid(n_bins_per_axis=5)
        ind = _make_individual()
        ok1 = g.submit(ind, 1.0, (0.0, 0.0, 0.0, 0.0))
        ok2 = g.submit(ind, 1.0, (0.5, 0.5, 0.5, 0.5))
        ok3 = g.submit(ind, 1.0, (1.0, 1.0, 1.0, 1.0))
        assert (ok1, ok2, ok3) == (True, True, True)
        assert g.n_filled == 3

    def test_submit_many(self) -> None:
        g = MAPElitesGrid(n_bins_per_axis=3)
        ind = _make_individual()
        items = [
            (ind, 1.0, (0.0, 0.0, 0.0, 0.0)),
            (ind, 2.0, (0.0, 0.0, 0.0, 0.0)),  # same cell, improves
            (ind, 0.5, (1.0, 1.0, 1.0, 1.0)),
        ]
        accepted = g.submit_many(items)
        assert accepted == 3
        assert g.n_filled == 2


# ---------------------------------------------------------------------------
# 4. MAPElitesGrid — coverage / best / slices
# ---------------------------------------------------------------------------


class TestMAPElitesGridMetrics:
    def test_coverage_growth(self) -> None:
        g = MAPElitesGrid(n_bins_per_axis=2)
        ind = _make_individual()
        assert g.coverage == 0.0
        g.submit(ind, 1.0, (0.0, 0.0, 0.0, 0.0))
        assert g.coverage == pytest.approx(1 / 16)
        g.submit(ind, 1.0, (1.0, 1.0, 1.0, 1.0))
        assert g.coverage == pytest.approx(2 / 16)

    def test_best_picks_max(self) -> None:
        g = MAPElitesGrid()
        ind = _make_individual()
        g.submit(ind, 0.3, (0.1, 0.1, 0.1, 0.1))
        g.submit(ind, 0.9, (0.2, 0.2, 0.2, 0.2))
        g.submit(ind, 0.5, (0.3, 0.3, 0.3, 0.3))
        best = g.best
        assert best is not None
        assert best.fitness == 0.9
        assert isinstance(best, MAPElitesCell)

    def test_best_per_persona_slice(self) -> None:
        """persona 2 軸の同じ cell を thought_factor 軸で複数 cell に分散."""
        g = MAPElitesGrid(n_bins_per_axis=3)
        ind = _make_individual()
        # persona (0,0) で thought の cell を変えて 2 投入
        g.submit(ind, 0.3, (0.0, 0.0, 0.0, 0.0))
        g.submit(ind, 0.9, (0.0, 0.0, 0.99, 0.99))
        # persona (2,2) で 1 投入
        g.submit(ind, 0.5, (0.99, 0.99, 0.5, 0.5))
        slices = g.best_per_persona_slice()
        assert (0, 0) in slices
        assert (2, 2) in slices
        assert slices[(0, 0)].fitness == 0.9
        assert slices[(2, 2)].fitness == 0.5

    def test_fitness_grid_shape_and_fill(self) -> None:
        g = MAPElitesGrid(n_bins_per_axis=3)
        ind = _make_individual()
        g.submit(ind, 0.7, (0.0, 0.0, 0.0, 0.0))
        arr = g.fitness_grid()
        assert arr.shape == (3, 3, 3, 3)
        assert arr[0, 0, 0, 0] == 0.7
        # 未埋め cell は -inf
        assert np.isinf(arr[2, 2, 2, 2]) and arr[2, 2, 2, 2] < 0

    def test_to_dict_roundtrip_keys(self) -> None:
        g = MAPElitesGrid(n_bins_per_axis=2)
        ind = _make_individual()
        g.submit(ind, 1.0, (0.0, 0.0, 0.0, 0.0))
        g.submit(ind, 2.0, (1.0, 1.0, 1.0, 1.0))
        d = g.to_dict()
        assert d["n_bins_per_axis"] == 2
        assert len(d["cells"]) == 2
        # key 文字列化が一意であること
        assert "0,0,0,0" in d["cells"]
        assert "1,1,1,1" in d["cells"]


# ---------------------------------------------------------------------------
# 5. Default feature extractors
# ---------------------------------------------------------------------------


class TestDefaultFeatures:
    def test_default_persona_features_shape_and_range(self) -> None:
        rng = np.random.default_rng(0)
        comp = random_persona_composition(rng, n=3)
        feats = default_persona_features(comp)
        assert len(feats) == 2
        assert 0.0 <= feats[0] <= 1.0  # mean affinity
        assert feats[1] >= 0.0  # std

    def test_default_persona_features_none(self) -> None:
        feats = default_persona_features(None)
        assert feats == (0.5, 0.0)

    def test_default_thought_features_shape(self) -> None:
        rng = np.random.default_rng(0)
        comp = random_persona_composition(rng, n=3)
        feats = default_thought_features(comp)
        assert len(feats) == 2
        for v in feats:
            assert 0.0 <= v <= 1.0

    def test_default_thought_features_none(self) -> None:
        feats = default_thought_features(None)
        assert feats == (0.5, 0.5)

    def test_default_map_elites_features_length_4(self) -> None:
        rng = np.random.default_rng(0)
        comp = random_persona_composition(rng, n=3)
        feats = default_map_elites_features(comp)
        assert len(feats) == 4

    def test_default_features_integrate_with_grid(self) -> None:
        """default feature extractor の値が grid.key() に流せる."""
        g = MAPElitesGrid()
        rng = np.random.default_rng(7)
        comp = random_persona_composition(rng, n=2)
        feats = default_map_elites_features(comp)
        ind = _make_individual()
        ok = g.submit(ind, 0.5, feats)
        assert ok is True
        assert g.n_filled == 1


# ---------------------------------------------------------------------------
# 6. Integration — 多様性圧で fitness 順位が変わる
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_penalty_rerank_can_promote_diverse_individual(self) -> None:
        """λ が十分大きいとき, 集団内で唯一 persona が異なる個体が
        base fitness では負けていても effective fitness で勝つことがある.
        """
        common = PersonaComposition(persona_ids=("oka-kiyoshi",), weights=(1.0,))
        rare = PersonaComposition(persona_ids=("feynman",), weights=(1.0,))
        comps = [common, common, common, rare]
        base = [1.0, 1.0, 1.0, 0.6]

        # λ=0 → base そのまま, rare が最下位
        p0 = PersonaOverlapPenalty(lambda_=0.0)
        out0 = p0.apply(comps, base)
        assert int(np.argmax(out0)) != 3

        # λ を大きくすると rare が逆転する
        p_big = PersonaOverlapPenalty(lambda_=10.0)
        out_big = p_big.apply(comps, base)
        assert int(np.argmax(out_big)) == 3

    def test_grid_then_penalty_workflow(self) -> None:
        """典型ワークフロー: grid に投入 + penalty で多様性ボーナス."""
        rng = np.random.default_rng(42)
        comps = [random_persona_composition(rng, n=2) for _ in range(8)]
        base = list(rng.uniform(0.0, 1.0, size=8))
        ind = _make_individual()

        # MAP-Elites archive
        grid = MAPElitesGrid(n_bins_per_axis=4)
        for fit, comp in zip(base, comps):
            grid.submit(ind, fit, default_map_elites_features(comp))

        # PersonaOverlapPenalty 適用
        penalty = PersonaOverlapPenalty(lambda_=0.7)
        eff = penalty.apply(comps, base)

        assert grid.n_filled >= 1
        assert eff.shape == (8,)
        # effective >= base のはず (lambda>0 + 多様 ≥ 0)
        assert np.all(eff >= np.asarray(base) - 1e-12)
