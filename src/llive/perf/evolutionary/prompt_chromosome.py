# SPDX-License-Identifier: Apache-2.0
"""PromptChromosome — 偉人思想・スキル・ルールを遺伝対象とする chromosome (llive v0.F EV-13 柱 A-2).

v0.B Genome (scalar 19 dim) のプロンプト層は列挙のみだったが, 本 chromosome は
**偉人 persona の組合せ / 思考スキルの bitmask / 運用 rule の bitmask /
prompt template / 言語スタイル / 引用密度** を遺伝対象に持ち上げる. 実際に
LLM に投げる prompt 構造そのものが遺伝対象になる.

形式化 (詳細は `docs/requirements_v0.F_genome_two_layer_and_novelty.md` §2 柱 A-2):

| Gene | 値域 | 例 |
|------|------|----|
| persona_set | bitmask (subset of KNOWN_PROMPT_PERSONAS) | {oka, polya, triz, six_hats, ...} |
| skill_set | bitmask (subset of KNOWN_PROMPT_SKILLS) | {structurize, recompose, loop, ...} |
| rule_set | bitmask (subset of KNOWN_PROMPT_RULES) | {fail_closed, honest_disclosure} |
| prompt_template_id | enum | base / chain_of_thought / tree_of_thought / debate / socratic |
| language_style | enum | terse / verbose / formal / casual / academic |
| historical_quote_density | float [0,1] | persona 引用密度 |

API は :class:`llive.perf.evolutionary.meta_chromosome.MetaChromosome` と
**完全に同型**: default() / to_dict() / from_dict() / kolmogorov_proxy() /
sample_neighborhood().

References:

- llive `docs/requirements_v0.F_genome_two_layer_and_novelty.md` §2 柱 A-2.
- Wang, R. et al. (2024). Promptbreeder ([arXiv:2309.16797](https://arxiv.org/abs/2309.16797)).
- llive COG-MESH PersonaOntology / 10 思考因子 (FR-23 系).

Status (2026-05-22 着地): skeleton. データ構造 + バリデーション + serialization +
neighborhood sampling + Kolmogorov proxy のみ. 実 PromptComposer 統合は
EV-18 以降.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Constants — master lists
# ---------------------------------------------------------------------------

#: 既知 persona id. llive COG-MESH PersonaOntology + 要件 §2 柱 A-2 に挙げられた
#: 偉人セット. 将来 persona_corpus_loader 側の ontology と一元化予定.
KNOWN_PROMPT_PERSONAS: tuple[str, ...] = (
    "oka",          # 岡潔 (情緒 + 国語力)
    "polya",        # G. Polya (How to Solve It)
    "triz",         # Altshuller TRIZ (40 原理 / 矛盾マトリクス)
    "six_hats",     # de Bono Six Thinking Hats
    "bayesian",     # 確率的推論
    "feynman",      # R. Feynman (素朴な再構成 + 教える)
    "kaneko",       # 金子勇 (Winny / EDLA)
)

#: 既知 skill id. llive 10 思考因子 (FR-23..FR-27 系) を skill として展開.
KNOWN_PROMPT_SKILLS: tuple[str, ...] = (
    "structurize",
    "recompose",
    "loop",
    "self_extend",
    "uncertainty",
    "explore",
    "align",
    "provenance",
    "perspective",
    "ground",
)

#: 既知 rule id. llive 運用規約 (CLAUDE.md / memory feedback_*) を rule として展開.
KNOWN_PROMPT_RULES: tuple[str, ...] = (
    "fail_closed",
    "honest_disclosure",
    "no_local_path",
    "no_image_placeholder",
    "approval_bus",
    "quiet_hours",
)

#: 既知 prompt_template_id. 既存 prompt 系の主要 template + 将来枠.
KNOWN_PROMPT_TEMPLATES: tuple[str, ...] = (
    "base",
    "chain_of_thought",
    "tree_of_thought",
    "debate",
    "socratic",
)

#: 既知 language_style. 言語表現の方向性を粗く分類.
KNOWN_PROMPT_LANGUAGE_STYLES: tuple[str, ...] = (
    "terse",
    "verbose",
    "formal",
    "casual",
    "academic",
)


def _validate_subset(
    name: str, values: tuple[str, ...], known: tuple[str, ...]
) -> None:
    """``values`` が ``known`` の subset であることを検証. duplicate も拒否."""
    seen: set[str] = set()
    known_set = set(known)
    for v in values:
        if not isinstance(v, str):
            raise ValueError(f"{name} element must be str, got {type(v)}")
        if v not in known_set:
            raise ValueError(
                f"unknown {name} member '{v}' (known={known})"
            )
        if v in seen:
            raise ValueError(f"duplicate {name} member '{v}'")
        seen.add(v)


def _coerce_tuple(values: Iterable[Any]) -> tuple[str, ...]:
    """from_dict 用. list/tuple を str tuple に正規化."""
    return tuple(str(v) for v in values)


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PromptChromosome:
    """プロンプト的選択 (思想・スキル・ルール) を遺伝対象とする frozen chromosome.

    v0.F 2 階建てゲノムの 2 階目 (要件 §2 柱 A-2). 将来
    ``Genome3D = (ImplChromosome, PromptChromosome, MetaChromosome)`` の 2 階目
    として組み込まれる. skeleton 段階では既存 Genome / MetaChromosome と
    **stand-alone** で共存する.

    集合 field (persona_set / skill_set / rule_set) は frozen を保つため
    ``tuple[str, ...]`` で表現する. 重複・未知メンバは __post_init__ で拒否.
    """

    #: 採用 persona の subset (KNOWN_PROMPT_PERSONAS から重複なし).
    persona_set: tuple[str, ...]

    #: 採用 skill の subset (KNOWN_PROMPT_SKILLS から重複なし).
    skill_set: tuple[str, ...]

    #: 採用 rule の subset (KNOWN_PROMPT_RULES から重複なし).
    rule_set: tuple[str, ...]

    #: prompt template id (KNOWN_PROMPT_TEMPLATES のいずれか).
    prompt_template_id: str

    #: 言語スタイル (KNOWN_PROMPT_LANGUAGE_STYLES のいずれか).
    language_style: str

    #: 偉人引用密度 [0.0, 1.0]. 1.0 = 引用多, 0.0 = 引用無し.
    historical_quote_density: float

    # ----- validation -----------------------------------------------------

    def __post_init__(self) -> None:
        # persona / skill / rule: subset の検証
        _validate_subset("persona_set", self.persona_set, KNOWN_PROMPT_PERSONAS)
        _validate_subset("skill_set", self.skill_set, KNOWN_PROMPT_SKILLS)
        _validate_subset("rule_set", self.rule_set, KNOWN_PROMPT_RULES)

        # prompt_template_id
        if self.prompt_template_id not in KNOWN_PROMPT_TEMPLATES:
            raise ValueError(
                f"unknown prompt_template_id '{self.prompt_template_id}' "
                f"(known={KNOWN_PROMPT_TEMPLATES})"
            )

        # language_style
        if self.language_style not in KNOWN_PROMPT_LANGUAGE_STYLES:
            raise ValueError(
                f"unknown language_style '{self.language_style}' "
                f"(known={KNOWN_PROMPT_LANGUAGE_STYLES})"
            )

        # historical_quote_density
        if not 0.0 <= self.historical_quote_density <= 1.0:
            raise ValueError(
                f"historical_quote_density {self.historical_quote_density} "
                f"not in [0,1]"
            )

    # ----- factories ------------------------------------------------------

    @classmethod
    def default(cls) -> PromptChromosome:
        """v0.B baseline 互換のデフォルト.

        最低限の persona (polya + triz) + 基本 skill (structurize + ground) +
        中核 rule (fail_closed + honest_disclosure) + base template.
        """
        return cls(
            persona_set=("polya", "triz"),
            skill_set=("structurize", "ground"),
            rule_set=("fail_closed", "honest_disclosure"),
            prompt_template_id="base",
            language_style="terse",
            historical_quote_density=0.1,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PromptChromosome:
        return cls(
            persona_set=_coerce_tuple(data["persona_set"]),
            skill_set=_coerce_tuple(data["skill_set"]),
            rule_set=_coerce_tuple(data["rule_set"]),
            prompt_template_id=str(data["prompt_template_id"]),
            language_style=str(data["language_style"]),
            historical_quote_density=float(data["historical_quote_density"]),
        )

    # ----- serialization --------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "persona_set": list(self.persona_set),
            "skill_set": list(self.skill_set),
            "rule_set": list(self.rule_set),
            "prompt_template_id": self.prompt_template_id,
            "language_style": self.language_style,
            "historical_quote_density": self.historical_quote_density,
        }

    def to_json_bytes(self) -> bytes:
        """JSON 化して bytes 化 (Kolmogorov complexity proxy 用).

        集合 field は元の順序を保つ (sort_keys=True は top-level key にのみ作用).
        """
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False).encode(
            "utf-8"
        )

    # ----- Kolmogorov complexity proxy ------------------------------------

    def kolmogorov_proxy(self) -> int:
        """gzip 圧縮後 byte 数. Kolmogorov complexity の計算可能近似.

        persona_set / skill_set / rule_set のメンバが多いほど proxy 値が増える.
        """
        return len(gzip.compress(self.to_json_bytes()))

    # ----- neighborhood sampling ------------------------------------------

    def sample_neighborhood(
        self,
        rng: np.random.Generator,
        step_size: float = 0.1,
    ) -> PromptChromosome:
        """近傍 chromosome を 1 つ sample.

        - 集合 field (persona/skill/rule): 各既知メンバを確率 ``step_size`` で
          flip (在 → 不在 / 不在 → 在). step_size=0.0 で完全に不変, =1.0 で
          全 bit を反転.
        - discrete enum (prompt_template_id / language_style): 確率
          ``step_size`` で別の候補へ switch.
        - continuous (historical_quote_density): Gaussian perturbation + clip.

        skeleton 段階では full evolution は実装しない. EvolutionLoop と統合
        された段階 (EV-14 以降) で本格化.
        """
        flip_prob = float(np.clip(step_size, 0.0, 1.0))

        def _flip_subset(
            current: tuple[str, ...], known: tuple[str, ...]
        ) -> tuple[str, ...]:
            current_set = set(current)
            new: list[str] = []
            for member in known:
                is_in = member in current_set
                # 確率 flip_prob で flip
                if rng.random() < flip_prob:
                    is_in = not is_in
                if is_in:
                    new.append(member)
            return tuple(new)

        new_persona = _flip_subset(self.persona_set, KNOWN_PROMPT_PERSONAS)
        new_skill = _flip_subset(self.skill_set, KNOWN_PROMPT_SKILLS)
        new_rule = _flip_subset(self.rule_set, KNOWN_PROMPT_RULES)

        new_template = (
            str(rng.choice(KNOWN_PROMPT_TEMPLATES))
            if rng.random() < flip_prob
            else self.prompt_template_id
        )
        new_style = (
            str(rng.choice(KNOWN_PROMPT_LANGUAGE_STYLES))
            if rng.random() < flip_prob
            else self.language_style
        )

        new_density = float(
            np.clip(
                self.historical_quote_density + rng.normal(0, step_size),
                0.0,
                1.0,
            )
        )

        return PromptChromosome(
            persona_set=new_persona,
            skill_set=new_skill,
            rule_set=new_rule,
            prompt_template_id=new_template,
            language_style=new_style,
            historical_quote_density=new_density,
        )


__all__ = [
    "KNOWN_PROMPT_LANGUAGE_STYLES",
    "KNOWN_PROMPT_PERSONAS",
    "KNOWN_PROMPT_RULES",
    "KNOWN_PROMPT_SKILLS",
    "KNOWN_PROMPT_TEMPLATES",
    "PromptChromosome",
]
