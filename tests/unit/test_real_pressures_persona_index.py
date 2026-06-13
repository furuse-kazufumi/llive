# SPDX-License-Identifier: Apache-2.0
"""genome_to_system_prompt の persona-index bridge (whole-system) テスト.

persona-indexed (各因子に担当ペルソナ) を実 LLM system prompt に反映する additive bridge。
default None では旧挙動維持 (後方互換) を固定。[[goal_surpass_mythos_evolutionary]] /
[[feedback_staged_poc_individual_structure]] の段階的採用 (小 PoC→構造採用→whole-system)。
"""
from __future__ import annotations

from llive.perf.evolutionary.genome_3d import Genome3D
from llive.perf.evolutionary.persona import PERSONA_ONTOLOGY
from llive.perf.evolutionary.real_pressures import (
    _persona_index_instruction,
    genome_to_system_prompt,
)

_MARKER = "Channel these expert perspectives"


def _genome_with_persona_index(idx: tuple[int, ...]) -> Genome3D:
    base = Genome3D.default()
    cf = base.c_factors.with_persona_index(idx)
    return Genome3D(c_impl=base.c_impl, c_prompt=base.c_prompt,
                    c_meta=base.c_meta, c_factors=cf)


def test_persona_index_none_is_unchanged():
    """既定 (persona_index=None) では persona 句が付かない = 旧挙動完全維持。"""
    sys = genome_to_system_prompt(Genome3D.default())
    assert _MARKER not in sys
    assert _persona_index_instruction(Genome3D.default()) is None


def test_persona_index_reflected_in_system_prompt():
    """persona_index 設定時、担当ペルソナの視点が system prompt に反映される。"""
    g = _genome_with_persona_index(tuple(range(10)))  # 10 因子に別 persona idx
    sys = genome_to_system_prompt(g)
    assert _MARKER in sys
    names = [p.name for p in PERSONA_ONTOLOGY.values()]
    assert any(n in sys for n in names), sys


def test_persona_index_changes_prompt_vs_default():
    """persona_index あり/なしで system prompt が変わる (= 選択信号の源になりうる)。"""
    base_sys = genome_to_system_prompt(Genome3D.default())
    pi_sys = genome_to_system_prompt(_genome_with_persona_index((0,) * 10))
    assert pi_sys != base_sys
    assert _MARKER in pi_sys


def test_flat_genome_without_c_factors_is_default():
    """c_prompt / c_factors を持たない個体は default system prompt (後方互換)。"""
    class _Flat:
        pass
    sys = genome_to_system_prompt(_Flat())
    assert _MARKER not in sys


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
