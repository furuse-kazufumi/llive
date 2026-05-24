# SPDX-License-Identifier: Apache-2.0
"""Antifragile Mutation controller (EVO-ANTIFRAGILE).

Nassim Taleb の *Antifragile* (反脆弱性) を進化計算へ持ち込む **opt-in** 機構。

通常の llive は高 surprise / エラーを検知すると **fail-closed** (守りに入る) が
default。この controller は逆の選択肢を一時的に与える: 高 surprise を「学習機会」
と捉え、**panic mode** へ遷移して

1. 普段 filter している **対立変異 pair** (相反する TRIZ 原理の同時適用) を unlock し、
2. UCB1 の exploration constant を一時的に **10x** に増幅し、
3. panic 中の ChangeOp を **すべて audit chain に署名つき** (SHA-256 hash chain) で残す。

局所最適 (集団が揃った stack 状態) から自己破壊的にジャンプする狙い。
[[project_idea_antifragile_mutation]] / [[project_idea_predictive_verification]] 参照。

設計判断 (重要):

* **fail-closed default は崩さない** — ``AntifragileConfig.enabled=False`` が既定。
  明示的 opt-in か環境変数 ``LLIVE_ANTIFRAGILE_AUTO=true`` でのみ有効化される。
* **Approval Bus を迂回しない** — controller は探索パラメータの増幅と監査記録のみを
  担う。panic 中の重大変更も通常どおり approval が必要 (本機構は approval を緩めない)。
* **honest disclosure** — panic episode ごとに ops 数 / 成功 / 損失を追跡し、
  ``disclosure()`` で時系列集計を返す。「自己破壊で次の安定へ」が本当に効くかは
  **未検証**であり、効果は定量化して初めて主張できる (本機構はその計測基盤)。

本 controller は既存の進化 driver へ **強制配線しない**。surprise の供給元
(:class:`~llive.memory.bayesian_surprise.BayesianSurpriseGate`)、監査記録
(:class:`~llive.security.audit.AuditTrail`)、UCB hyperparameter
(:mod:`llive.perf.evolutionary.fitness_ucb`) を疎結合で参照し、loop 側が opt-in で
consult する形を取る。

使用例 (Integration)::

    from llive.evolution.antifragile import AntifragileController, AntifragileConfig
    from llive.memory.bayesian_surprise import BayesianSurpriseGate
    from llive.security.audit import AuditTrail

    ctrl = AntifragileController(
        AntifragileConfig.from_env(),          # LLIVE_ANTIFRAGILE_AUTO で有効化
        gate=BayesianSurpriseGate(k=1.0),
        audit_trail=AuditTrail(),
    )

    # 進化ループの 1 ステップごとに:
    if ctrl.observe_surprise(surprise):        # panic に入ったか
        c = ctrl.exploration_constant(base_c)  # UCB1 c を 10x (panic 時)
        for pair in ctrl.unlocked_conflict_pairs():
            ...                                # 相反原理の同時適用を許可
    ctrl.record_change_op(op, outcome="success")   # panic 中は audit chain へ
    ctrl.tick()                                # cooldown 経過で自動復帰
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:  # pragma: no cover - type hints only
    from llive.memory.bayesian_surprise import BayesianSurpriseGate

# 監査記録は ``append(actor, action, payload) -> entry`` を満たす duck-typed object を
# 受け取る (本番は llive.security.audit.AuditTrail)。テスト用の in-memory fake も可。
AuditLike = Any
ClockFn = Callable[[], float]

# 真偽値とみなす環境変数の値 (大文字小文字無視)。
_TRUE_TOKENS = frozenset({"1", "true", "yes", "on"})

#: opt-in を制御する環境変数名。
AUTO_ENV_VAR = "LLIVE_ANTIFRAGILE_AUTO"


class PanicState(Enum):
    """controller の状態。"""

    NORMAL = "normal"
    """通常運転。探索パラメータは素通し、対立 pair は filter されたまま。"""

    PANIC = "panic"
    """高 surprise を検知した学習モード。探索増幅 + 対立 pair unlock + 全 op 監査。"""


@dataclass(frozen=True)
class ConflictPair:
    """通常は filter で抑えている「相反する TRIZ 原理」の組。

    panic mode 中だけ同時適用を許可する (例: #1 分割 と #40 複合材料 を同 ChangeOp で
    発火)。原理 id のみ必須で、名称・根拠は説明用。
    """

    principle_a: int
    principle_b: int
    name_a: str = ""
    name_b: str = ""
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "principle_a": self.principle_a,
            "principle_b": self.principle_b,
            "name_a": self.name_a,
            "name_b": self.name_b,
            "rationale": self.rationale,
        }


#: 既定の対立 pair。[[project_idea_antifragile_mutation]] の例を正本とする。
DEFAULT_CONFLICT_PAIRS: tuple[ConflictPair, ...] = (
    ConflictPair(
        1, 40, "Segmentation", "Composite materials",
        "分割と複合材料を同時適用: 部品化しつつ素材融合 (矛盾を構造に持ち込む)",
    ),
    ConflictPair(
        14, 2, "Spheroidality", "Taking out",
        "球面化と取り出しを逆方向で: 一体化と分離を同時に試す",
    ),
    ConflictPair(
        1, 5, "Segmentation", "Merging",
        "分割と併合の教科書的対立: 局所最適から両極へ同時ジャンプ",
    ),
)


@dataclass
class AntifragileEpisode:
    """1 回の panic episode の記録 (honest disclosure 用)。"""

    index: int
    trigger_surprise: float
    trigger_threshold: float
    started_at: float
    ended_at: float | None = None
    exit_reason: str | None = None
    n_ops: int = 0
    n_success: int = 0
    n_loss: int = 0

    @property
    def is_active(self) -> bool:
        return self.ended_at is None

    @property
    def duration_s(self) -> float | None:
        if self.ended_at is None:
            return None
        return self.ended_at - self.started_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "trigger_surprise": self.trigger_surprise,
            "trigger_threshold": self.trigger_threshold,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "exit_reason": self.exit_reason,
            "duration_s": self.duration_s,
            "n_ops": self.n_ops,
            "n_success": self.n_success,
            "n_loss": self.n_loss,
        }


@dataclass(frozen=True)
class AntifragileConfig:
    """controller の設定。``enabled=False`` の fail-closed が既定。

    Parameters
    ----------
    enabled:
        panic mode を許可するか。**既定 False** (fail-closed)。opt-in 専用。
    cold_threshold:
        surprise gate を渡さない場合に使う固定閾値。``[0, 1]`` を想定。
    cooldown_s:
        panic に入ってからの最長滞在時間 (秒)。経過したら強制復帰 (risk の上限)。
        既定 300s = 5 分。
    exploration_multiplier:
        panic 中に UCB1 exploration constant へ掛ける倍率。既定 10x。``>= 1.0``。
    recovery_ratio:
        surprise が ``threshold * recovery_ratio`` を下回ったら panic を解除する
        hysteresis 係数。``(0, 1]``。既定 0.8 (閾値の 80% まで下がれば復帰)。
    conflict_pairs:
        panic 中に unlock する対立 pair。
    ucb_clip:
        増幅後の exploration constant を clamp する上限 (UCB genome bound 等)。
        ``None`` なら clamp しない。
    audit_all_ops:
        ``True`` なら panic 外の ChangeOp も監査記録する。既定 False
        (panic 中のみ記録 = idea の規約どおり)。
    actor:
        audit chain に記録する actor 名。
    """

    enabled: bool = False
    cold_threshold: float = 0.8
    cooldown_s: float = 300.0
    exploration_multiplier: float = 10.0
    recovery_ratio: float = 0.8
    conflict_pairs: tuple[ConflictPair, ...] = DEFAULT_CONFLICT_PAIRS
    ucb_clip: float | None = None
    audit_all_ops: bool = False
    actor: str = "antifragile"

    def __post_init__(self) -> None:
        if self.exploration_multiplier < 1.0:
            raise ValueError("exploration_multiplier must be >= 1.0")
        if not (0.0 < self.recovery_ratio <= 1.0):
            raise ValueError("recovery_ratio must be in (0, 1]")
        if self.cooldown_s <= 0.0:
            raise ValueError("cooldown_s must be > 0")
        if self.ucb_clip is not None and self.ucb_clip <= 0.0:
            raise ValueError("ucb_clip must be > 0 when set")

    @classmethod
    def from_env(
        cls, env: dict[str, str] | None = None, **overrides: Any
    ) -> AntifragileConfig:
        """環境変数から ``enabled`` を解決して構築。``overrides`` が最優先。

        ``LLIVE_ANTIFRAGILE_AUTO`` が真値 (1/true/yes/on) のとき ``enabled=True``。
        明示的に ``enabled=`` を渡せば環境変数より優先される。
        """
        source = env if env is not None else os.environ
        raw = str(source.get(AUTO_ENV_VAR, "")).strip().lower()
        enabled = raw in _TRUE_TOKENS
        params: dict[str, Any] = {"enabled": enabled}
        params.update(overrides)
        return cls(**params)


class AntifragileController:
    """surprise 駆動の panic state machine。

    fail-closed default を保ちながら、opt-in 時のみ panic mode で探索を増幅する。
    既存進化 driver には配線せず、loop 側が各メソッドを consult する疎結合設計。
    """

    def __init__(
        self,
        config: AntifragileConfig | None = None,
        *,
        gate: BayesianSurpriseGate | None = None,
        audit_trail: AuditLike | None = None,
        clock: ClockFn | None = None,
    ) -> None:
        self.config = config or AntifragileConfig()
        self.gate = gate
        self.audit = audit_trail
        # 単調増加時計を注入可能に (テストの決定性確保)。
        if clock is not None:
            self._clock = clock
        else:
            import time

            self._clock = time.monotonic
        self.state: PanicState = PanicState.NORMAL
        self._panic_started_at: float | None = None
        self._current_episode: AntifragileEpisode | None = None
        self.episodes: list[AntifragileEpisode] = []
        # honest disclosure: 無効化されていなければ panic していたであろう回数。
        self._suppressed_triggers: int = 0

    # -- state queries -----------------------------------------------------

    @property
    def is_panic(self) -> bool:
        return self.state is PanicState.PANIC

    @property
    def current_episode(self) -> AntifragileEpisode | None:
        return self._current_episode

    def threshold(self) -> float:
        """現在の発火閾値。gate があれば動的閾値、無ければ ``cold_threshold``。"""
        if self.gate is not None:
            return float(self.gate.threshold)
        return self.config.cold_threshold

    # -- surprise ingestion ------------------------------------------------

    def observe_surprise(self, surprise: float, *, update_gate: bool = True) -> bool:
        """surprise を 1 件供給し、panic 状態を更新して ``is_panic`` を返す。

        gate を渡している場合、閾値は **更新前の統計**で評価してから gate を更新する
        (:meth:`BayesianSurpriseGate.should_write` と同じ順序)。
        """
        surprise = float(surprise)
        theta = self.threshold()
        exceeded = surprise >= theta

        if self.config.enabled:
            if self.state is PanicState.NORMAL:
                if exceeded:
                    self._enter_panic(surprise, theta)
            else:  # PANIC: 復帰条件を評価
                self._maybe_recover(surprise, theta)
        elif exceeded:
            # fail-closed: 無効時は決して panic しない。発火し得た回数だけ記録。
            self._suppressed_triggers += 1

        if self.gate is not None and update_gate:
            self.gate.update(surprise)

        return self.is_panic

    def tick(self) -> bool:
        """surprise 供給なしの時間経過チェック。cooldown 経過で自動復帰。

        loop が surprise を毎ステップ供給しない場合でも、定期的に呼べば
        panic の最長滞在 (``cooldown_s``) を保証できる。
        """
        if self.state is PanicState.PANIC:
            self._maybe_recover(surprise=None, theta=None)
        return self.is_panic

    def stop(self, reason: str = "user_stop") -> bool:
        """Approval Bus / user による panic 停止指示。即座に NORMAL へ。

        Returns
        -------
        bool
            実際に panic を停止したら True (既に NORMAL なら False)。
        """
        if self.state is PanicState.PANIC:
            self._exit_panic(reason)
            return True
        return False

    # -- panic-mode parameters ---------------------------------------------

    def exploration_constant(self, base: float) -> float:
        """UCB1 exploration constant。panic 中のみ ``exploration_multiplier`` 倍。

        ``ucb_clip`` が設定されていれば増幅後に上限 clamp する。
        """
        base = float(base)
        if not self.is_panic:
            return base
        amplified = base * self.config.exploration_multiplier
        if self.config.ucb_clip is not None:
            amplified = min(amplified, self.config.ucb_clip)
        return amplified

    @property
    def mutation_rate_multiplier(self) -> float:
        """panic 中の変異率倍率 (探索寄せ)。NORMAL では 1.0。"""
        return self.config.exploration_multiplier if self.is_panic else 1.0

    def unlocked_conflict_pairs(self) -> tuple[ConflictPair, ...]:
        """panic 中に同時適用を許可する対立 pair。NORMAL では空。"""
        return self.config.conflict_pairs if self.is_panic else ()

    # -- change-op auditing ------------------------------------------------

    def record_change_op(
        self,
        op: Any,
        *,
        outcome: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Any | None:
        """ChangeOp を audit chain に署名つきで記録 (panic 中は必須記録)。

        Parameters
        ----------
        op:
            記録対象。:class:`ChangeOp` でも文字列でも可 (説明文字列化される)。
        outcome:
            ``"success"`` / ``"loss"`` / ``None``。panic episode の集計に使う。
        payload:
            追加メタデータ (audit payload に merge)。

        Returns
        -------
        記録した audit entry (audit_trail 未設定なら ``None``)。

        Notes
        -----
        panic 外の op は既定では記録しない (``audit_all_ops=True`` で記録)。
        episode カウンタは panic 中の op のみ加算する。
        """
        in_panic = self.is_panic
        entry = None
        if in_panic or self.config.audit_all_ops:
            entry_payload: dict[str, Any] = {
                "op": _describe_op(op),
                "panic": in_panic,
                "outcome": outcome,
            }
            if in_panic and self._current_episode is not None:
                entry_payload["episode"] = self._current_episode.index
            if payload:
                entry_payload.update(payload)
            entry = self._audit("change_op", entry_payload)

        if in_panic and self._current_episode is not None:
            ep = self._current_episode
            ep.n_ops += 1
            if outcome == "success":
                ep.n_success += 1
            elif outcome == "loss":
                ep.n_loss += 1
        return entry

    # -- honest disclosure -------------------------------------------------

    def disclosure(self) -> dict[str, Any]:
        """panic の成功率 / 損失率 / 滞在時間を時系列集計して返す。

        「自己破壊で次の安定へ」が本当に効くかは未検証。本 dict はその効果を
        定量化するための素データであり、勝った気になる前に内訳を疑うこと
        ([[feedback_benchmark_honest_disclosure]])。
        """
        total_ops = sum(ep.n_ops for ep in self.episodes)
        total_success = sum(ep.n_success for ep in self.episodes)
        total_loss = sum(ep.n_loss for ep in self.episodes)
        decided = total_success + total_loss
        durations = [
            ep.duration_s for ep in self.episodes if ep.duration_s is not None
        ]
        mean_duration = sum(durations) / len(durations) if durations else None
        return {
            "enabled": self.config.enabled,
            "state": self.state.value,
            "episodes": len(self.episodes),
            "active_episode": self._current_episode is not None,
            "suppressed_triggers": self._suppressed_triggers,
            "panic_ops_total": total_ops,
            "panic_ops_success": total_success,
            "panic_ops_loss": total_loss,
            "success_rate": (total_success / decided) if decided else None,
            "loss_rate": (total_loss / decided) if decided else None,
            "mean_panic_duration_s": mean_duration,
            "exploration_multiplier": self.config.exploration_multiplier,
            "honest_note": (
                "panic mode の効果 (自己破壊で次の安定へ) は未検証。"
                "success_rate/loss_rate を時系列で追い、内訳を疑ってから主張すること。"
            ),
        }

    # -- internals ---------------------------------------------------------

    def _enter_panic(self, surprise: float, theta: float) -> None:
        now = self._clock()
        episode = AntifragileEpisode(
            index=len(self.episodes),
            trigger_surprise=surprise,
            trigger_threshold=theta,
            started_at=now,
        )
        self.episodes.append(episode)
        self._current_episode = episode
        self._panic_started_at = now
        self.state = PanicState.PANIC
        self._audit(
            "panic_enter",
            {
                "episode": episode.index,
                "surprise": surprise,
                "threshold": theta,
                "exploration_multiplier": self.config.exploration_multiplier,
                "unlocked_pairs": [p.to_dict() for p in self.config.conflict_pairs],
            },
        )

    def _maybe_recover(self, surprise: float | None, theta: float | None) -> None:
        """panic からの復帰条件を評価。cooldown 経過 or surprise 回復で NORMAL へ。"""
        assert self._panic_started_at is not None
        now = self._clock()
        if now - self._panic_started_at >= self.config.cooldown_s:
            self._exit_panic("cooldown_elapsed")
            return
        if surprise is not None and theta is not None:
            if surprise < theta * self.config.recovery_ratio:
                self._exit_panic("surprise_recovered")

    def _exit_panic(self, reason: str) -> None:
        now = self._clock()
        episode = self._current_episode
        if episode is not None:
            episode.ended_at = now
            episode.exit_reason = reason
            self._audit(
                "panic_exit",
                {
                    "episode": episode.index,
                    "reason": reason,
                    "duration_s": episode.duration_s,
                    "n_ops": episode.n_ops,
                    "n_success": episode.n_success,
                    "n_loss": episode.n_loss,
                },
            )
        self.state = PanicState.NORMAL
        self._panic_started_at = None
        self._current_episode = None

    def _audit(self, action: str, payload: dict[str, Any]) -> Any | None:
        if self.audit is None:
            return None
        return self.audit.append(actor=self.config.actor, action=action, payload=payload)


def _describe_op(op: Any) -> str:
    """ChangeOp / 文字列 / 任意 object を監査用の短い説明文字列へ。"""
    if isinstance(op, str):
        return op
    target = getattr(op, "target_container", None)
    if target is not None:
        return f"{type(op).__name__}(target={target})"
    return repr(op)


__all__ = [
    "AUTO_ENV_VAR",
    "DEFAULT_CONFLICT_PAIRS",
    "AntifragileConfig",
    "AntifragileController",
    "AntifragileEpisode",
    "ConflictPair",
    "PanicState",
]
