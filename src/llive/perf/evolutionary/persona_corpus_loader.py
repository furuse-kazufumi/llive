# SPDX-License-Identifier: Apache-2.0
"""PersonaCorpusLoader (v0.E CE-23 / Phase E.13) — skeleton.

ユーザー指示 (2026-05-21):
    「Raptor RAD コーパス (学術論文 / 伝記 / 哲学書) から persona の thought
     pattern を auto 抽出して PERSONA_ONTOLOGY を拡張したい」

CE-23 は **外部 corpus 依存 + LLM 依存** のため本 module は skeleton:

- **Loader 入口** (``PersonaCorpusLoader``): corpus path or text snippets を
  受け取り, 抽出済み ``Persona`` 候補 dict を返す.
- **LLM injection** (``ThoughtPatternExtractor`` Protocol): LLM 呼び出し
  ロジックは外部 injection. なければ単純 keyword counting fallback
  (テスト + offline 動作のため).
- **Heuristic factor_affinity** — keyword presence / weights から 10 思考
  因子の affinity vector を推定 (簡易 heuristic, [0, 1]).
- **export**: 抽出結果を YAML/JSON に書き出して既存 PERSONA_ONTOLOGY に
  merge できる形 (``Persona.from_dict`` 互換).

実装範囲 (skeleton):
- offline 動作する **keyword-based fallback extractor**
- LLM injection の Protocol 定義
- factor_affinity 推定 heuristic
- merge helper (既存 ontology に新 persona を追加)

外部 corpus 解析 (実 RAD path 横断 / LLM 呼出し) は後続フェーズ.

要件根拠: ``docs/requirements_v0.E_competitive_coevolution.md`` CE-23 + E.13
+ [[project_rad_expansion_2026_05]] memory.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from llive.perf.evolutionary.persona import (
    PERSONA_ONTOLOGY,
    THOUGHT_FACTORS,
    Persona,
)

# ---------------------------------------------------------------------------
# ThoughtPatternExtractor Protocol — LLM injection point
# ---------------------------------------------------------------------------


class ThoughtPatternExtractor(Protocol):
    """corpus snippet から thought patterns + factor weights を抽出する関数.

    Implementations may use LLMs, regex, or heuristics. Output:

    Returns
    -------
    tuple[tuple[str, ...], dict[str, float]]
        (thought_patterns, factor_keyword_counts).
        thought_patterns: 抽出された 3-5 個の特性キーワード.
        factor_keyword_counts: factor_name → 出現回数 dict (THOUGHT_FACTORS の
        いずれか). 後段で affinity に正規化される.
    """

    def __call__(
        self, snippets: Sequence[str], persona_id: str
    ) -> tuple[tuple[str, ...], dict[str, float]]: ...


# ---------------------------------------------------------------------------
# Keyword-based fallback extractor (offline, no LLM)
# ---------------------------------------------------------------------------


# 10 思考因子 ↔ 代表キーワード mapping (日本語 + 英語 mixed, 簡易 heuristic)
# 公開プロジェクトと整合させる必要があり, 過剰に長くしない.
FACTOR_KEYWORDS: dict[str, tuple[str, ...]] = {
    "factor_structurize": (
        "structure",
        "framework",
        "axiom",
        "construct",
        "公理",
        "構造",
        "体系",
    ),
    "factor_recompose": (
        "rearrange",
        "decompose",
        "synthesize",
        "再構成",
        "分解",
        "合成",
    ),
    "factor_closed_loop": (
        "feedback",
        "loop",
        "iterate",
        "self-correct",
        "閉ループ",
        "反復",
        "自己修正",
    ),
    "factor_self_extend": (
        "self",
        "growth",
        "extend",
        "autopoiesis",
        "自己拡張",
        "成長",
    ),
    "factor_uncertainty": (
        "uncertainty",
        "probability",
        "stochastic",
        "不確実",
        "確率",
        "確証",
    ),
    "factor_exploration": (
        "explore",
        "discover",
        "novel",
        "wander",
        "探索",
        "発見",
        "未知",
    ),
    "factor_consistency": (
        "consistent",
        "rigorous",
        "proof",
        "verify",
        "整合",
        "厳密",
        "証明",
    ),
    "factor_provenance": (
        "history",
        "origin",
        "provenance",
        "trace",
        "由来",
        "起源",
        "履歴",
    ),
    "factor_multiview": (
        "multiple",
        "perspective",
        "viewpoint",
        "polysemy",
        "多視点",
        "多角",
    ),
    "factor_reality_link": (
        "reality",
        "empirical",
        "experiment",
        "observation",
        "現実",
        "実験",
        "観測",
    ),
}


def _count_keywords(snippets: Sequence[str], keywords: Sequence[str]) -> int:
    """case-insensitive substring count."""
    lc = [s.lower() for s in snippets]
    total = 0
    for kw in keywords:
        kw_lc = kw.lower()
        for s in lc:
            total += s.count(kw_lc)
    return total


def keyword_extractor(
    snippets: Sequence[str], persona_id: str
) -> tuple[tuple[str, ...], dict[str, float]]:
    """Keyword counting fallback extractor (LLM 不要, offline 動作可能).

    Returns
    -------
    thought_patterns : tuple[str, ...]
        ヒット数上位の代表キーワード (最大 5 個).
    factor_keyword_counts : dict[str, float]
        各 thought factor のヒット総数.
    """
    counts: dict[str, float] = {}
    per_keyword_hits: dict[str, int] = {}
    for factor, keywords in FACTOR_KEYWORDS.items():
        for kw in keywords:
            hits = _count_keywords(snippets, [kw])
            if hits > 0:
                per_keyword_hits[kw] = per_keyword_hits.get(kw, 0) + hits
        counts[factor] = float(
            sum(per_keyword_hits.get(kw, 0) for kw in keywords)
        )
    # 代表 keyword tuple (count 順, top 5)
    sorted_kws = sorted(
        per_keyword_hits.items(), key=lambda item: item[1], reverse=True
    )
    thought_patterns = tuple(kw for kw, _ in sorted_kws[:5])
    return thought_patterns, counts


# ---------------------------------------------------------------------------
# Affinity heuristic — counts → [0, 1] vector
# ---------------------------------------------------------------------------


def affinity_from_counts(counts: Mapping[str, float]) -> tuple[float, ...]:
    """factor 別 keyword count から [0, 1] affinity vector に正規化.

    log1p で大きい count を圧縮 → max-normalize. 全 0 のとき (0.5,)*N を返し
    "情報無し中央" にする.
    """
    raw = np.array(
        [math.log1p(counts.get(f, 0.0)) for f in THOUGHT_FACTORS],
        dtype=np.float64,
    )
    if raw.max() <= 0.0:
        return tuple(0.5 for _ in THOUGHT_FACTORS)
    norm = raw / raw.max()
    return tuple(float(x) for x in norm)


# ---------------------------------------------------------------------------
# PersonaCorpusLoader
# ---------------------------------------------------------------------------


@dataclass
class PersonaCandidate:
    """抽出途中の persona 候補. 既存 ``Persona`` に変換可能."""

    persona_id: str
    name: str
    era: str = "unknown"
    fields: tuple[str, ...] = ()
    snippets: list[str] = field(default_factory=list)
    extracted_patterns: tuple[str, ...] = ()
    extracted_affinity: tuple[float, ...] = ()

    def to_persona(self) -> Persona:
        affinity = self.extracted_affinity or tuple(0.5 for _ in THOUGHT_FACTORS)
        return Persona(
            persona_id=self.persona_id,
            name=self.name,
            era=self.era,
            fields=self.fields,
            thought_patterns=self.extracted_patterns,
            factor_affinity=affinity,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "persona_id": self.persona_id,
            "name": self.name,
            "era": self.era,
            "fields": list(self.fields),
            "snippets": list(self.snippets),
            "extracted_patterns": list(self.extracted_patterns),
            "extracted_affinity": list(self.extracted_affinity),
        }


@dataclass
class PersonaCorpusLoader:
    """corpus snippets → Persona 候補生成 skeleton.

    Attributes
    ----------
    extractor : ThoughtPatternExtractor
        snippet → (patterns, factor_counts) 抽出関数. デフォルトは
        offline 動作する keyword_extractor.
    """

    extractor: ThoughtPatternExtractor = field(default=keyword_extractor)

    def extract(
        self,
        persona_id: str,
        name: str,
        snippets: Sequence[str],
        *,
        era: str = "unknown",
        fields: Sequence[str] = (),
    ) -> PersonaCandidate:
        """1 名分の snippets を抽出して PersonaCandidate を返す."""
        patterns, counts = self.extractor(snippets, persona_id)
        affinity = affinity_from_counts(counts)
        return PersonaCandidate(
            persona_id=persona_id,
            name=name,
            era=era,
            fields=tuple(fields),
            snippets=list(snippets),
            extracted_patterns=patterns,
            extracted_affinity=affinity,
        )

    def extract_many(
        self,
        items: Iterable[
            tuple[str, str, Sequence[str], str, Sequence[str]]
        ],
    ) -> list[PersonaCandidate]:
        """複数 (persona_id, name, snippets, era, fields) を一括抽出.

        Returns
        -------
        list[PersonaCandidate]
        """
        out: list[PersonaCandidate] = []
        for persona_id, name, snippets, era, fields in items:
            out.append(
                self.extract(
                    persona_id,
                    name,
                    snippets,
                    era=era,
                    fields=fields,
                )
            )
        return out

    @staticmethod
    def merge_into_ontology(
        candidates: Iterable[PersonaCandidate],
        *,
        ontology: dict[str, Persona] | None = None,
        overwrite: bool = False,
    ) -> dict[str, Persona]:
        """既存 ontology に新 candidates を追加した新 dict を返す.

        副作用なし: ``PERSONA_ONTOLOGY`` 自体を mutate しない.

        Parameters
        ----------
        candidates : Iterable[PersonaCandidate]
        ontology : dict | None
            基底 ontology. None なら ``PERSONA_ONTOLOGY`` をコピー.
        overwrite : bool
            既存 id があるとき上書きするか. False なら skip.
        """
        base: dict[str, Persona] = (
            dict(PERSONA_ONTOLOGY) if ontology is None else dict(ontology)
        )
        for c in candidates:
            if c.persona_id in base and not overwrite:
                continue
            base[c.persona_id] = c.to_persona()
        return base


# ---------------------------------------------------------------------------
# Optional: corpus path discovery helper (offline-safe)
# ---------------------------------------------------------------------------


def find_persona_snippets_in_text_file(
    path: Path | str, name_aliases: Sequence[str], *, context_chars: int = 200
) -> list[str]:
    """テキストファイル 1 本から persona name のヒット近傍を切り出す.

    name_aliases にある語の前後 ``context_chars`` 字を 1 snippet にする.
    Encoding fallback: utf-8 → cp932 (Windows). 読み込み失敗時は空 list.
    """
    p = Path(path)
    if not p.exists() or not p.is_file():
        return []
    text: str | None = None
    for encoding in ("utf-8", "cp932"):
        try:
            text = p.read_text(encoding=encoding)
            break
        except (UnicodeDecodeError, OSError):
            continue
    if text is None:
        return []
    snippets: list[str] = []
    lower = text.lower()
    for alias in name_aliases:
        alias_lc = alias.lower()
        start = 0
        while True:
            idx = lower.find(alias_lc, start)
            if idx < 0:
                break
            lo = max(0, idx - context_chars)
            hi = min(len(text), idx + len(alias) + context_chars)
            snippets.append(text[lo:hi])
            start = idx + len(alias)
    return snippets


__all__ = [
    "FACTOR_KEYWORDS",
    "PersonaCandidate",
    "PersonaCorpusLoader",
    "ThoughtPatternExtractor",
    "affinity_from_counts",
    "find_persona_snippets_in_text_file",
    "keyword_extractor",
]
