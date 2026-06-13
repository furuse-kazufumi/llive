# SPDX-License-Identifier: Apache-2.0
"""Genome duplication wrappers (llive v0.F EV-17 柱 A-3).

ユーザー指摘 (2026-05-22 深夜): 「あるものはゲノムが重複していたり、並列処理して
いる進化や突然変異があると面白いかもしれません」.

生物学的原型: シダ植物・酵母の **Whole Genome Duplication (WGD)**, バクテリアの
**Horizontal Gene Transfer (HGT)**, 神経 ensemble の **並列 spike**. 進化計算では
これに相当する操作が個別実装されてきたが (NEAT 構造遺伝, AutoML-Zero の op 複製
など), 本 module はそれを **集団内多重度 (multiplicity)** という統一概念で扱う
skeleton を提供する.

設計方針:

- :class:`IndividualWithMultiplicity` は **genome 自体を変えない wrapper**. 集団内に
  同じ genome ID を持つコピーが複数存在することを ``multiplicity`` field で表す.
  genome の内容を変えたい場合は :func:`parallel_mutate` で N 個の独立変異を生成し
  個別の Individual として扱う.
- ``duplication_origin`` は **なぜ重複したか** を記録する 4 値 enum.
  :class:`DuplicationOrigin` の各値は PhyTree の edge op
  (``crossover`` / ``mutation`` / ``clone``) とは独立の **個体生成 origin** を表す.
- ``parent_id`` は clone/fork 元の SHA-256 content ID (PhyTree compute_individual_id
  と一致). seed (初期集団) では None.

形式化 (詳細は `docs/requirements_v0.F_*.md` §3 柱 A-3):

| Origin | 意味 | 典型用例 |
|--------|------|---------|
| CLONE | 単純コピー (multiplicity 増殖) | winners を倍に増やして次世代に温存 |
| WGD | 全染色体重複 | 進化ジャンプ (シダ植物的) |
| HORIZONTAL_TRANSFER | 別系統からの取り込み | island migration / cross-substrate import |
| PARALLEL_FORK | 並列突然変異の起点 | 1 個体から N 独立変異を spawn |

References:

- Wolfe, K. H., & Shields, D. C. (1997). Molecular evidence for an ancient
  duplication of the entire yeast genome. *Nature* 387, 708–713.
- Real, E. et al. (2020). AutoML-Zero ([arXiv:2003.03384](https://arxiv.org/abs/2003.03384)).
- llive `docs/requirements_v0.F_genome_two_layer_and_novelty.md` §3 柱 A-3.

Status (2026-05-22 着地): skeleton. データ構造 + バリデーション + serialization
のみ. 実 EvolutionLoop / Population 統合は次フェーズ.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class DuplicationOrigin(StrEnum):
    """個体重複の origin (生成由来).

    PhyTree edge op (``crossover`` / ``mutation`` / ``clone``) とは独立で,
    **なぜこの個体が集団に存在するのか** を表すマーカー. UI / 可視化 / 統計
    分析時の groupby key として使う.
    """

    CLONE = "clone"
    """単純コピー (winners 増殖). genome は parent と完全同一."""

    WGD = "whole_genome_duplication"
    """全染色体重複 (進化ジャンプ). multiplicity ≥ 2, 後続 mutation の起点."""

    HORIZONTAL_TRANSFER = "horizontal_transfer"
    """別系統 / 別 island / 別 substrate からの取り込み."""

    PARALLEL_FORK = "parallel_fork"
    """並列突然変異の起点. parallel_mutate で生成された個体の元種."""


#: 既知 DuplicationOrigin 値. validation / export 用.
KNOWN_DUPLICATION_ORIGINS: tuple[str, ...] = tuple(o.value for o in DuplicationOrigin)


@dataclass(frozen=True)
class IndividualWithMultiplicity:
    """重複情報を持つ個体 wrapper. frozen / immutable / JSON-serializable.

    **genome 自体は変えない**. 集団内に同じ genome を持つコピーが N 個存在する
    ことを ``multiplicity`` field で表現する. genome の内容を変えたい場合は
    :func:`parallel_mutate` で N 個の独立変異を spawn し, それぞれを別 instance
    として扱う.
    """

    #: SHA-256 content ID. PhyTree.compute_individual_id と整合.
    genome_id: str

    #: 集団内多重度. 1 = 通常, N>1 = N コピー存在.
    multiplicity: int

    #: 重複の origin. :class:`DuplicationOrigin` のいずれか.
    duplication_origin: DuplicationOrigin

    #: 元個体 ID (clone/fork 元). seed (初期集団) では None.
    parent_id: str | None = None

    # ----- validation -----------------------------------------------------

    def __post_init__(self) -> None:
        if not isinstance(self.genome_id, str) or not self.genome_id:
            raise ValueError("genome_id must be a non-empty str")
        if self.multiplicity < 1:
            raise ValueError(
                f"multiplicity {self.multiplicity} < 1 — 個体は最低 1 体存在せねばならない"
            )
        if not isinstance(self.duplication_origin, DuplicationOrigin):
            raise ValueError(
                f"duplication_origin must be DuplicationOrigin, "
                f"got {type(self.duplication_origin).__name__}"
            )
        if self.parent_id is not None and (
            not isinstance(self.parent_id, str) or not self.parent_id
        ):
            raise ValueError("parent_id must be None or non-empty str")

    # ----- serialization --------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """JSON 化可能な dict 化. ``duplication_origin`` は str value で展開."""
        return {
            "genome_id": self.genome_id,
            "multiplicity": self.multiplicity,
            "duplication_origin": self.duplication_origin.value,
            "parent_id": self.parent_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> IndividualWithMultiplicity:
        """``to_dict()`` round-trip 対応の復元."""
        origin_raw = data["duplication_origin"]
        if isinstance(origin_raw, DuplicationOrigin):
            origin = origin_raw
        else:
            origin = DuplicationOrigin(str(origin_raw))
        return cls(
            genome_id=str(data["genome_id"]),
            multiplicity=int(data["multiplicity"]),
            duplication_origin=origin,
            parent_id=(
                None if data.get("parent_id") is None else str(data["parent_id"])
            ),
        )


__all__ = [
    "KNOWN_DUPLICATION_ORIGINS",
    "DuplicationOrigin",
    "IndividualWithMultiplicity",
]
