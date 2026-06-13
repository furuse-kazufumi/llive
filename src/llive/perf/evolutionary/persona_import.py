# SPDX-License-Identifier: Apache-2.0
"""E.12 PersonaImportAlgorithm (CE-20).

ユーザー指示 (2026-05-21):
    「派生 A の persona_ids を 派生 B が import (部分採用).
     『ガロア + 岡潔』のような hybrid persona が出現. 派生間で persona
     ライブラリを交換」

CE-19 (HistoricalPersonaOntology) と CE-21 (PersonaCompositionMutation) が
既存 ``persona.py`` で実装済み. 本 module は **派生間転送ロジック**:

- どの persona を採用するか/拒否するか per-persona 判定
- affinity 互換性 (target の effective_factor_affinity と source persona の
  factor_affinity の cosine 類似度)
- source peer_score floor で「信用ない派生からは import しない」
- blend strategy: ``extend`` / ``replace`` / ``blend_weights``
- COG-MESH-05 Quarantined Memory の zone share 通知 hook
  (``PersonaZoneShareEvent`` を返すだけ. 実 zone 操作は別 module)

決定論性:
- ``rng`` 注入 (numpy Generator). 同じ rng + 同じ input → 同じ plan.
- 提案 plan は frozen dataclass. apply で新 PersonaComposition を返す
  (副作用なし).

要件根拠: ``docs/requirements_v0.E_competitive_coevolution.md`` 0.7 節
+ CE-20 + Phase E.12.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from llive.perf.evolutionary.persona import (
    PERSONA_ONTOLOGY,
    PersonaComposition,
)

# ---------------------------------------------------------------------------
# PersonaImportPlan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PersonaImportPlan:
    """A から B への persona import 提案. 純データ.

    Attributes
    ----------
    source_id : str
        派生 A の識別子 (logging / share event 用).
    target_id : str
        派生 B の識別子.
    imported_persona_ids : tuple[str, ...]
        実際に B に import する persona id.
    rejected_persona_ids : tuple[str, ...]
        拒否された (互換性低 / 重複 / 上限) persona id.
    blend_strategy : str
        ``extend`` / ``replace`` / ``blend_weights``.
    initial_weight : float
        import された persona の初期 weight (renormalize 前).
    """

    source_id: str
    target_id: str
    imported_persona_ids: tuple[str, ...]
    rejected_persona_ids: tuple[str, ...]
    blend_strategy: str = "extend"
    initial_weight: float = 0.3

    def apply(
        self,
        target_comp: PersonaComposition,
        source_comp: PersonaComposition,
    ) -> PersonaComposition:
        """plan に従って target_comp を更新した新 PersonaComposition を返す.

        副作用なし. import_policy は target を維持.
        """
        if not self.imported_persona_ids:
            return target_comp

        if self.blend_strategy == "extend":
            return _apply_extend(target_comp, self)
        if self.blend_strategy == "replace":
            return _apply_replace(target_comp, source_comp, self)
        if self.blend_strategy == "blend_weights":
            return _apply_blend_weights(target_comp, source_comp, self)
        raise ValueError(f"unknown blend_strategy: {self.blend_strategy!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "imported_persona_ids": list(self.imported_persona_ids),
            "rejected_persona_ids": list(self.rejected_persona_ids),
            "blend_strategy": self.blend_strategy,
            "initial_weight": float(self.initial_weight),
        }


# ---------------------------------------------------------------------------
# PersonaZoneShareEvent — COG-MESH-05 Quarantined Memory hook
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PersonaZoneShareEvent:
    """派生間 persona share の通知データ.

    COG-MESH-05 Quarantined Memory zone への通知に使う envelope.
    本 module は event を返すだけで, zone への実書込みは別 module.

    Attributes
    ----------
    source_id : str
        派生 A の識別子.
    target_id : str
        派生 B の識別子.
    persona_ids : tuple[str, ...]
        共有された persona id.
    zone : str
        通知先 memory zone (``shared`` / ``mentor`` / ``quarantine``).
    note : str
        Free-form メモ.
    """

    source_id: str
    target_id: str
    persona_ids: tuple[str, ...]
    zone: str = "shared"
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "persona_ids": list(self.persona_ids),
            "zone": self.zone,
            "note": self.note,
        }


# ---------------------------------------------------------------------------
# PersonaImportAlgorithm — 派生間 persona 採択ロジック
# ---------------------------------------------------------------------------


@dataclass
class PersonaImportAlgorithm:
    """CE-20 — 派生 A から派生 B へ persona を per-id で部分採用するアルゴリズム.

    Attributes
    ----------
    max_imports_per_event : int
        1 plan で import できる persona 数の上限.
    min_source_peer_score : float
        source の peer_score がこれ未満なら何も import しない (信頼下限).
    affinity_threshold : float
        candidate persona の factor_affinity と target.effective_factor_affinity
        の cosine 類似度がこれ未満なら拒否. 0 で全許可, 1 で同方向のみ.
    blend_strategy : str
        ``extend`` (default, persona_ids を追加), ``replace`` (target 内
        既存 persona を入れ替え), ``blend_weights`` (target の persona
        weight を source 寄りに blend).
    initial_weight : float
        import された persona の初期 weight (renormalize 前). [0, 1].
    forbid_existing : bool
        既に target に存在する persona は import しない.
    zone : str
        PersonaZoneShareEvent.zone のデフォルト値.
    """

    max_imports_per_event: int = 2
    min_source_peer_score: float = 0.0
    affinity_threshold: float = 0.0
    blend_strategy: str = "extend"
    initial_weight: float = 0.3
    forbid_existing: bool = True
    zone: str = "shared"

    def __post_init__(self) -> None:
        if self.max_imports_per_event < 0:
            raise ValueError("max_imports_per_event must be >= 0")
        if not (-1.0 <= self.affinity_threshold <= 1.0):
            raise ValueError("affinity_threshold must be in [-1, 1]")
        if not (0.0 <= self.initial_weight <= 1.0):
            raise ValueError("initial_weight must be in [0, 1]")
        if self.blend_strategy not in ("extend", "replace", "blend_weights"):
            raise ValueError(f"unknown blend_strategy: {self.blend_strategy!r}")

    # -- planning ---------------------------------------------------------

    def plan(
        self,
        source_comp: PersonaComposition,
        target_comp: PersonaComposition,
        *,
        source_peer_score: float = 1.0,
        source_id: str = "A",
        target_id: str = "B",
        rng: np.random.Generator | None = None,
    ) -> PersonaImportPlan:
        """B が A の persona の何を採用するか決定し plan を返す."""
        rng = rng or np.random.default_rng()

        if source_peer_score < self.min_source_peer_score:
            return PersonaImportPlan(
                source_id=source_id,
                target_id=target_id,
                imported_persona_ids=(),
                rejected_persona_ids=tuple(source_comp.persona_ids),
                blend_strategy=self.blend_strategy,
                initial_weight=self.initial_weight,
            )

        target_ids = set(target_comp.persona_ids)
        target_aff = target_comp.effective_factor_affinity()

        accepted: list[str] = []
        rejected: list[str] = []
        for pid in source_comp.persona_ids:
            if self.forbid_existing and pid in target_ids:
                rejected.append(pid)
                continue
            if pid not in PERSONA_ONTOLOGY:
                rejected.append(pid)
                continue
            persona = PERSONA_ONTOLOGY[pid]
            cand_aff = np.asarray(persona.factor_affinity, dtype=np.float64)
            cos = _cosine(target_aff, cand_aff)
            if cos < self.affinity_threshold:
                rejected.append(pid)
                continue
            accepted.append(pid)

        # 上限 cap. rng で安定 shuffle してから top-N を採用.
        if len(accepted) > self.max_imports_per_event:
            order = rng.permutation(len(accepted))
            accepted = [accepted[i] for i in order[: self.max_imports_per_event]]
            # 採用されなかった候補は rejected に回す
            remained = [
                accepted_pid
                for accepted_pid in source_comp.persona_ids
                if accepted_pid not in accepted and accepted_pid not in rejected
            ]
            rejected.extend(remained)

        return PersonaImportPlan(
            source_id=source_id,
            target_id=target_id,
            imported_persona_ids=tuple(accepted),
            rejected_persona_ids=tuple(rejected),
            blend_strategy=self.blend_strategy,
            initial_weight=self.initial_weight,
        )

    # -- execution --------------------------------------------------------

    def execute(
        self,
        source_comp: PersonaComposition,
        target_comp: PersonaComposition,
        *,
        source_peer_score: float = 1.0,
        source_id: str = "A",
        target_id: str = "B",
        rng: np.random.Generator | None = None,
    ) -> tuple[PersonaComposition, PersonaImportPlan, PersonaZoneShareEvent | None]:
        """plan → apply → share event 生成 をワンショットで実行する.

        Returns
        -------
        tuple
            (new_target_comp, plan, zone_share_event).
            zone_share_event は import が 1 つ以上発生したときだけ非 None.
        """
        plan = self.plan(
            source_comp,
            target_comp,
            source_peer_score=source_peer_score,
            source_id=source_id,
            target_id=target_id,
            rng=rng,
        )
        new_target = plan.apply(target_comp, source_comp)
        event: PersonaZoneShareEvent | None = None
        if plan.imported_persona_ids:
            event = PersonaZoneShareEvent(
                source_id=source_id,
                target_id=target_id,
                persona_ids=plan.imported_persona_ids,
                zone=self.zone,
                note=f"strategy={self.blend_strategy}",
            )
        return new_target, plan, event


# ---------------------------------------------------------------------------
# Blend strategy implementations
# ---------------------------------------------------------------------------


def _apply_extend(
    target: PersonaComposition, plan: PersonaImportPlan
) -> PersonaComposition:
    """既存 persona_ids に new ones を append, weights renormalize."""
    new_ids = list(target.persona_ids) + list(plan.imported_persona_ids)
    new_weights = list(target.weights) + [
        plan.initial_weight for _ in plan.imported_persona_ids
    ]
    return PersonaComposition(
        persona_ids=tuple(new_ids),
        weights=tuple(new_weights),
        import_policy=target.import_policy,
    ).normalize_weights()


def _apply_replace(
    target: PersonaComposition,
    source: PersonaComposition,
    plan: PersonaImportPlan,
) -> PersonaComposition:
    """target の末尾を import 数分削って new ones を入れ替える.

    target の persona 数が import 数より少ない場合は extend 的に振る舞う.
    """
    n_import = len(plan.imported_persona_ids)
    keep_n = max(0, len(target.persona_ids) - n_import)
    kept_ids = target.persona_ids[:keep_n]
    kept_weights = target.weights[:keep_n]
    new_ids = list(kept_ids) + list(plan.imported_persona_ids)
    new_weights = list(kept_weights) + [
        plan.initial_weight for _ in plan.imported_persona_ids
    ]
    # 衝突 (forbid_existing=False のときに発生し得る) は重複 id を最後出現で
    # 上書きする. PersonaComposition は重複禁止.
    deduped_ids: list[str] = []
    deduped_weights: list[float] = []
    seen: set[str] = set()
    # 逆順で見て一意 → 元順序に戻す
    for pid, w in reversed(list(zip(new_ids, new_weights, strict=True))):
        if pid in seen:
            continue
        seen.add(pid)
        deduped_ids.append(pid)
        deduped_weights.append(w)
    deduped_ids.reverse()
    deduped_weights.reverse()
    return PersonaComposition(
        persona_ids=tuple(deduped_ids),
        weights=tuple(deduped_weights),
        import_policy=target.import_policy,
    ).normalize_weights()


def _apply_blend_weights(
    target: PersonaComposition,
    source: PersonaComposition,
    plan: PersonaImportPlan,
) -> PersonaComposition:
    """target の persona に source の同名 weight を 0.5/0.5 blend し,
    import_only な persona は append (extend と同じ).

    "mentor が部分的に持ち込む" 中間 strategy.
    """
    src_map = dict(zip(source.persona_ids, source.weights, strict=True))
    new_ids: list[str] = list(target.persona_ids)
    new_weights: list[float] = []
    for pid, w_t in zip(target.persona_ids, target.weights, strict=True):
        w_s = src_map.get(pid)
        if w_s is None:
            new_weights.append(float(w_t))
        else:
            new_weights.append(float((w_t + w_s) / 2.0))
    # import される new persona を append
    for pid in plan.imported_persona_ids:
        if pid not in new_ids:
            new_ids.append(pid)
            new_weights.append(plan.initial_weight)
    return PersonaComposition(
        persona_ids=tuple(new_ids),
        weights=tuple(new_weights),
        import_policy=target.import_policy,
    ).normalize_weights()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


__all__ = [
    "PersonaImportAlgorithm",
    "PersonaImportPlan",
    "PersonaZoneShareEvent",
]
