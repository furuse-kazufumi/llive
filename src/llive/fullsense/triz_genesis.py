"""TRIZ Trigger Genesis (A-2) — Spec §3.3 T-Z1..4 自発 trigger 検出器.

ResidentRunner の StimulusSource として登録すると、agent が観測する
metric 流から TRIZ 矛盾 (T-Z1..4) を検出し、自発 Stimulus を内発的に
注入する。これにより外部プロンプトなしで「TRIZ 起源の思考サイクル」が
回り始める (= §22 SING の A°1 endogenous goal generation の最小実装)。

検出する 4 種の矛盾:

* **T-Z1 administrative contradiction** — 目標進捗 metric が伸びない
  (停滞 / 後退の観測)
* **T-Z2 technical contradiction** — X 改善 ⇒ Y 悪化 のペア
  (既存 ``ContradictionDetector`` を流用)
* **T-Z3 physical contradiction** — 同一 feature に opposite preference が
  共存 (例: memory.size は capacity の為に large、latency の為に small)
* **T-Z4 resource contradiction** — resource は available だが access 不能
  (available_rate と access_rate の比に乖離)

検出された Stimulus には ``source="triz-genesis"`` と ``epistemic_type``
が乗り、§F3 TRIZ Reasoning Engine が後段で principle mapping を行える
ようテキスト中に metric 情報を埋め込む。
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass

from llive.fullsense.types import EpistemicType, Stimulus
from llive.triz.contradiction import (
    Contradiction,
    ContradictionDetector,
    MetricSpec,
)


@dataclass
class TZ1GoalProgressConfig:
    """T-Z1 administrative contradiction の検出設定."""

    metric_name: str = "goal.progress"
    """進捗 metric の名前 (0..1 想定、1.0 = 完遂)."""

    window: int = 20
    """直近 N 件の sample で進捗を評価."""

    stagnation_epsilon: float = 0.01
    """progress の延び率がこれ未満なら停滞と判定."""

    cooldown_s: float = 2.0
    """同じ T-Z1 を連続で発火させない最短間隔."""


@dataclass
class TZ3OppositePref:
    """T-Z3 physical contradiction: 同一 metric への opposite preference 1 件."""

    metric_name: str
    """対象 metric (e.g. "memory.size")."""

    pref_a: str
    """方向 A の好み (例: "large for capacity")."""

    pref_b: str
    """方向 B の好み (例: "small for latency")."""


@dataclass
class TZ4ResourceConfig:
    """T-Z4 resource contradiction の検出設定."""

    available_metric: str
    """resource が「ある」割合の metric."""

    access_metric: str
    """resource に「access できた」割合の metric."""

    gap_threshold: float = 0.3
    """available - access >= gap_threshold で発火."""


# ---------------------------------------------------------------------------
# TRIZ Genesis source
# ---------------------------------------------------------------------------


class TrizGenesisSource:
    """StimulusSource: ``poll()`` で T-Z1..4 を Stimulus 化して返す.

    使い方::

        genesis = TrizGenesisSource()
        genesis.observe("pipeline.latency_ms", 120)
        genesis.observe("pipeline.throughput", 800)
        ...
        s = genesis.poll()  # Stimulus or None

    検出器は内部に 1 件キューを持つので、複数矛盾が見つかった場合は
    severity 上位順に 1 件ずつ ``poll()`` で取り出される。
    """

    def __init__(
        self,
        *,
        detector: ContradictionDetector | None = None,
        goal_progress: TZ1GoalProgressConfig | None = None,
        opposite_prefs: Iterable[TZ3OppositePref] = (),
        resource_pairs: Iterable[TZ4ResourceConfig] = (),
        epistemic_type: EpistemicType | None = EpistemicType.NORMATIVE,
    ) -> None:
        self._detector = detector if detector is not None else ContradictionDetector()
        self._goal_cfg = goal_progress or TZ1GoalProgressConfig()
        self._opposite_prefs = list(opposite_prefs)
        self._resource_pairs = list(resource_pairs)
        self._epistemic_type = epistemic_type

        self._goal_buffer: deque[float] = deque(maxlen=self._goal_cfg.window)
        self._last_tz1_at: float = 0.0
        self._latest_metrics: dict[str, float] = {}
        self._tz3_emit_index: int = 0
        self._tz4_emit_index: int = 0
        self._tz2_queue: deque[Contradiction] = deque()

    # -- ingestion ---------------------------------------------------------

    def register_metric(self, spec: MetricSpec) -> None:
        """ContradictionDetector の registry に metric spec を追加."""
        self._detector.register(spec)

    def observe(self, metric: str, value: float) -> None:
        self._latest_metrics[metric] = float(value)
        # T-Z1: goal progress buffer
        if metric == self._goal_cfg.metric_name:
            self._goal_buffer.append(float(value))
        # T-Z2: detector へ流す
        self._detector.observe(metric, float(value))

    def observe_many(self, sample: dict[str, float]) -> None:
        for k, v in sample.items():
            self.observe(k, v)

    # -- detection ---------------------------------------------------------

    def detect_t_z1(self) -> Stimulus | None:
        """T-Z1: goal progress が停滞 / 後退している."""
        buf = self._goal_buffer
        if len(buf) < max(4, self._goal_cfg.window // 2):
            return None
        now = time.time()
        if now - self._last_tz1_at < self._goal_cfg.cooldown_s:
            return None
        first = list(buf)[: len(buf) // 2]
        second = list(buf)[len(buf) // 2 :]
        rate = (sum(second) / len(second)) - (sum(first) / len(first))
        if rate >= self._goal_cfg.stagnation_epsilon:
            return None  # 十分伸びている
        self._last_tz1_at = now
        return Stimulus(
            content=(
                f"TRIZ T-Z1 administrative: goal progress is stagnant "
                f"(rate={rate:+.4f}, metric={self._goal_cfg.metric_name}). "
                "Re-examine subgoals or relax constraints."
            ),
            source="triz-genesis:t-z1",
            surprise=min(1.0, abs(rate) + 0.5),
            epistemic_type=self._epistemic_type,
        )

    def detect_t_z2(self) -> Stimulus | None:
        """T-Z2: technical contradiction (improve X → degrade Y)."""
        if not self._tz2_queue:
            self._tz2_queue.extend(self._detector.detect())
        if not self._tz2_queue:
            return None
        c = self._tz2_queue.popleft()
        return Stimulus(
            content=(
                f"TRIZ T-Z2 technical: improving {c.improve_metric} "
                f"degrades {c.degrade_metric} "
                f"(features {c.improve_feature_id} vs {c.degrade_feature_id}, "
                f"severity={c.severity:.2f}). "
                "Apply 40-principle matrix lookup before falling through."
            ),
            source=f"triz-genesis:t-z2:{c.contradiction_id}",
            surprise=float(c.severity),
            epistemic_type=self._epistemic_type,
        )

    def detect_t_z3(self) -> Stimulus | None:
        """T-Z3: physical contradiction — 同一 feature が両方向に求められる."""
        if not self._opposite_prefs:
            return None
        # round-robin で 1 件返す
        pref = self._opposite_prefs[
            self._tz3_emit_index % len(self._opposite_prefs)
        ]
        self._tz3_emit_index += 1
        # 対象 metric を観測したことがある時のみ発火
        if pref.metric_name not in self._latest_metrics:
            return None
        return Stimulus(
            content=(
                f"TRIZ T-Z3 physical: {pref.metric_name} must be "
                f"{pref.pref_a} AND {pref.pref_b}. "
                "Apply principle of separation (time / space / scale / condition)."
            ),
            source=f"triz-genesis:t-z3:{pref.metric_name}",
            surprise=0.7,
            epistemic_type=self._epistemic_type,
        )

    def detect_t_z4(self) -> Stimulus | None:
        """T-Z4: resource contradiction — available だが access 不能."""
        if not self._resource_pairs:
            return None
        pair = self._resource_pairs[
            self._tz4_emit_index % len(self._resource_pairs)
        ]
        self._tz4_emit_index += 1
        avail = self._latest_metrics.get(pair.available_metric)
        access = self._latest_metrics.get(pair.access_metric)
        if avail is None or access is None:
            return None
        gap = avail - access
        if gap < pair.gap_threshold:
            return None
        return Stimulus(
            content=(
                f"TRIZ T-Z4 resource: {pair.available_metric}={avail:.2f} but "
                f"{pair.access_metric}={access:.2f} (gap={gap:.2f}). "
                "Investigate access path / permission / bottleneck."
            ),
            source=f"triz-genesis:t-z4:{pair.available_metric}",
            surprise=min(1.0, gap + 0.4),
            epistemic_type=self._epistemic_type,
        )

    # -- StimulusSource interface -----------------------------------------

    def poll(self) -> Stimulus | None:
        """T-Z1..4 を順に試し、最初に検出できたものを返す.

        順序は severity 期待値が高い順: T-Z2 (実測 detector) > T-Z4 (gap) >
        T-Z3 (定性 preference) > T-Z1 (停滞)。
        """
        for fn in (
            self.detect_t_z2,
            self.detect_t_z4,
            self.detect_t_z3,
            self.detect_t_z1,
        ):
            s = fn()
            if s is not None:
                return s
        return None


__all__ = [
    "TZ1GoalProgressConfig",
    "TZ3OppositePref",
    "TZ4ResourceConfig",
    "TrizGenesisSource",
]
