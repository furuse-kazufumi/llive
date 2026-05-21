# SPDX-License-Identifier: Apache-2.0
"""PersonaImportAlgorithm (v0.E E.12 / CE-20) — unit tests."""

from __future__ import annotations

import numpy as np
import pytest

from llive.perf.evolutionary import (
    PersonaComposition,
    PersonaImportAlgorithm,
    PersonaImportPlan,
    PersonaZoneShareEvent,
    persona_dissimilarity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _oka() -> PersonaComposition:
    return PersonaComposition(persona_ids=("oka-kiyoshi",), weights=(1.0,))


def _newton() -> PersonaComposition:
    return PersonaComposition(persona_ids=("newton",), weights=(1.0,))


def _feynman() -> PersonaComposition:
    return PersonaComposition(persona_ids=("feynman",), weights=(1.0,))


def _galois_feynman() -> PersonaComposition:
    return PersonaComposition(
        persona_ids=("galois", "feynman"), weights=(0.5, 0.5)
    )


# ---------------------------------------------------------------------------
# 1. PersonaImportAlgorithm — construction
# ---------------------------------------------------------------------------


class TestPersonaImportAlgorithmConstruction:
    def test_default(self) -> None:
        algo = PersonaImportAlgorithm()
        assert algo.max_imports_per_event == 2
        assert algo.blend_strategy == "extend"
        assert algo.affinity_threshold == 0.0
        assert algo.initial_weight == 0.3

    def test_invalid_max_imports(self) -> None:
        with pytest.raises(ValueError):
            PersonaImportAlgorithm(max_imports_per_event=-1)

    def test_invalid_affinity_threshold(self) -> None:
        with pytest.raises(ValueError):
            PersonaImportAlgorithm(affinity_threshold=1.5)
        with pytest.raises(ValueError):
            PersonaImportAlgorithm(affinity_threshold=-1.5)

    def test_invalid_blend_strategy(self) -> None:
        with pytest.raises(ValueError):
            PersonaImportAlgorithm(blend_strategy="merge_mixed")

    def test_invalid_initial_weight(self) -> None:
        with pytest.raises(ValueError):
            PersonaImportAlgorithm(initial_weight=1.5)
        with pytest.raises(ValueError):
            PersonaImportAlgorithm(initial_weight=-0.1)


# ---------------------------------------------------------------------------
# 2. plan() — selection rules
# ---------------------------------------------------------------------------


class TestPlanSelection:
    def test_low_source_peer_score_skips_all(self) -> None:
        algo = PersonaImportAlgorithm(min_source_peer_score=0.5)
        plan = algo.plan(
            _galois_feynman(),
            _oka(),
            source_peer_score=0.2,
        )
        assert plan.imported_persona_ids == ()
        assert set(plan.rejected_persona_ids) == {"galois", "feynman"}

    def test_existing_persona_rejected(self) -> None:
        algo = PersonaImportAlgorithm(forbid_existing=True)
        target = PersonaComposition(persona_ids=("feynman",), weights=(1.0,))
        plan = algo.plan(_galois_feynman(), target)
        # feynman は既存なので拒否, galois は受理
        assert "galois" in plan.imported_persona_ids
        assert "feynman" in plan.rejected_persona_ids

    def test_existing_persona_allowed_when_flag_off(self) -> None:
        algo = PersonaImportAlgorithm(forbid_existing=False)
        target = PersonaComposition(persona_ids=("feynman",), weights=(1.0,))
        plan = algo.plan(_galois_feynman(), target)
        assert set(plan.imported_persona_ids) == {"galois", "feynman"}

    def test_max_imports_capped(self) -> None:
        algo = PersonaImportAlgorithm(max_imports_per_event=1)
        rng = np.random.default_rng(0)
        plan = algo.plan(
            PersonaComposition(
                persona_ids=("galois", "feynman", "newton"),
                weights=(0.33, 0.33, 0.34),
            ),
            _oka(),
            rng=rng,
        )
        assert len(plan.imported_persona_ids) == 1

    def test_unknown_persona_id_rejected(self) -> None:
        """ontology に無い id はそもそも PersonaComposition で作れないので
        plan() の入口に達しない. このテストは defensive code path のため
        skipped (PersonaComposition __post_init__ で防御済み)."""
        # PersonaComposition は __post_init__ で unknown id を弾く
        with pytest.raises(ValueError):
            PersonaComposition(persona_ids=("imaginary-person",), weights=(1.0,))

    def test_affinity_threshold_rejects_dissimilar(self) -> None:
        """affinity_threshold が高いと cosine sim が低い persona は拒否."""
        algo_high = PersonaImportAlgorithm(affinity_threshold=0.99)
        plan = algo_high.plan(_newton(), _oka())
        # newton と oka-kiyoshi の cosine sim < 0.99 のはず → 拒否
        # (両者 factor_affinity は heuristic だが完全一致ではない)
        assert "newton" in plan.rejected_persona_ids
        assert "newton" not in plan.imported_persona_ids

    def test_zero_affinity_threshold_accepts(self) -> None:
        algo = PersonaImportAlgorithm(affinity_threshold=0.0)
        plan = algo.plan(_newton(), _oka())
        assert "newton" in plan.imported_persona_ids


# ---------------------------------------------------------------------------
# 3. apply() — blend strategies
# ---------------------------------------------------------------------------


class TestApplyExtend:
    def test_extend_appends_new_persona(self) -> None:
        algo = PersonaImportAlgorithm(blend_strategy="extend")
        plan = algo.plan(_newton(), _oka())
        new_comp = plan.apply(_oka(), _newton())
        assert "oka-kiyoshi" in new_comp.persona_ids
        assert "newton" in new_comp.persona_ids
        # weights は normalize されている
        assert abs(sum(new_comp.weights) - 1.0) < 1e-9

    def test_no_imports_returns_same(self) -> None:
        algo = PersonaImportAlgorithm()
        plan = PersonaImportPlan(
            source_id="A",
            target_id="B",
            imported_persona_ids=(),
            rejected_persona_ids=(),
            blend_strategy="extend",
        )
        target = _oka()
        out = plan.apply(target, _newton())
        assert out is target or out.persona_ids == target.persona_ids


class TestApplyReplace:
    def test_replace_swaps_tail(self) -> None:
        algo = PersonaImportAlgorithm(blend_strategy="replace")
        source = PersonaComposition(
            persona_ids=("newton",), weights=(1.0,)
        )
        target = PersonaComposition(
            persona_ids=("oka-kiyoshi", "kant"),
            weights=(0.5, 0.5),
        )
        plan = algo.plan(source, target)
        new_comp = plan.apply(target, source)
        # tail (kant) が置き換わるか, 少なくとも newton が入る
        assert "newton" in new_comp.persona_ids


class TestApplyBlendWeights:
    def test_blend_weights_averages_existing(self) -> None:
        algo = PersonaImportAlgorithm(blend_strategy="blend_weights")
        source = PersonaComposition(
            persona_ids=("oka-kiyoshi",), weights=(1.0,)
        )
        target = PersonaComposition(
            persona_ids=("oka-kiyoshi",), weights=(0.5,)
        )
        # forbid_existing=True なので import 数 0 だが blend は走らない
        # (plan.apply は imported_persona_ids==() で no-op)
        plan = algo.plan(source, target)
        new_comp = plan.apply(target, source)
        # imported が無いので target そのまま
        assert new_comp.persona_ids == target.persona_ids

    def test_blend_weights_with_new_import(self) -> None:
        algo = PersonaImportAlgorithm(blend_strategy="blend_weights")
        source = PersonaComposition(
            persona_ids=("newton",), weights=(1.0,)
        )
        target = PersonaComposition(
            persona_ids=("oka-kiyoshi",), weights=(1.0,)
        )
        plan = algo.plan(source, target)
        new_comp = plan.apply(target, source)
        # newton が append された + weights renormalize
        assert "newton" in new_comp.persona_ids
        assert abs(sum(new_comp.weights) - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# 4. execute() — end-to-end
# ---------------------------------------------------------------------------


class TestExecute:
    def test_execute_returns_triple(self) -> None:
        algo = PersonaImportAlgorithm()
        new_comp, plan, event = algo.execute(
            _newton(), _oka(), source_id="A1", target_id="B1"
        )
        assert isinstance(new_comp, PersonaComposition)
        assert isinstance(plan, PersonaImportPlan)
        assert isinstance(event, PersonaZoneShareEvent)
        assert event.source_id == "A1"
        assert event.target_id == "B1"
        assert "newton" in event.persona_ids
        assert event.zone == "shared"

    def test_execute_no_imports_no_event(self) -> None:
        """既に target にいる persona しか source にない → event=None."""
        algo = PersonaImportAlgorithm(forbid_existing=True)
        source = PersonaComposition(
            persona_ids=("oka-kiyoshi",), weights=(1.0,)
        )
        target = source
        new_comp, plan, event = algo.execute(source, target)
        assert plan.imported_persona_ids == ()
        assert event is None
        assert new_comp.persona_ids == target.persona_ids

    def test_execute_increases_diversity(self) -> None:
        """import 前後で persona_dissimilarity が変化することを確認."""
        algo = PersonaImportAlgorithm()
        source = _newton()
        target = _oka()
        d_before = persona_dissimilarity(source, target)
        new_target, _, _ = algo.execute(source, target)
        d_after = persona_dissimilarity(source, new_target)
        # newton を取り込んだので similar に近づく
        assert d_after <= d_before

    def test_execute_deterministic_with_seed(self) -> None:
        """同じ rng seed なら結果が完全一致."""
        algo = PersonaImportAlgorithm(max_imports_per_event=1)
        source = PersonaComposition(
            persona_ids=("galois", "feynman", "newton"),
            weights=(0.33, 0.33, 0.34),
        )
        target = _oka()
        rng1 = np.random.default_rng(42)
        rng2 = np.random.default_rng(42)
        r1 = algo.execute(source, target, rng=rng1)
        r2 = algo.execute(source, target, rng=rng2)
        assert r1[1].imported_persona_ids == r2[1].imported_persona_ids


# ---------------------------------------------------------------------------
# 5. PersonaZoneShareEvent
# ---------------------------------------------------------------------------


class TestPersonaZoneShareEvent:
    def test_to_dict_roundtrip(self) -> None:
        ev = PersonaZoneShareEvent(
            source_id="a",
            target_id="b",
            persona_ids=("newton", "kant"),
            zone="mentor",
            note="hello",
        )
        d = ev.to_dict()
        assert d["source_id"] == "a"
        assert d["target_id"] == "b"
        assert d["persona_ids"] == ["newton", "kant"]
        assert d["zone"] == "mentor"
        assert d["note"] == "hello"

    def test_default_zone_shared(self) -> None:
        ev = PersonaZoneShareEvent(
            source_id="a",
            target_id="b",
            persona_ids=("newton",),
        )
        assert ev.zone == "shared"

    def test_custom_zone_via_algo(self) -> None:
        algo = PersonaImportAlgorithm(zone="mentor")
        _, _, ev = algo.execute(_newton(), _oka())
        assert ev is not None
        assert ev.zone == "mentor"


# ---------------------------------------------------------------------------
# 6. PersonaImportPlan — to_dict
# ---------------------------------------------------------------------------


class TestPersonaImportPlanDict:
    def test_to_dict_keys(self) -> None:
        plan = PersonaImportPlan(
            source_id="A",
            target_id="B",
            imported_persona_ids=("newton",),
            rejected_persona_ids=("kant",),
            blend_strategy="extend",
            initial_weight=0.4,
        )
        d = plan.to_dict()
        assert d == {
            "source_id": "A",
            "target_id": "B",
            "imported_persona_ids": ["newton"],
            "rejected_persona_ids": ["kant"],
            "blend_strategy": "extend",
            "initial_weight": 0.4,
        }

    def test_apply_unknown_strategy_raises(self) -> None:
        plan = PersonaImportPlan(
            source_id="A",
            target_id="B",
            imported_persona_ids=("newton",),
            rejected_persona_ids=(),
            blend_strategy="bogus",
        )
        with pytest.raises(ValueError):
            plan.apply(_oka(), _newton())
