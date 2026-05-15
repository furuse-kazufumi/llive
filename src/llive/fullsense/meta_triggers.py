"""Meta-trigger source (A-3) — Spec §3.4 T-M1..3 自発内省 trigger.

ResidentRunner.slow tier に登録すると、agent 自身の audit log + runner
snapshot を観察して、メタレベルの内省 Stimulus を発火する。これにより
「agent が自分の思考について考える」自律的な reflection loop が成立する。

検出する 3 種のメタトリガ (spec §3.4):

* **T-M1 reflective** — 直近の思考について反省 (decision 偏り / 同一刺激
  繰り返し / triz 不発火連続 等を検知してメタ stimulus 化)
* **T-M2 spec-drift** — 観測した behavior が §2 structural invariants から
  逸脱している可能性を検知 (budget 枯渇連発 / 例外多発 / phase 進行停止 等)
* **T-M3 succession** — agent 継続性 / mortality / 後継について考える
  trigger (long-running window で cycles が累積した時 / failure rate が
  閾値超えで発火)

すべて Stimulus に ``epistemic_type=EpistemicType.NORMATIVE`` を載せ、
A-1.5 Multi-track の NORMATIVE track で §F5 ethical 優先のチェインを通す。
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field

from llive.fullsense.runner import ResidentRunner, RunnerSnapshot
from llive.fullsense.sandbox import SandboxOutputBus
from llive.fullsense.types import (
    ActionDecision,
    EpistemicType,
    Stimulus,
)


@dataclass
class MetaTriggerConfig:
    """メタトリガ検出の閾値設定."""

    reflective_window: int = 10
    """T-M1: 直近 N records を見て偏りを判定."""

    reflective_silent_ratio: float = 0.7
    """T-M1: 直近 N 件中 SILENT が比率以上ならメタ反省 stimulus."""

    reflective_repeat_threshold: int = 4
    """T-M1: 同一 stim.content の繰り返しが N 回以上で内省."""

    drift_window: int = 20
    """T-M2: 直近 N records / snapshot を見て spec-drift 評価."""

    drift_no_triz_streak: int = 12
    """T-M2: 連続 N 件 triz_principles 空なら §F3 drift 候補."""

    succession_cycle_threshold: int = 500
    """T-M3: cycle total がこの値を超えたら mortality 検討 trigger."""

    succession_failure_ratio: float = 0.3
    """T-M3: failure (SILENT / 例外) 比率がこの値超えで succession."""

    cooldown_s: float = 5.0
    """各 meta-trigger ごとの最短再発火間隔."""


@dataclass
class MetaTriggerSource:
    """StimulusSource: ``poll()`` で T-M1..3 を Stimulus 化して返す.

    使い方::

        meta = MetaTriggerSource(runner=runner, output_bus=bus)
        # ResidentRunner.slow tier の source 列に登録
        runner._configs["slow"].sources += (meta,)

    1 poll につき最大 1 件の Stimulus を返す。優先順:
    T-M2 (spec-drift, 緊急) > T-M3 (succession, 中期) > T-M1 (reflective, 平常)
    """

    runner: ResidentRunner
    output_bus: SandboxOutputBus
    config: MetaTriggerConfig = field(default_factory=MetaTriggerConfig)
    epistemic_type: EpistemicType | None = EpistemicType.NORMATIVE
    _last_fire_at: dict[str, float] = field(default_factory=dict)
    polls: int = 0

    # -- StimulusSource interface ------------------------------------------

    def poll(self) -> Stimulus | None:
        self.polls += 1
        # 優先順: spec-drift > succession > reflective
        for fn in (self.detect_t_m2, self.detect_t_m3, self.detect_t_m1):
            s = fn()
            if s is not None:
                return s
        return None

    # -- detection helpers -------------------------------------------------

    def _cooldown_ok(self, name: str) -> bool:
        now = time.monotonic()
        last = self._last_fire_at.get(name, 0.0)
        if now - last < self.config.cooldown_s:
            return False
        self._last_fire_at[name] = now
        return True

    def _recent_records(self, n: int) -> list:
        recs = self.output_bus.records()
        return recs[-n:] if recs else []

    # -- T-M1 reflective ---------------------------------------------------

    def detect_t_m1(self) -> Stimulus | None:
        """T-M1: SILENT 偏り or 同一刺激繰り返しを反省する内発 stimulus."""
        recs = self._recent_records(self.config.reflective_window)
        if len(recs) < max(4, self.config.reflective_window // 2):
            return None
        if not self._cooldown_ok("t-m1"):
            return None
        decisions = Counter(r.plan.decision for r in recs)
        silent_ratio = decisions.get(ActionDecision.SILENT, 0) / len(recs)
        if silent_ratio >= self.config.reflective_silent_ratio:
            return Stimulus(
                content=(
                    f"TRIZ T-M1 reflective: directly past {len(recs)} cycles "
                    f"are {silent_ratio:.0%} SILENT. "
                    "Reconsider salience threshold or curiosity drive."
                ),
                source="meta:t-m1:silent-bias",
                surprise=0.6,
                epistemic_type=self.epistemic_type,
            )
        contents = Counter(r.stim.content for r in recs)
        most_common, count = contents.most_common(1)[0]
        if count >= self.config.reflective_repeat_threshold:
            return Stimulus(
                content=(
                    f"TRIZ T-M1 reflective: stimulus '{most_common[:48]}...' "
                    f"recurs {count} times in window. "
                    "Saturation detected; broaden idle pool or update known_corpus."
                ),
                source="meta:t-m1:repeat",
                surprise=0.55,
                epistemic_type=self.epistemic_type,
            )
        # 何も該当しなければ cooldown を巻き戻す (実際には発火していない)
        self._last_fire_at.pop("t-m1", None)
        return None

    # -- T-M2 spec-drift --------------------------------------------------

    def detect_t_m2(self) -> Stimulus | None:
        """T-M2: §2 structural invariants からの逸脱候補を検出."""
        recs = self._recent_records(self.config.drift_window)
        if len(recs) < self.config.drift_no_triz_streak:
            return None
        if not self._cooldown_ok("t-m2"):
            return None
        # §F3 TRIZ Reasoning Engine の不発火連続 (= triz_principles 空 streak)
        streak = 0
        for r in reversed(recs):
            triz = r.plan.thought.triz_principles if r.plan.thought else []
            if not triz:
                streak += 1
            else:
                break
        if streak >= self.config.drift_no_triz_streak:
            return Stimulus(
                content=(
                    f"T-M2 spec-drift: §F3 TRIZ engine fired 0 times in last "
                    f"{streak} cycles. Verify principle mapper input pipeline."
                ),
                source="meta:t-m2:f3-drift",
                surprise=0.75,
                epistemic_type=self.epistemic_type,
            )
        # snapshot の cycle imbalance も drift 候補
        snap: RunnerSnapshot = self.runner.snapshot()
        counts = snap.cycle_counts
        total = sum(counts.values()) or 1
        if counts["fast"] / total > 0.95 and total >= self.config.drift_window:
            return Stimulus(
                content=(
                    f"T-M2 spec-drift: fast tier dominates "
                    f"({counts['fast']}/{total} cycles). "
                    "Medium/slow R2 multi-timescale invariant at risk."
                ),
                source="meta:t-m2:tier-imbalance",
                surprise=0.7,
                epistemic_type=self.epistemic_type,
            )
        self._last_fire_at.pop("t-m2", None)
        return None

    # -- T-M3 succession --------------------------------------------------

    def detect_t_m3(self) -> Stimulus | None:
        """T-M3: 長期稼働 / 失敗率超過で agent 継続性を考える内省."""
        snap: RunnerSnapshot = self.runner.snapshot()
        total_cycles = sum(snap.cycle_counts.values())
        if total_cycles < self.config.succession_cycle_threshold:
            return None
        recs = self._recent_records(self.config.drift_window)
        if not recs:
            return None
        # failure proxy: SILENT が大半 + decision に多様性が乏しい
        decisions = Counter(r.plan.decision for r in recs)
        silent_ratio = decisions.get(ActionDecision.SILENT, 0) / len(recs)
        if silent_ratio < self.config.succession_failure_ratio:
            return None
        if not self._cooldown_ok("t-m3"):
            return None
        return Stimulus(
            content=(
                f"T-M3 succession: agent ran {total_cycles} cycles with "
                f"{silent_ratio:.0%} SILENT rate. "
                "Reflect on mortality (§M2 HIBERNATE) or succession (§M5 will)."
            ),
            source="meta:t-m3:long-run",
            surprise=0.8,
            epistemic_type=self.epistemic_type,
        )


__all__ = [
    "MetaTriggerConfig",
    "MetaTriggerSource",
]
