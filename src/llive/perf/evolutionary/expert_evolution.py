# SPDX-License-Identifier: Apache-2.0
"""ExpertPanel composition の進化 + 生存率 tracking (v0.E CE-16/17).

ユーザー洞察 (2026-05-21):
    「どの専門家を軸にすれば生存率が高いかを模索するような行動を取らせる
    必要がある」

設計:

- ``ExpertCompositionGenome``: tuple[persona_id, ...] + protocol を genome 化.
- ``ExpertCompositionMutation``: persona の swap / add / remove + protocol
  change.
- ``SurvivalRateTracker``: 各 composition signature の出現 / 生存世代 / mean
  score を集計. signature = sorted persona_ids + protocol.

参照: CE-14/15 (ExpertPanel) と協調.

要件根拠: ``docs/requirements_v0.E_competitive_coevolution.md`` CE-16/17.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

import numpy as np

from llive.perf.evolutionary.expert_council import (
    ExpertPanel,
    Protocol,
    build_panel_from_personas,
)
from llive.perf.evolutionary.persona import PERSONA_ONTOLOGY

_PROTOCOLS: tuple[Protocol, ...] = (
    "weighted_average",
    "round_robin",
    "moderator_vote",
    "veto",
)


@dataclass(frozen=True)
class ExpertCompositionGenome:
    """ExpertPanel composition を genome 化したもの.

    Attributes
    ----------
    persona_ids : tuple[str, ...]
        採用 persona id. unique, 順序保持 (Round-robin で意味).
    protocol : Protocol
        議論プロトコル.
    moderator_index : int
        moderator_vote protocol で議長 index.
    """

    persona_ids: tuple[str, ...]
    protocol: Protocol = "weighted_average"
    moderator_index: int = 0

    def __post_init__(self) -> None:
        if not self.persona_ids:
            raise ValueError("persona_ids must be non-empty")
        if len(set(self.persona_ids)) != len(self.persona_ids):
            raise ValueError("persona_ids must be unique")
        for pid in self.persona_ids:
            if pid not in PERSONA_ONTOLOGY:
                raise ValueError(f"unknown persona_id: {pid!r}")
        if self.protocol not in _PROTOCOLS:
            raise ValueError(f"unknown protocol: {self.protocol!r}")
        if not (0 <= self.moderator_index < len(self.persona_ids)):
            raise ValueError(
                f"moderator_index {self.moderator_index} out of range "
                f"[0, {len(self.persona_ids)})"
            )

    def signature(self) -> str:
        """同一 composition 判定用 signature.

        sorted persona_ids + protocol. moderator_index は signature に含めない
        (議論結果の差異が小さい設計判断).
        """
        sorted_pids = sorted(self.persona_ids)
        return f"{'+'.join(sorted_pids)}|{self.protocol}"

    def to_panel(self, *, bias_score: float = 0.5, veto_threshold: float = 0.3) -> ExpertPanel:
        """対応する ExpertPanel を構築."""
        return build_panel_from_personas(
            self.persona_ids,
            protocol=self.protocol,
            bias_score=bias_score,
            moderator_index=self.moderator_index,
            veto_threshold=veto_threshold,
        )


@dataclass(frozen=True)
class ExpertCompositionMutation:
    """ExpertCompositionGenome の mutation.

    operator:
      - swap_persona
      - add_persona
      - remove_persona
      - change_protocol
      - shift_moderator

    Attributes
    ----------
    p_swap : float
    p_add : float
    p_remove : float
    p_change_protocol : float
    p_shift_moderator : float
    min_personas : int
    max_personas : int
    """

    p_swap: float = 0.3
    p_add: float = 0.15
    p_remove: float = 0.15
    p_change_protocol: float = 0.1
    p_shift_moderator: float = 0.05
    min_personas: int = 2
    max_personas: int = 5

    def __post_init__(self) -> None:
        for prob in (
            self.p_swap, self.p_add, self.p_remove,
            self.p_change_protocol, self.p_shift_moderator,
        ):
            if not (0.0 <= prob <= 1.0):
                raise ValueError(f"probabilities must be in [0, 1], got {prob}")
        if self.min_personas < 1:
            raise ValueError("min_personas must be >= 1")
        if self.max_personas < self.min_personas:
            raise ValueError("max_personas must be >= min_personas")

    def __call__(
        self,
        genome: ExpertCompositionGenome,
        rng: np.random.Generator,
    ) -> ExpertCompositionGenome:
        ids = list(genome.persona_ids)
        protocol = genome.protocol
        moderator_index = genome.moderator_index
        all_ids = list(PERSONA_ONTOLOGY.keys())

        if rng.random() < self.p_swap and ids:
            unused = [pid for pid in all_ids if pid not in ids]
            if unused:
                idx = int(rng.integers(0, len(ids)))
                ids[idx] = unused[int(rng.integers(0, len(unused)))]

        if rng.random() < self.p_add and len(ids) < self.max_personas:
            unused = [pid for pid in all_ids if pid not in ids]
            if unused:
                ids.append(unused[int(rng.integers(0, len(unused)))])

        if rng.random() < self.p_remove and len(ids) > self.min_personas:
            idx = int(rng.integers(0, len(ids)))
            ids.pop(idx)
            if moderator_index >= len(ids):
                moderator_index = max(0, len(ids) - 1)

        if rng.random() < self.p_change_protocol:
            protocol = _PROTOCOLS[int(rng.integers(0, len(_PROTOCOLS)))]

        if rng.random() < self.p_shift_moderator and ids:
            moderator_index = int(rng.integers(0, len(ids)))

        return ExpertCompositionGenome(
            persona_ids=tuple(ids),
            protocol=protocol,
            moderator_index=min(moderator_index, len(ids) - 1),
        )


@dataclass
class CompositionStat:
    """1 つの composition signature の生存統計."""

    signature: str
    first_seen_generation: int
    last_seen_generation: int
    appearances: int = 0
    survived_generations: int = 0  # 連続して残った世代数 (max streak)
    current_streak: int = 0
    total_score: float = 0.0
    score_samples: int = 0

    def mean_score(self) -> float:
        if self.score_samples == 0:
            return 0.0
        return self.total_score / self.score_samples


@dataclass
class SurvivalRateTracker:
    """各 composition signature の生存統計を集計.

    Usage:
    ```
    tracker = SurvivalRateTracker()
    for gen in range(N):
        signatures = [g.signature() for g in compositions_at_gen]
        tracker.observe(gen, signatures, scores=...)
    print(tracker.top_signatures(k=5))
    ```

    Attributes
    ----------
    stats : dict[str, CompositionStat]
    """

    stats: dict[str, CompositionStat] = field(default_factory=dict)

    def observe(
        self,
        generation: int,
        signatures: Iterable[str],
        scores: Iterable[float] | None = None,
    ) -> None:
        """1 世代の出現 + score を記録.

        scores は signatures と同順. None なら score 集計はスキップ.
        """
        sigs = list(signatures)
        score_list: list[float | None]
        if scores is None:
            score_list = [None] * len(sigs)
        else:
            score_list = list(scores)
            if len(score_list) != len(sigs):
                raise ValueError("scores length must match signatures length")

        # 各 signature が今世代何回出現したか
        sig_counts: dict[str, int] = defaultdict(int)
        sig_score_sums: dict[str, float] = defaultdict(float)
        sig_score_samples: dict[str, int] = defaultdict(int)
        for sig, sc in zip(sigs, score_list, strict=True):
            sig_counts[sig] += 1
            if sc is not None:
                sig_score_sums[sig] += float(sc)
                sig_score_samples[sig] += 1

        # 既存 stat を全て一旦 streak 切れチェック
        seen_this_gen = set(sig_counts.keys())
        for sig, stat in list(self.stats.items()):
            if sig in seen_this_gen:
                # 連続出現
                stat.current_streak += 1
                stat.survived_generations = max(
                    stat.survived_generations, stat.current_streak
                )
                stat.last_seen_generation = generation
                stat.appearances += sig_counts[sig]
                stat.total_score += sig_score_sums[sig]
                stat.score_samples += sig_score_samples[sig]
            else:
                stat.current_streak = 0

        # 新規 signature
        for sig in seen_this_gen:
            if sig not in self.stats:
                self.stats[sig] = CompositionStat(
                    signature=sig,
                    first_seen_generation=generation,
                    last_seen_generation=generation,
                    appearances=sig_counts[sig],
                    survived_generations=1,
                    current_streak=1,
                    total_score=sig_score_sums[sig],
                    score_samples=sig_score_samples[sig],
                )

    def top_signatures(
        self,
        *,
        k: int = 5,
        by: str = "survived_generations",
    ) -> list[CompositionStat]:
        """上位 k 件を返す. by: survived_generations / appearances / mean_score."""
        if by == "survived_generations":
            def key_fn(s):
                return s.survived_generations
        elif by == "appearances":
            def key_fn(s):
                return s.appearances
        elif by == "mean_score":
            def key_fn(s):
                return s.mean_score()
        else:
            raise ValueError(f"unknown sort key: {by!r}")
        return sorted(self.stats.values(), key=key_fn, reverse=True)[:k]

    def to_dict(self) -> dict[str, dict[str, float | int | str]]:
        return {
            sig: {
                "signature": stat.signature,
                "first_seen_generation": stat.first_seen_generation,
                "last_seen_generation": stat.last_seen_generation,
                "appearances": stat.appearances,
                "survived_generations": stat.survived_generations,
                "current_streak": stat.current_streak,
                "total_score": stat.total_score,
                "score_samples": stat.score_samples,
                "mean_score": stat.mean_score(),
            }
            for sig, stat in self.stats.items()
        }


__all__ = [
    "CompositionStat",
    "ExpertCompositionGenome",
    "ExpertCompositionMutation",
    "SurvivalRateTracker",
]
