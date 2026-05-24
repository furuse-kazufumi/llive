# SPDX-License-Identifier: Apache-2.0
"""Extended persona ontology — factor_affinity を記述文から自動算出 (ハードコード排除).

ユーザー指摘 (2026-05-24):
    「(手で付けた factor_affinity の) ハードコード部分はちょっと疑った方が良い」

手書きの affinity ベクトルは根拠が弱く [[feedback_benchmark_honest_disclosure]] に反する。
本 module は各人物の **特性記述文 (``affinity_text``)** から
``persona_corpus_loader.keyword_extractor`` + ``affinity_from_counts`` で
factor_affinity を **自動算出** する。数値は記述テキスト由来なので「なぜこの因子が高いか」を
``affinity_text`` を読めば追える = 疑える形。

設計:

- **数値ハードコードなし**: ``EXTENDED_PERSONA_DATA`` に持つのは
  ``{name, era, fields, thought_patterns, affinity_text}`` のみ。affinity は build 時算出。
- **数百人スケール**: 人物を 1 件追記するだけで拡張できる (手動数値の付与・検算が不要)。
- ``thought_patterns`` は意味ある特性語を別途保持 (keyword_extractor の抽出語は
  FACTOR_KEYWORDS の語そのものになり意味が薄いため、affinity 算出と役割を分離)。
- ``register_extended_personas()`` で ``PERSONA_ONTOLOGY`` に冪等 merge (既存 id は上書きしない)。

honest disclosure: ``affinity_text`` を「FACTOR_KEYWORDS に当たる語で書く」点はなお heuristic。
真の精緻化は LLM injection (``ThoughtPatternExtractor``) か実伝記 corpus (CE-23 後続)。本 module は
「手動数値 → 記述由来の自動算出」への中間段階であり、数値の出所を透明化することが目的。
"""
from __future__ import annotations

from typing import Any

from llive.perf.evolutionary.persona import PERSONA_ONTOLOGY, Persona
from llive.perf.evolutionary.persona_corpus_loader import (
    affinity_from_counts,
    keyword_extractor,
)

# persona_id -> {name, era, fields, thought_patterns, affinity_text}
# affinity_text は FACTOR_KEYWORDS (構造/探索/観測/反復/確率... + 英語) が拾える特性記述文。
# 数百人規模はこの dict (将来は YAML 外部化) に追記するだけで拡張できる。
EXTENDED_PERSONA_DATA: dict[str, dict[str, Any]] = {
    "darwin": {
        "name": "チャールズ・ダーウィン",
        "era": "19C-Biology",
        "fields": ("biology", "evolution", "natural-history"),
        "thought_patterns": ("自然選択", "変異と適応", "系統樹", "漸進", "観察"),
        "affinity_text": (
            "膨大な観測 observation と探索 explore による自然選択の発見 discover novel。"
            "変異を分解 decompose 再構成し、系統樹で起源 origin と履歴 history を辿る来歴 provenance の学。"
            "実験 experiment と現実 reality に基づく empirical。自己 self の成長 growth と適応 extend が漸進する。"
        ),
    },
    "altshuller": {
        "name": "ゲンリッヒ・アルトシュラー",
        "era": "20C-Inventive-Methodology",
        "fields": ("engineering", "inventive-problem-solving", "triz"),
        "thought_patterns": ("矛盾", "40の発明原理", "理想性", "資源", "進化のパターン"),
        "affinity_text": (
            "矛盾を体系 framework 化する構造 structure 的方法。40 の発明原理は分解 decompose と合成 synthesize。"
            "理想性へ多視点 multiple perspective で資源を探索 explore。特許の履歴 history を反復 iterate 分析。"
        ),
    },
    "helmholtz": {
        "name": "ヘルマン・フォン・ヘルムホルツ",
        "era": "19C-Physiology-Physics",
        "fields": ("physiology", "physics", "perception"),
        "thought_patterns": ("無意識的推論", "知覚は推論", "エネルギー保存", "学際", "測定"),
        "affinity_text": (
            "知覚は無意識的な推論であり、不確実 uncertainty な感覚から確率 probability 的に世界を構成 construct する。"
            "生理学の実験 experiment と観測 observation に基づく現実 reality 接続。知覚と行動の反復 loop。学際的な多視点 multiple。"
        ),
    },
    "shannon": {
        "name": "クロード・シャノン",
        "era": "20C-Information-Theory",
        "fields": ("information-theory", "mathematics", "engineering"),
        "thought_patterns": ("情報量", "エントロピー", "符号化", "ノイズと冗長性", "通信路容量"),
        "affinity_text": (
            "情報を体系 framework 化し、エントロピーで不確実 uncertainty を確率 probability 的に定量化。"
            "符号化は厳密 rigorous な証明 proof と整合 consistent。ノイズと冗長性を分解 decompose。"
        ),
    },
    "turing": {
        "name": "アラン・チューリング",
        "era": "20C-Computation",
        "fields": ("computer-science", "mathematics", "cryptography", "biology"),
        "thought_patterns": ("計算可能性", "万能機械", "模倣ゲーム", "形態形成", "暗号解読"),
        "affinity_text": (
            "計算可能性を公理 axiom と構造 structure で定義。万能機械は自己 self を拡張 extend し成長 growth する。"
            "模倣ゲームで未知 novel を探索 explore 発見 discover。形態形成を証明 proof で厳密 rigorous に。暗号を多角 multiple に解読。"
        ),
    },
    "poincare": {
        "name": "アンリ・ポアンカレ",
        "era": "19C-20C-Mathematics",
        "fields": ("mathematics", "physics", "philosophy-of-science"),
        "thought_patterns": ("数学的直観", "無意識の創造", "位相幾何", "三体問題", "規約主義"),
        "affinity_text": (
            "数学的直観は無意識の創造。位相幾何は分解 decompose と合成 synthesize の再構成。"
            "三体問題の確率 probability 的カオスを探索 explore 発見 discover。多視点 multiple perspective の規約主義。"
        ),
    },
    "kahneman": {
        "name": "ダニエル・カーネマン",
        "era": "20C-21C-Cognitive-Psychology",
        "fields": ("psychology", "behavioral-economics", "decision-theory"),
        "thought_patterns": ("二重過程", "認知バイアス", "プロスペクト理論", "ヒューリスティクス", "緩慢な思考"),
        "affinity_text": (
            "二重過程を多視点 multiple perspective で対比。認知バイアスは不確実 uncertainty な判断の確率 probability 的歪み。"
            "プロスペクト理論は心理実験 experiment と観測 observation の現実 reality に基づく。整合 consistent な検証 verify。"
        ),
    },
}


def _build(data: dict[str, dict[str, Any]]) -> dict[str, Persona]:
    """各 entry の affinity_text から factor_affinity を自動算出して Persona を構築."""
    out: dict[str, Persona] = {}
    for pid, d in data.items():
        # affinity は記述文から導出 — 手動ハードコードしない
        _patterns, counts = keyword_extractor([d["affinity_text"]], pid)
        affinity = affinity_from_counts(counts)
        out[pid] = Persona(
            persona_id=pid,
            name=d["name"],
            era=d["era"],
            fields=tuple(d["fields"]),
            thought_patterns=tuple(d["thought_patterns"]),
            factor_affinity=affinity,
        )
    return out


#: build 時に affinity_text から算出された拡張ペルソナ (数値ハードコードなし)。
EXTENDED_PERSONAS: dict[str, Persona] = _build(EXTENDED_PERSONA_DATA)


def register_extended_personas() -> int:
    """``PERSONA_ONTOLOGY`` に拡張ペルソナを冪等 merge する.

    既存 id は上書きしない (古典/研究方法論ペルソナを保護)。返り値 = 新規追加数。
    利用側 (進化ループ / RAD) が本 module を import すると下記の副作用で自動登録される。
    """
    added = 0
    for pid, persona in EXTENDED_PERSONAS.items():
        if pid not in PERSONA_ONTOLOGY:
            PERSONA_ONTOLOGY[pid] = persona
            added += 1
    return added


# import 副作用: 本 module を import した時点で PERSONA_ONTOLOGY を拡張する。
register_extended_personas()


__all__ = [
    "EXTENDED_PERSONA_DATA",
    "EXTENDED_PERSONAS",
    "register_extended_personas",
]
