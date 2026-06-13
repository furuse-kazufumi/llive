# SPDX-License-Identifier: Apache-2.0
"""進化走行前の凍結点整備テスト (2026-05-24)。

進化を長期 run / resume で走らせ始めると変更困難になる凍結点を pin する。ユーザー指示:
「走り始めると変更困難な改造は今入れ切る」「失敗しても実験結果が残らないと意味がない」。

- `_BACKEND_NAMES` の二重定義 (fitness_llm vs llive_variant) の一致 — ずれると同じ
  backend_id が別 backend に解釈され、走行中の個体が破綻する。
- founder の backend_id を on-prem (mock=0) で初期化 — bounds 中点 (≈anthropic=cloud) だと
  実 LLM fitness の fail-closed で全 founder が淘汰されてしまう。
"""

from __future__ import annotations

from llive.perf.evolutionary.fitness_llm import _BACKEND_NAMES as _FITNESS_BACKEND_NAMES
from llive.perf.evolutionary.llive_variant import (
    LIVE_VARIANT_GENOME_LABELS,
)
from llive.perf.evolutionary.llive_variant import (
    _BACKEND_NAMES as _VARIANT_BACKEND_NAMES,
)
from llive.perf.evolutionary.persona_evolution import build_founder_genome


def test_backend_names_synchronized_across_modules() -> None:
    # backend_id (genome dim 13) は fitness_llm と llive_variant の双方で index 解決される。
    # 二重定義がずれると同じ数値が別 backend に解釈され、過去個体の意味が破綻する (凍結点)。
    assert _FITNESS_BACKEND_NAMES == _VARIANT_BACKEND_NAMES


def test_founder_backend_id_initialized_on_prem() -> None:
    # founder の backend_id は on-prem (mock=0) 初期化。cloud 中点だと実 LLM fitness で淘汰。
    idx = LIVE_VARIANT_GENOME_LABELS.index("backend_id")
    for pid in ("furuse-kazufumi", "oka-kiyoshi", "grothendieck"):
        genome = build_founder_genome(pid)
        backend_id = int(genome.value_by_label("backend_id", idx))
        assert backend_id == 0, f"{pid}: founder backend_id={backend_id} (mock=0 であるべき)"
        assert _VARIANT_BACKEND_NAMES[backend_id] == "mock"


def test_founder_thought_factors_preserved() -> None:
    # backend_id 誘導が思考因子 dim (0..9) を壊していないこと (persona affinity が genome に残る)。
    from llive.perf.evolutionary.persona import get_persona

    genome = build_founder_genome("furuse-kazufumi")
    affinity = get_persona("furuse-kazufumi").factor_affinity
    arr = genome.as_array()
    for i, expected in enumerate(affinity):
        assert abs(float(arr[i]) - float(expected)) < 1e-9
