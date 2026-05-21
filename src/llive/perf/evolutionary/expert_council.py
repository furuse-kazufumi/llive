# SPDX-License-Identifier: Apache-2.0
"""Expert Panel + Council Protocol — Society of Mind × MoE (v0.E CE-14/15).

ユーザー指示 (2026-05-21):
    「専門家が数人議論しあって一つの結論を出す構造を各 llive 亜種が実施する
    として, どの専門家を軸にすれば生存率が高いかを模索」

設計:

- ``Expert`` dataclass: 1 専門家 = (name, specialization_vector, bias_score).
  specialization_vector は llive 10 思考因子 (THOUGHT_FACTORS) と同次元の
  affinity vector. bias_score は自己主張の強さ.
- ``ExpertPanel`` dataclass: N 人 expert + protocol を持つ.
- ``deliberate(panel, topic_vector)``: protocol に従い議論を simulate し
  CouncilDecision を返す.

Protocol 種別:

- ``round_robin``: 各 expert が順番に発言. 最終発言が結論.
- ``moderator_vote``: moderator が質問を出し, expert は yes/no で投票.
  多数決で結論.
- ``veto``: 全員の confidence が threshold 以上で初めて proceed. 1 人でも
  veto なら no-decision.
- ``weighted_average``: confidence で重み付けして average response vector.

Mock 版 (credential 不要): LLM 推論なし. specialization_vector との内積を
"発言 confidence" として扱う. 実 LLM 議論は Phase E.8 後の credential 復旧後.

参照: Minsky (1986) Society of Mind, Shazeer et al. (2017) Mixture of Experts,
Li et al. (2023) CAMEL, Wu et al. (2023) AutoGen.

要件根拠: ``docs/requirements_v0.E_competitive_coevolution.md`` CE-14/15/16.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from llive.perf.evolutionary.persona import THOUGHT_FACTORS


Protocol = Literal["round_robin", "moderator_vote", "veto", "weighted_average"]


@dataclass(frozen=True)
class Expert:
    """1 人の専門家.

    Attributes
    ----------
    name : str
        Display 名. 任意.
    specialization_vector : tuple[float, ...]
        ``THOUGHT_FACTORS`` 10 軸上の affinity [0, 1]. 大きいほど得意.
    bias_score : float
        自己主張の強さ. high = 多く発言したがる. ∈ [0, 1].
    """

    name: str
    specialization_vector: tuple[float, ...]
    bias_score: float = 0.5

    def __post_init__(self) -> None:
        if len(self.specialization_vector) != len(THOUGHT_FACTORS):
            raise ValueError(
                f"specialization_vector length must be {len(THOUGHT_FACTORS)}"
            )
        for v in self.specialization_vector:
            if not (0.0 <= float(v) <= 1.0):
                raise ValueError(f"specialization values must be in [0, 1], got {v}")
        if not (0.0 <= float(self.bias_score) <= 1.0):
            raise ValueError(f"bias_score must be in [0, 1], got {self.bias_score}")

    def confidence_for_topic(self, topic_vector: np.ndarray) -> float:
        """topic に対する自信度. cosine-like similarity を normalize."""
        s = np.asarray(self.specialization_vector, dtype=np.float64)
        t = np.asarray(topic_vector, dtype=np.float64)
        sn = float(np.linalg.norm(s))
        tn = float(np.linalg.norm(t))
        if sn == 0 or tn == 0:
            return 0.0
        cosine = float(np.dot(s, t) / (sn * tn))
        # cosine ∈ [-1, 1] → [0, 1]
        return max(0.0, min(1.0, (cosine + 1.0) / 2.0)) * (0.5 + 0.5 * self.bias_score)


@dataclass(frozen=True)
class CouncilDecision:
    """1 回の議論結果.

    Attributes
    ----------
    decided : bool
        True なら proceed, False なら no-decision (veto 等で失敗).
    consensus_vector : np.ndarray
        集約された 10 軸 response vector.
    contributions : dict[str, float]
        各 expert の貢献度 (confidence).
    transcript : tuple[tuple[str, float], ...]
        発言ログ (name, confidence). Round-robin で順序を保持.
    """

    decided: bool
    consensus_vector: np.ndarray
    contributions: dict[str, float]
    transcript: tuple[tuple[str, float], ...]


@dataclass
class ExpertPanel:
    """N 人 expert + 議論 protocol.

    Attributes
    ----------
    experts : tuple[Expert, ...]
        専門家リスト.
    protocol : Protocol
        議論方式.
    veto_threshold : float
        veto protocol で必要な最小 confidence.
    moderator_index : int
        moderator_vote protocol で議長役の expert index.
    """

    experts: tuple[Expert, ...]
    protocol: Protocol = "weighted_average"
    veto_threshold: float = 0.3
    moderator_index: int = 0

    def __post_init__(self) -> None:
        if not self.experts:
            raise ValueError("experts must be non-empty")
        if self.protocol not in (
            "round_robin", "moderator_vote", "veto", "weighted_average"
        ):
            raise ValueError(f"unknown protocol: {self.protocol!r}")
        if not (0.0 <= self.veto_threshold <= 1.0):
            raise ValueError("veto_threshold must be in [0, 1]")
        if not (0 <= self.moderator_index < len(self.experts)):
            raise ValueError(
                f"moderator_index {self.moderator_index} out of range "
                f"[0, {len(self.experts)})"
            )

    # ---------- public API ----------------------------------------------

    @property
    def size(self) -> int:
        return len(self.experts)

    def deliberate(
        self,
        topic_vector: np.ndarray,
        rng: np.random.Generator | None = None,
    ) -> CouncilDecision:
        """議題 topic_vector について議論し結論を返す.

        Parameters
        ----------
        topic_vector : np.ndarray
            shape (n_factors,) の topic 表現. 各 expert はこれに対する
            confidence を計算する.
        rng : np.random.Generator | None
            random 要素 (round_robin の noise) で使用. None なら 0 で固定.
        """
        topic = np.asarray(topic_vector, dtype=np.float64)
        if topic.shape != (len(THOUGHT_FACTORS),):
            raise ValueError(
                f"topic_vector shape must be ({len(THOUGHT_FACTORS)},), got {topic.shape}"
            )
        if rng is None:
            rng = np.random.default_rng(0)

        confs = np.array(
            [e.confidence_for_topic(topic) for e in self.experts]
        )
        transcript: list[tuple[str, float]] = []
        contributions: dict[str, float] = {}

        if self.protocol == "weighted_average":
            return self._weighted_average(topic, confs)
        if self.protocol == "round_robin":
            return self._round_robin(topic, confs, rng)
        if self.protocol == "moderator_vote":
            return self._moderator_vote(topic, confs)
        if self.protocol == "veto":
            return self._veto(topic, confs)
        # unreachable
        raise RuntimeError(f"unhandled protocol: {self.protocol!r}")

    # ---------- protocol implementations --------------------------------

    def _weighted_average(
        self, topic: np.ndarray, confs: np.ndarray
    ) -> CouncilDecision:
        """confidence で重み付けして expert vector を平均."""
        if confs.sum() <= 1e-12:
            consensus = topic.copy()  # no signal: fall back to topic
        else:
            weights = confs / confs.sum()
            vectors = np.stack([
                np.asarray(e.specialization_vector, dtype=np.float64)
                for e in self.experts
            ])
            consensus = (weights[:, None] * vectors).sum(axis=0)
        transcript = tuple((e.name, float(c)) for e, c in zip(self.experts, confs))
        contributions = {e.name: float(c) for e, c in zip(self.experts, confs)}
        return CouncilDecision(
            decided=True,
            consensus_vector=consensus,
            contributions=contributions,
            transcript=transcript,
        )

    def _round_robin(
        self,
        topic: np.ndarray,
        confs: np.ndarray,
        rng: np.random.Generator,
    ) -> CouncilDecision:
        """順番に発言. 各 step で前者の意見を一部受けて更新.

        final = last_expert の specialization with cumulative drift.
        """
        cumulative = topic.copy()
        transcript: list[tuple[str, float]] = []
        contributions: dict[str, float] = {}
        for i, (e, conf) in enumerate(zip(self.experts, confs)):
            s = np.asarray(e.specialization_vector, dtype=np.float64)
            # 各 expert が cumulative を自身寄りに引っ張る
            cumulative = (1.0 - conf) * cumulative + conf * s
            transcript.append((e.name, float(conf)))
            contributions[e.name] = float(conf)
        return CouncilDecision(
            decided=True,
            consensus_vector=cumulative,
            contributions=contributions,
            transcript=tuple(transcript),
        )

    def _moderator_vote(
        self, topic: np.ndarray, confs: np.ndarray
    ) -> CouncilDecision:
        """moderator が yes/no 質問を出し, 各 expert が confidence>=0.5 で yes.

        多数決で yes が過半数なら decided=True, consensus は yes 派の重み付け平均.
        """
        votes = confs >= 0.5
        n_yes = int(votes.sum())
        decided = n_yes > len(self.experts) // 2

        if decided:
            yes_indices = np.where(votes)[0]
            yes_weights = confs[yes_indices] / max(1e-12, confs[yes_indices].sum())
            vectors = np.stack([
                np.asarray(self.experts[i].specialization_vector, dtype=np.float64)
                for i in yes_indices
            ])
            consensus = (yes_weights[:, None] * vectors).sum(axis=0)
        else:
            consensus = topic.copy()

        transcript = tuple(
            (f"{e.name}({'YES' if v else 'NO'})", float(c))
            for e, c, v in zip(self.experts, confs, votes)
        )
        contributions = {
            e.name: float(c) if v else 0.0
            for e, c, v in zip(self.experts, confs, votes)
        }
        return CouncilDecision(
            decided=decided,
            consensus_vector=consensus,
            contributions=contributions,
            transcript=transcript,
        )

    def _veto(
        self, topic: np.ndarray, confs: np.ndarray
    ) -> CouncilDecision:
        """全員の confidence が veto_threshold 以上で初めて decided=True."""
        decided = bool(np.all(confs >= self.veto_threshold))
        if decided:
            weights = confs / max(1e-12, confs.sum())
            vectors = np.stack([
                np.asarray(e.specialization_vector, dtype=np.float64)
                for e in self.experts
            ])
            consensus = (weights[:, None] * vectors).sum(axis=0)
        else:
            consensus = topic.copy()
        transcript = tuple((e.name, float(c)) for e, c in zip(self.experts, confs))
        contributions = {e.name: float(c) for e, c in zip(self.experts, confs)}
        return CouncilDecision(
            decided=decided,
            consensus_vector=consensus,
            contributions=contributions,
            transcript=transcript,
        )


# ---------------------------------------------------------------------------
# helper: build panel from PERSONA_ONTOLOGY
# ---------------------------------------------------------------------------


def build_panel_from_personas(
    persona_ids: tuple[str, ...],
    *,
    protocol: Protocol = "weighted_average",
    bias_score: float = 0.5,
    moderator_index: int = 0,
    veto_threshold: float = 0.3,
) -> ExpertPanel:
    """PERSONA_ONTOLOGY の persona から ExpertPanel を組み立てる.

    persona の factor_affinity をそのまま specialization_vector として使う.
    歴史人物 panel が即座に作れる.
    """
    from llive.perf.evolutionary.persona import get_persona

    experts = tuple(
        Expert(
            name=p.name,
            specialization_vector=p.factor_affinity,
            bias_score=bias_score,
        )
        for p in (get_persona(pid) for pid in persona_ids)
    )
    return ExpertPanel(
        experts=experts,
        protocol=protocol,
        veto_threshold=veto_threshold,
        moderator_index=moderator_index,
    )


__all__ = [
    "CouncilDecision",
    "Expert",
    "ExpertPanel",
    "Protocol",
    "build_panel_from_personas",
]
