# SPDX-License-Identifier: Apache-2.0
"""Tests for lldarwin Stage2 (proxy) — LLM 苦手軸 Pressure plugin.

設計: fullsense docs/vision/LLDARWIN_DESIGN.md §3。各苦手軸を関連思考因子の
case 群に写像し、lldarwin の ε-lexicase が軸ごとに specialist を保存する。
HONEST: proxy のみ (個体は実 LLM でなく genome)。mechanism feasibility 検証用。
"""
from __future__ import annotations

import numpy as np

from llive.perf.evolutionary.genome_3d import Genome3D
from llive.perf.evolutionary.individual import Individual
from llive.perf.evolutionary.lldarwin import MultiPressureSelector
from llive.perf.evolutionary.population import Population
from llive.perf.evolutionary.pressures import (
    LLM_WEAKNESS_PRESSURES,
    ProxyPressure,
    make_pressure_fitness,
)


def test_catalog_factors_are_valid() -> None:
    """カタログの全 pressure が既知の思考因子のみ参照する (__post_init__ 検証)."""
    assert len(LLM_WEAKNESS_PRESSURES) == 5
    names = {p.name for p in LLM_WEAKNESS_PRESSURES}
    assert names == {
        "typo_robustness",
        "polysemy_wsd",
        "multistep_robustness",
        "calibration",
        "context_management",
    }


def test_unknown_factor_rejected() -> None:
    """未知の思考因子を参照する pressure は構築時に弾く (fail-closed)."""
    try:
        ProxyPressure("bad", ("factor_nonexistent",))
    except ValueError:
        return
    raise AssertionError("unknown factor should raise ValueError")


def test_fitness_breakdown_has_all_pressure_cases() -> None:
    """make_pressure_fitness の breakdown に全 pressure の case が入る."""
    fit = make_pressure_fitness()
    report = fit(Genome3D.default())
    # 3+3+3+2+3 = 14 cases
    assert len(report.breakdown) == 14
    assert any(k.startswith("typo_robustness::") for k in report.breakdown)
    assert any(k.startswith("calibration::") for k in report.breakdown)
    assert 0.0 <= report.score <= 1.0
    assert "PROXY" in report.notes


def test_lexicase_preserves_axis_specialists() -> None:
    """ある苦手軸の因子に強い genome が、別軸に強い genome と共存する (specialist 保存)."""
    rng = np.random.default_rng(0)
    fit = make_pressure_fitness()
    # multistep に強い genome (構造化/閉ループ/自己拡張 高) vs calibration に強い genome
    # (不確実性/来歴 高)。c_factors を直接いじって対照的な specialist を作る。
    g_multistep = Genome3D.default()
    g_calib = Genome3D.default()
    fac_m = np.asarray(g_multistep.c_factors.as_array(), dtype=float)
    fac_c = np.asarray(g_calib.c_factors.as_array(), dtype=float)
    fac_m[:] = 0.1
    fac_m[[0, 2, 3], :] = 0.9  # structurize/closed_loop/self_extend
    fac_c[:] = 0.1
    fac_c[[4, 7], :] = 0.9  # uncertainty/provenance

    from llive.perf.evolutionary.thought_factor_per_layer import (
        ThoughtFactorPerLayerChromosome,
    )

    g_multistep = Genome3D(
        c_impl=g_multistep.c_impl,
        c_prompt=g_multistep.c_prompt,
        c_meta=g_multistep.c_meta,
        c_factors=ThoughtFactorPerLayerChromosome.from_matrix(fac_m),
    )
    g_calib = Genome3D(
        c_impl=g_calib.c_impl,
        c_prompt=g_calib.c_prompt,
        c_meta=g_calib.c_meta,
        c_factors=ThoughtFactorPerLayerChromosome.from_matrix(fac_c),
    )
    x = Individual(genome=g_multistep)
    y = Individual(genome=g_calib)
    x.record_fitness(fit(g_multistep))
    y.record_fitness(fit(g_calib))
    sel = MultiPressureSelector(epsilon=0.0)
    pop = Population(individuals=[x, y])
    chosen = {sel(pop, rng).individual_id for _ in range(60)}
    assert len(chosen) == 2  # 異なる軸の specialist が両方生存
