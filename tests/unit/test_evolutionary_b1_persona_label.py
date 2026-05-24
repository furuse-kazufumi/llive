# SPDX-License-Identifier: Apache-2.0
"""B1 回帰テスト: 19-dim persona-style genome の backend_id を *位置でなく label* で解決.

過去のバグ (gem-critic が FullSense 視点で発見): `llm_fitness` は 5-dim genome を前提に
backend_id を `values[0]` 付近で読み、19-dim persona genome (思考因子 10 + memory 3 +
backend 1 + sampler 3 + proactive 2) を渡すと **思考因子 idx0 を backend_id と誤読**。
`on_prem_backend_factory` (cloud fail-closed) と併用すると大半が cloud 判定 → 淘汰され、
集団が壊れた。`Genome.value_by_label` による label 解決 (fitness_llm._genome_field /
LlivVariantBuilder.build_config) で修正済み。本テストはその回帰を防ぐ。
"""

from __future__ import annotations

from llive.perf.evolutionary import llm_fitness_factory
from llive.perf.evolutionary.genome import Genome
from llive.perf.evolutionary.llive_variant import (
    LIVE_VARIANT_GENOME_BOUNDS,
    LIVE_VARIANT_GENOME_LABELS,
)


def _persona_style_genome(*, factor0: float, backend_id: float) -> Genome:
    """19-dim genome (labels 付き). idx0=factor_structurize, idx13=backend_id."""
    values = (
        factor0, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5,  # 10 思考因子
        0.5, 0.5, 0.75,        # memory tier (idx10-12)
        backend_id,            # idx13 backend_id
        0.7, 0.8, 0.0,         # sampler (idx14-16)
        0.6, 30.0,             # proactive (idx17-18)
    )
    return Genome.from_values(
        values,
        bounds=LIVE_VARIANT_GENOME_BOUNDS,
        labels=LIVE_VARIANT_GENOME_LABELS,
    )


def test_b1_backend_id_resolved_by_label_not_position() -> None:
    # idx0 (factor_structurize) = 1.0 → 旧バグでは backend_id=values[0]=int(1)=openai=cloud と
    # 誤読され purity violation で淘汰された。idx13 (本来の backend_id) = 0.0 = mock (on-prem)。
    genome = _persona_style_genome(factor0=1.0, backend_id=0.0)
    fitness = llm_fitness_factory()  # default = on_prem_backend_factory (cloud fail-closed)
    report = fitness(genome)
    # 修正済み: backend_id は label 解決で idx13=mock → 淘汰されない
    assert "purity_violation" not in report.breakdown
    assert report.score > 0.0
    assert report.breakdown["backend_id"] == 0.0  # mock に解決 (factor0 ではない)


def test_b1_cloud_backend_at_correct_index_still_culled() -> None:
    # idx13 (backend_id) = 2.0 = anthropic (cloud)。idx0 = 0.0 (mock と誤読されうる) でも、
    # label 解決が idx13 を正しく拾い cloud と判定 → on-prem fail-closed → 淘汰。
    genome = _persona_style_genome(factor0=0.0, backend_id=2.0)
    fitness = llm_fitness_factory()
    report = fitness(genome)
    assert report.breakdown.get("purity_violation") == 1.0
    assert report.score == 0.0


def test_b1_genome_without_labels_uses_fallback_index() -> None:
    # labels なし genome は fallback_index に依存する (旧 5-dim 経路の保険)。
    # 19-dim だが labels なし → value_by_label("backend_id", 0) は values[0] を使う。
    # これは「labels を付ければ position 非依存」という設計の対照確認。
    values = (
        0.0, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5,
        0.5, 0.5, 0.75, 2.0, 0.7, 0.8, 0.0, 0.6, 30.0,
    )
    genome = Genome.from_values(values, bounds=LIVE_VARIANT_GENOME_BOUNDS)  # labels 省略
    fitness = llm_fitness_factory()
    report = fitness(genome)
    # labels なしなら fallback_index=0 → values[0]=0.0=mock → 淘汰されない
    # (idx13 の cloud 値 2.0 は label がないので参照されない)
    assert report.breakdown["backend_id"] == 0.0
