# SPDX-License-Identifier: Apache-2.0
"""Extended persona ontology — affinity 自動算出の単体テスト。

ユーザー指摘 (2026-05-24)「ハードコード部分は疑った方が良い」を受け、拡張ペルソナの
factor_affinity が **手動数値でなく affinity_text から導出される**ことを pin する。
"""

from __future__ import annotations

from llive.perf.evolutionary.persona import (
    PERSONA_ONTOLOGY,
    THOUGHT_FACTORS,
    get_persona,
)
from llive.perf.evolutionary.experimental.persona_extended import (
    EXTENDED_PERSONA_DATA,
    EXTENDED_PERSONAS,
    register_extended_personas,
)


def test_extended_personas_registered_via_import_side_effect() -> None:
    for pid in EXTENDED_PERSONA_DATA:
        assert pid in PERSONA_ONTOLOGY


def test_register_is_idempotent() -> None:
    assert register_extended_personas() == 0  # 既に登録済み


def test_data_has_no_hardcoded_affinity() -> None:
    # データ源に生の affinity 数値が無い (記述文のみ) ことを保証 = ハードコード排除。
    for pid, d in EXTENDED_PERSONA_DATA.items():
        assert "factor_affinity" not in d, f"{pid}: 数値ハードコードが混入"
        assert d.get("affinity_text"), f"{pid}: affinity_text 必須"


def test_affinity_is_derived_not_flat() -> None:
    # affinity_text からヒットして算出されている (全 0.5 = 情報なし中央 でない) こと。
    for pid, persona in EXTENDED_PERSONAS.items():
        assert len(persona.factor_affinity) == len(THOUGHT_FACTORS)
        all_mid = all(abs(v - 0.5) < 1e-9 for v in persona.factor_affinity)
        assert not all_mid, f"{pid}: affinity_text がヒットせず中央値 (記述不足)"
        assert all(0.0 <= v <= 1.0 for v in persona.factor_affinity)


def test_derived_top_factor_matches_description_intent() -> None:
    # 記述の意図と最上位因子が整合することを代表例で pin (算出の妥当性)。
    def top_factor(pid: str) -> str:
        aff = dict(zip(THOUGHT_FACTORS, get_persona(pid).factor_affinity, strict=True))
        return max(aff, key=lambda k: aff[k])

    assert top_factor("darwin") == "factor_reality_link"  # 膨大な観測
    assert top_factor("altshuller") in ("factor_structurize", "factor_recompose")  # 体系/分解合成
    assert top_factor("turing") == "factor_exploration"  # 未知の探索
    assert top_factor("poincare") == "factor_recompose"  # 位相の再構成


def test_extended_personas_well_formed() -> None:
    for pid, persona in EXTENDED_PERSONAS.items():
        assert persona.thought_patterns  # 非空
        assert persona.fields  # 非空
        assert persona.era != "unknown"
