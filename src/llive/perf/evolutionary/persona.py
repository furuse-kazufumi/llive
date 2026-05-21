# SPDX-License-Identifier: Apache-2.0
"""Historical Persona Ontology + PersonaCompositionMutation (v0.E CE-19/21/22).

ユーザー指示 (2026-05-21):
    「数学面において岡潔を軸に思考パターンを構築したように, 各 llive 亜種が
    有名な人物の思考パターンを調べて, 自身の思考アルゴリズムに取り込んで
    いくようなアルゴリズムが必要になります」

既存実装 [[project-llive-oka]] OKA-FX (岡潔: 情緒/行き詰まり/文章化/国語力)
が「歴史人物 1 名」の先例. 本 module はそれを集団内 multi-persona に拡張.

設計判断:

- ``Persona`` dataclass: 1 人物 = (id, name, era, fields, thought_patterns,
  factor_affinity).  factor_affinity は llive 10 思考因子上の per-factor 親和度.
- ``PERSONA_ONTOLOGY``: 最初の 10 名 (岡潔 / グロタンディーク / ファインマン /
  ガロア / フォン・ノイマン / ニュートン / カント / ソクラテス / 老子 / 孫子).
- ``PersonaComposition``: 複数 persona の組合せ (id+weight). normalize 推奨.
- ``PersonaCompositionMutation``: composition の組合せ変更 (1 名 swap / weight 摂動).
- ``persona_dissimilarity``: 2 個 composition の Jaccard + factor_affinity L2.

要件根拠: ``docs/requirements_v0.E_competitive_coevolution.md`` 0.7 節.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

import numpy as np


# ---------------------------------------------------------------------------
# Persona dataclass + ontology
# ---------------------------------------------------------------------------


THOUGHT_FACTORS: tuple[str, ...] = (
    "factor_structurize",
    "factor_recompose",
    "factor_closed_loop",
    "factor_self_extend",
    "factor_uncertainty",
    "factor_exploration",
    "factor_consistency",
    "factor_provenance",
    "factor_multiview",
    "factor_reality_link",
)


@dataclass(frozen=True)
class Persona:
    """1 人物の思考パターン.

    Attributes
    ----------
    persona_id : str
        kebab-case slug (例: "oka-kiyoshi").
    name : str
        Display 名.
    era : str
        概念的時代区分 (例: "20C-Mathematics").
    fields : tuple[str, ...]
        専門分野タグ (例: ("mathematics", "philosophy")).
    thought_patterns : tuple[str, ...]
        言語化された思考特性のキーワード 3-5 個.
    factor_affinity : tuple[float, ...]
        10 思考因子上の親和度 [0, 1]. THOUGHT_FACTORS 順.
    """

    persona_id: str
    name: str
    era: str
    fields: tuple[str, ...]
    thought_patterns: tuple[str, ...]
    factor_affinity: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.factor_affinity) != len(THOUGHT_FACTORS):
            raise ValueError(
                f"factor_affinity len {len(self.factor_affinity)} != "
                f"{len(THOUGHT_FACTORS)}"
            )
        for v in self.factor_affinity:
            if not (0.0 <= float(v) <= 1.0):
                raise ValueError(f"factor_affinity values must be in [0,1], got {v}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "persona_id": self.persona_id,
            "name": self.name,
            "era": self.era,
            "fields": list(self.fields),
            "thought_patterns": list(self.thought_patterns),
            "factor_affinity": list(self.factor_affinity),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Persona:
        return cls(
            persona_id=str(data["persona_id"]),
            name=str(data["name"]),
            era=str(data["era"]),
            fields=tuple(data.get("fields", [])),
            thought_patterns=tuple(data.get("thought_patterns", [])),
            factor_affinity=tuple(float(v) for v in data["factor_affinity"]),
        )


# 初期 ontology (10 名). factor_affinity は heuristic で付与, 出典は
# 一般的な伝記 / 哲学史 / 数学史. 後の corpus 自動抽出 (CE-23) で精緻化される.
PERSONA_ONTOLOGY: dict[str, Persona] = {
    "oka-kiyoshi": Persona(
        persona_id="oka-kiyoshi",
        name="岡潔",
        era="20C-Mathematics",
        fields=("mathematics", "philosophy", "literature"),
        thought_patterns=("情緒", "行き詰まり", "文章化", "国語力", "多変数函数"),
        # 来歴 / 多視点 / 整合 / 自己拡張 が高め. exploration は中.
        factor_affinity=(0.5, 0.6, 0.5, 0.8, 0.4, 0.5, 0.8, 0.9, 0.7, 0.6),
    ),
    "grothendieck": Persona(
        persona_id="grothendieck",
        name="アレクサンドル・グロタンディーク",
        era="20C-Mathematics",
        fields=("mathematics", "algebraic-geometry"),
        thought_patterns=("普遍性", "圏論", "抽象化", "scheme", "rising-sea"),
        factor_affinity=(0.95, 0.9, 0.6, 0.95, 0.5, 0.8, 0.85, 0.6, 0.85, 0.4),
    ),
    "feynman": Persona(
        persona_id="feynman",
        name="リチャード・ファインマン",
        era="20C-Physics",
        fields=("physics", "education"),
        thought_patterns=("好奇心", "直感", "具体例", "diagram", "play"),
        factor_affinity=(0.6, 0.7, 0.5, 0.8, 0.7, 0.95, 0.7, 0.6, 0.8, 0.9),
    ),
    "galois": Persona(
        persona_id="galois",
        name="エヴァリスト・ガロア",
        era="19C-Mathematics",
        fields=("mathematics", "algebra"),
        thought_patterns=("群論", "対称性", "革命的視点", "若き天才"),
        factor_affinity=(0.9, 0.95, 0.4, 0.7, 0.6, 0.85, 0.7, 0.5, 0.7, 0.3),
    ),
    "von-neumann": Persona(
        persona_id="von-neumann",
        name="ジョン・フォン・ノイマン",
        era="20C-Universalist",
        fields=("mathematics", "computer-science", "economics", "physics"),
        thought_patterns=("汎用性", "高速", "ゲーム理論", "アーキテクチャ"),
        factor_affinity=(0.85, 0.85, 0.7, 0.9, 0.6, 0.7, 0.85, 0.8, 0.9, 0.85),
    ),
    "newton": Persona(
        persona_id="newton",
        name="アイザック・ニュートン",
        era="17C-Universalist",
        fields=("mathematics", "physics", "alchemy"),
        thought_patterns=("巨人の肩", "演繹", "分析", "微積分"),
        factor_affinity=(0.9, 0.7, 0.6, 0.7, 0.5, 0.7, 0.85, 0.9, 0.5, 0.8),
    ),
    "kant": Persona(
        persona_id="kant",
        name="イマヌエル・カント",
        era="18C-Philosophy",
        fields=("philosophy", "ethics"),
        thought_patterns=("純粋理性", "批判", "カテゴリ", "アプリオリ"),
        factor_affinity=(0.95, 0.7, 0.7, 0.6, 0.6, 0.5, 0.95, 0.9, 0.85, 0.5),
    ),
    "socrates": Persona(
        persona_id="socrates",
        name="ソクラテス",
        era="Classical-Antiquity-Philosophy",
        fields=("philosophy",),
        thought_patterns=("問答法", "無知の知", "助産術"),
        factor_affinity=(0.6, 0.7, 0.9, 0.7, 0.95, 0.8, 0.6, 0.7, 0.95, 0.7),
    ),
    "laozi": Persona(
        persona_id="laozi",
        name="老子",
        era="Classical-Antiquity-Philosophy",
        fields=("philosophy", "taoism"),
        thought_patterns=("無為自然", "反転思考", "柔よく剛を制す"),
        factor_affinity=(0.4, 0.95, 0.85, 0.5, 0.9, 0.6, 0.7, 0.5, 0.9, 0.85),
    ),
    "sun-tzu": Persona(
        persona_id="sun-tzu",
        name="孫子",
        era="Classical-Antiquity-Strategy",
        fields=("strategy", "military"),
        thought_patterns=("兵法", "勢", "虚実", "勝兵先勝"),
        factor_affinity=(0.85, 0.85, 0.7, 0.6, 0.9, 0.7, 0.8, 0.6, 0.85, 0.95),
    ),
}


def list_persona_ids() -> tuple[str, ...]:
    return tuple(sorted(PERSONA_ONTOLOGY.keys()))


def get_persona(persona_id: str) -> Persona:
    if persona_id not in PERSONA_ONTOLOGY:
        raise KeyError(f"unknown persona_id: {persona_id!r}")
    return PERSONA_ONTOLOGY[persona_id]


# ---------------------------------------------------------------------------
# PersonaComposition (個体の persona 組合せ)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PersonaComposition:
    """1 派生個体に紐付く persona 組合せ.

    Attributes
    ----------
    persona_ids : tuple[str, ...]
        採用 persona id 列 (重複なし).
    weights : tuple[float, ...]
        各 persona の比重. sum=1.0 推奨 (normalize_weights で正規化).
    import_policy : str
        ``"exclusive"`` (1 名で固定) / ``"mix"`` (重み付け平均) /
        ``"moderator"`` (1 名が議長, 他は参加).
    """

    persona_ids: tuple[str, ...]
    weights: tuple[float, ...]
    import_policy: str = "mix"

    def __post_init__(self) -> None:
        if not self.persona_ids:
            raise ValueError("persona_ids must be non-empty")
        if len(self.persona_ids) != len(self.weights):
            raise ValueError("persona_ids and weights must have equal length")
        if len(set(self.persona_ids)) != len(self.persona_ids):
            raise ValueError("persona_ids must be unique")
        for w in self.weights:
            if w < 0:
                raise ValueError(f"weights must be >= 0, got {w}")
        if self.import_policy not in ("exclusive", "mix", "moderator"):
            raise ValueError(f"unknown import_policy: {self.import_policy!r}")
        for pid in self.persona_ids:
            if pid not in PERSONA_ONTOLOGY:
                raise ValueError(f"unknown persona_id in composition: {pid!r}")

    def normalize_weights(self) -> PersonaComposition:
        total = sum(self.weights)
        if total <= 0:
            # 等分 fallback
            n = len(self.weights)
            return PersonaComposition(
                persona_ids=self.persona_ids,
                weights=tuple(1.0 / n for _ in range(n)),
                import_policy=self.import_policy,
            )
        return PersonaComposition(
            persona_ids=self.persona_ids,
            weights=tuple(float(w / total) for w in self.weights),
            import_policy=self.import_policy,
        )

    def effective_factor_affinity(self) -> np.ndarray:
        """weight 加重平均の thought-factor affinity vector を返す.

        ``import_policy='exclusive'`` のとき weights[0] 個の persona のみ使う.
        ``import_policy='moderator'`` のとき moderator (= persona_ids[0]) の
        weight を 2x にしてから normalize する (議長補正).
        """
        normalized = self.normalize_weights()
        weights = np.asarray(normalized.weights, dtype=np.float64)
        if self.import_policy == "exclusive":
            mask = np.zeros_like(weights)
            mask[0] = 1.0
            weights = mask
        elif self.import_policy == "moderator":
            adj = weights.copy()
            adj[0] *= 2.0
            adj /= adj.sum()
            weights = adj
        affinity = np.zeros(len(THOUGHT_FACTORS), dtype=np.float64)
        for pid, w in zip(self.persona_ids, weights, strict=True):
            persona = PERSONA_ONTOLOGY[pid]
            affinity += w * np.asarray(persona.factor_affinity, dtype=np.float64)
        return affinity

    def to_dict(self) -> dict[str, Any]:
        return {
            "persona_ids": list(self.persona_ids),
            "weights": list(self.weights),
            "import_policy": self.import_policy,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PersonaComposition:
        return cls(
            persona_ids=tuple(data["persona_ids"]),
            weights=tuple(float(w) for w in data["weights"]),
            import_policy=str(data.get("import_policy", "mix")),
        )


def random_persona_composition(
    rng: random.Random | np.random.Generator,
    *,
    n: int = 3,
    import_policy: str = "mix",
) -> PersonaComposition:
    """ontology からランダムに n 名選び composition を作る."""
    ids = list(PERSONA_ONTOLOGY.keys())
    if n > len(ids):
        raise ValueError(f"n ({n}) > ontology size ({len(ids)})")
    if isinstance(rng, np.random.Generator):
        idx = rng.choice(len(ids), size=n, replace=False)
        chosen = tuple(ids[int(i)] for i in idx)
        weights = tuple(float(rng.uniform(0.1, 1.0)) for _ in range(n))
    else:
        chosen = tuple(rng.sample(ids, n))
        weights = tuple(rng.uniform(0.1, 1.0) for _ in range(n))
    return PersonaComposition(
        persona_ids=chosen, weights=weights, import_policy=import_policy
    ).normalize_weights()


# ---------------------------------------------------------------------------
# PersonaCompositionMutation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PersonaCompositionMutation:
    """PersonaComposition の組合せ変更 mutation.

    3 種 operator を確率的に選ぶ:

    1. **swap_persona**: 1 名を別 persona に差し替え.
    2. **add_persona** / **remove_persona**: 1 名追加 / 削除.
    3. **perturb_weights**: weights に Gaussian noise を加えて renormalize.

    Attributes
    ----------
    p_swap : float
        swap 確率.
    p_add_remove : float
        add or remove 確率 (combined).
    p_weight_perturb : float
        weights perturbation 確率.
    min_personas : int
        最小 persona 数.
    max_personas : int
        最大 persona 数.
    weight_sigma : float
        perturb_weights の Gaussian σ.
    """

    p_swap: float = 0.3
    p_add_remove: float = 0.2
    p_weight_perturb: float = 0.5
    min_personas: int = 1
    max_personas: int = 5
    weight_sigma: float = 0.1

    def __post_init__(self) -> None:
        for prob in (self.p_swap, self.p_add_remove, self.p_weight_perturb):
            if not (0.0 <= prob <= 1.0):
                raise ValueError(f"probabilities must be in [0, 1], got {prob}")
        if self.min_personas < 1:
            raise ValueError("min_personas must be >= 1")
        if self.max_personas < self.min_personas:
            raise ValueError("max_personas must be >= min_personas")
        if self.weight_sigma <= 0:
            raise ValueError("weight_sigma must be > 0")

    def __call__(
        self,
        comp: PersonaComposition,
        rng: np.random.Generator,
    ) -> PersonaComposition:
        ids = list(comp.persona_ids)
        weights = list(comp.weights)
        all_ids = list(PERSONA_ONTOLOGY.keys())

        # 1. swap
        if rng.random() < self.p_swap and ids:
            idx = int(rng.integers(0, len(ids)))
            unused = [pid for pid in all_ids if pid not in ids]
            if unused:
                ids[idx] = unused[int(rng.integers(0, len(unused)))]

        # 2. add / remove
        if rng.random() < self.p_add_remove:
            if len(ids) < self.max_personas:
                unused = [pid for pid in all_ids if pid not in ids]
                if unused:
                    ids.append(unused[int(rng.integers(0, len(unused)))])
                    weights.append(float(rng.uniform(0.1, 1.0)))
            elif len(ids) > self.min_personas:
                idx = int(rng.integers(0, len(ids)))
                ids.pop(idx)
                weights.pop(idx)

        # 3. perturb_weights
        if rng.random() < self.p_weight_perturb and weights:
            new_w = np.maximum(
                0.001,
                np.asarray(weights) + rng.normal(0.0, self.weight_sigma, size=len(weights)),
            )
            weights = list(new_w.tolist())

        result = PersonaComposition(
            persona_ids=tuple(ids),
            weights=tuple(weights),
            import_policy=comp.import_policy,
        ).normalize_weights()
        return result


# ---------------------------------------------------------------------------
# Persona dissimilarity (for diversity preservation)
# ---------------------------------------------------------------------------


def persona_dissimilarity(
    a: PersonaComposition, b: PersonaComposition
) -> float:
    """2 個 composition の差異 [0, 1].

    = (1 - Jaccard(id sets)) * 0.5 + L2(factor_affinity diff) * 0.5

    Jaccard: id 集合の被り少ないほど高い.
    L2: 加重 factor affinity の距離 (normalize to [0,1] roughly).
    """
    set_a = set(a.persona_ids)
    set_b = set(b.persona_ids)
    union = set_a | set_b
    if not union:
        return 0.0
    jaccard = len(set_a & set_b) / len(union)
    aff_a = a.effective_factor_affinity()
    aff_b = b.effective_factor_affinity()
    l2 = float(np.linalg.norm(aff_a - aff_b))
    # L2 max ≈ sqrt(10) = 3.16, normalize to [0,1]
    l2_norm = min(1.0, l2 / math.sqrt(len(THOUGHT_FACTORS)))
    return 0.5 * (1.0 - jaccard) + 0.5 * l2_norm


__all__ = [
    "PERSONA_ONTOLOGY",
    "Persona",
    "PersonaComposition",
    "PersonaCompositionMutation",
    "THOUGHT_FACTORS",
    "get_persona",
    "list_persona_ids",
    "persona_dissimilarity",
    "random_persona_composition",
]
