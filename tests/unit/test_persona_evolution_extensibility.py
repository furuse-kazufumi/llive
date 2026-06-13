# SPDX-License-Identifier: Apache-2.0
"""persona 世代交代の **拡張耐性 (extend-without-breakage)** 不変条件テスト.

ユーザー原則 (2026-05-23):
    「進化とアルゴリズム拡張が並行して破綻せずに実現可能な形で進めて行ける事が重要」。

この原則を支える既存コントラクトを persona 経路で固定する:

1. **新 dim を足さない** (genome_version.py addendum §1-2) — founder genome は 19-dim flat
   不変。`assert_flat_dim` で守る → 古い snapshot が常に resume 可能。
2. **resume 継続性** — run → snapshot → resume が例外なく世代を進める。
3. **roster 拡張無破綻** — persona を足した run も従来 run も両方走る (段階的追加)。
4. **fail-closed dispatch** — 未知版タグは拒否、第4 dim を導入していない。
5. **plugin 拡張点** — custom fitness を差し替えても loop は壊れない。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from llive.perf.evolutionary import (
    RESEARCH_METHODOLOGY_PERSONA_IDS,
    build_founder_genome,
    run_persona_evolution,
)
from llive.perf.evolutionary.genome_version import (
    KNOWN_GENOME_VERSIONS,
    assert_flat_dim,
    assert_no_fourth_dim,
    dispatch_target,
)
from llive.perf.evolutionary.individual import FitnessReport


# 1. 新 dim を足さない — founder genome は 19-dim flat 不変
def test_founder_genome_honors_flat_dim_invariant() -> None:
    """全 research ペルソナの founder genome が 19-dim flat 不変条件を守る.

    これが守られる限り、persona を増やしても genome 構造は変わらず、過去の
    snapshot は常に resume 可能 (= 走り続ける進化を壊さない)。
    """
    for pid in RESEARCH_METHODOLOGY_PERSONA_IDS:
        genome = build_founder_genome(pid)
        assert_flat_dim(genome.as_array())  # 19 でなければ AssertionError


# 2. resume 継続性 — run → snapshot → resume が破綻しない
def test_resume_continues_without_breakage(tmp_path: Path) -> None:
    out = tmp_path / "evo"
    # 初回: gen 0..3, 毎世代 snapshot (persist + checkpoint_every=1)
    r1 = run_persona_evolution(
        RESEARCH_METHODOLOGY_PERSONA_IDS,
        population_size=6,
        generations=3,
        seed=0,
        out_dir=out,
        patience=99,
        persist_generation_log=True,
        checkpoint_every=1,
    )
    gen1 = r1.evolution_result.final_population.generation
    assert gen1 >= 3

    # resume: snapshot から再開してさらに進める → 例外なし + 世代前進
    r2 = run_persona_evolution(
        RESEARCH_METHODOLOGY_PERSONA_IDS,
        population_size=6,
        generations=2,
        seed=0,
        out_dir=out,
        patience=99,
        persist_generation_log=True,
        checkpoint_every=1,
        resume_from=out,
    )
    gen2 = r2.evolution_result.final_population.generation
    assert gen2 > gen1  # resume 後さらに進んだ (破綻せず継続)


# 3. roster 拡張無破綻 — persona を足しても従来 roster でも両方走る
def test_roster_extension_no_breakage() -> None:
    base = list(RESEARCH_METHODOLOGY_PERSONA_IDS)
    extended = base + ["oka-kiyoshi"]  # 段階的に 1 名追加

    r_base = run_persona_evolution(base, population_size=6, generations=2, seed=0)
    r_ext = run_persona_evolution(extended, population_size=7, generations=2, seed=0)

    assert r_base.evolution_result.final_population.generation == 2
    assert r_ext.evolution_result.final_population.generation == 2
    assert len(r_ext.founder_ids) == len(r_base.founder_ids) + 1


# 4. fail-closed dispatch + 第4 dim を導入していない
def test_genome_version_dispatch_fail_closed() -> None:
    assert_no_fourth_dim()  # 19/38/40 の 3 値だけ
    for v in KNOWN_GENOME_VERSIONS:
        assert dispatch_target(v) == v
    with pytest.raises(KeyError):
        dispatch_target("bogus-version")  # 未知タグは拒否 (fail-closed)


# 5. plugin 拡張点 — custom fitness を差し替えても loop は壊れない
def test_custom_fitness_plugin_no_breakage() -> None:
    def custom_fitness(genome) -> FitnessReport:  # noqa: ANN001
        # genome の次元に依存しない定数 fitness (拡張 operator の最小例)
        return FitnessReport(score=0.5, n_samples=1)

    res = run_persona_evolution(
        RESEARCH_METHODOLOGY_PERSONA_IDS,
        population_size=6,
        generations=2,
        seed=0,
        fitness_fn=custom_fitness,
    )
    assert res.used_proxy_fitness is False
    assert res.evolution_result.final_population.generation == 2


# 6. 決定論 — 同 seed・同設定なら best_score 再現 (拡張前後の回帰検出に使える)
def test_determinism_enables_regression_detection() -> None:
    kw = dict(population_size=6, generations=3, seed=42)
    a = run_persona_evolution(RESEARCH_METHODOLOGY_PERSONA_IDS, **kw)
    b = run_persona_evolution(RESEARCH_METHODOLOGY_PERSONA_IDS, **kw)
    assert a.evolution_result.best_score == b.evolution_result.best_score


# 7. immigration — 走行中の集団に persona を追加しても破綻しない (段階的追加の連続化)
def test_immigration_adds_persona_midrun_without_breakage(tmp_path: Path) -> None:
    out = tmp_path / "evo"
    # 初回 run (founders 2 名) + snapshot
    r1 = run_persona_evolution(
        ["friston", "millidge"],
        population_size=8,
        generations=3,
        seed=0,
        out_dir=out,
        patience=99,
        persist_generation_log=True,
        checkpoint_every=1,
    )
    gen1 = r1.evolution_result.final_population.generation
    assert r1.injected_persona_ids == ()

    # resume + 新ペルソナ 1 名を移民 (mid-run 追加)
    r2 = run_persona_evolution(
        ["friston", "millidge"],
        population_size=8,
        generations=2,
        seed=0,
        out_dir=out,
        patience=99,
        persist_generation_log=True,
        checkpoint_every=1,
        resume_from=out,
        inject_persona_ids=["isomura-takuya"],
    )
    # 移民が記録され、世代が前進、集団サイズ不変、破綻なし
    assert r2.injected_persona_ids == ("isomura-takuya",)
    assert r2.evolution_result.final_population.generation > gen1
    assert r2.evolution_result.final_population.size == 8
    # extensibility 契約: 移民後も全個体 19-dim flat 不変
    for ind in r2.evolution_result.final_population.individuals:
        assert_flat_dim(ind.genome.as_array())


# 8. immigration — 集団全置換になる過大投入は fail-closed
def test_immigration_rejects_oversized_injection(tmp_path: Path) -> None:
    out = tmp_path / "evo2"
    run_persona_evolution(
        ["friston"],
        population_size=3,
        generations=2,
        seed=0,
        out_dir=out,
        patience=99,
        persist_generation_log=True,
        checkpoint_every=1,
    )
    # inject 数 >= 集団サイズ → ValueError (集団を全置換しない)
    with pytest.raises(ValueError):
        run_persona_evolution(
            ["friston"],
            population_size=3,
            generations=1,
            seed=0,
            out_dir=out,
            resume_from=out,
            inject_persona_ids=["friston", "millidge", "isomura-takuya"],
        )
