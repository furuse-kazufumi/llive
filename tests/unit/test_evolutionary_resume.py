# SPDX-License-Identifier: Apache-2.0
"""resume の bounds 同期 (B-LOGIC-3) — 単体テスト."""

from __future__ import annotations

import json

from llive.perf.evolutionary import (
    EvolutionConfig,
    EvolutionLoop,
    GenomeBounds,
    Population,
    sphere_fitness,
)


def test_resume_syncs_bounds_from_snapshot(tmp_path) -> None:
    """resume 時に population.bounds を snapshot の bounds に同期する (B-LOGIC-3).

    同期しないと resumed 個体の genome dim と bounds dim が食い違い、以後の
    operator/clip が破綻する。1-dim の running population に 2-dim snapshot を
    resume し、bounds が 2-dim に揃うことを保証する。
    """
    pop = Population.random(
        bounds=GenomeBounds(lower=(0.0,), upper=(1.0,)), size=4, seed=0
    )
    snap_pop = Population.random(
        bounds=GenomeBounds(lower=(0.0, 0.0), upper=(1.0, 1.0)), size=4, seed=1
    )
    snap_pop.generation = 3
    snap_path = tmp_path / "snapshot_gen_0003.json"
    snap_path.write_text(
        json.dumps(snap_pop.to_dict(), ensure_ascii=False), encoding="utf-8"
    )

    loop = EvolutionLoop(fitness_fn=sphere_fitness)
    config = EvolutionConfig(
        max_generations=0, resume_from=snap_path, log_progress=False
    )
    loop.run(pop, config)

    # bounds が snapshot の 2-dim に同期され、個体 genome dim と一致する
    assert pop.bounds.n_dims == 2
    for ind in pop.individuals:
        assert ind.genome.n_dims == pop.bounds.n_dims
