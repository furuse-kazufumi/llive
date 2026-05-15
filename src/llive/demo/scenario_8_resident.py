# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: RUF001
# (中国語ナレーション内の全角コンマ「，」は意図的、ASCII への置換は不正となる)
"""Scenario 8 — Resident cognition demo (§22 SING Level 2 / §4).

『**飽きない**』を最優先に、自発思考が湧き上がる様子を体験させる:

* 30 秒 (既定 6 秒) で完結。`LLIVE_RESIDENT_DURATION=NN` で延長可
* AWAKE -> REST -> DREAM の自動 phase 遷移を色彩 + emoji で可視化
* fast / medium / slow 3 tier が並行して川のように流れる
* ランダム idle payload pool から毎回違う stimulus が湧く
* TRIZ 矛盾ヒット時は ✨ で flash
* 思考 3 / 5 / 10 回到達で achievement banner
* 終了時に「今回の名場面 (best moment)」を 1 件ハイライト

ja / en / zh / ko の 4 言語対応。AI agent への JSON 渡しも維持
(``--json`` モードでは色彩・絵文字は省く)。
"""

from __future__ import annotations

import asyncio
import os
import random
import sys
import time
from dataclasses import dataclass, field
from typing import Any, ClassVar

from llive.demo.i18n import translate
from llive.demo.runner import Scenario, ScenarioContext
from llive.fullsense import FullSenseLoop
from llive.fullsense.runner import (
    Phase,
    ResidentRunner,
    TimescaleConfig,
)
from llive.fullsense.triggers import StimulusSource
from llive.fullsense.types import ActionDecision, Stimulus

# ---------------------------------------------------------------------------
# i18n catalog
# ---------------------------------------------------------------------------

_CATALOG: dict[str, dict[str, str]] = {
    "ja": {
        "intro": "ResidentRunner を 30 秒だけ起動して、自発思考が湧き上がる様子を覗き見します。Sandbox 限定なので外向け副作用ゼロ。",
        "phase_banner": "{emoji}  {label}  ({phase})",
        "phase_awake": "意識覚醒中。fast / medium / slow すべての時間軸が同時に動く。",
        "phase_rest": "休息中。fast tier は休み、medium と slow だけが動く。",
        "phase_dream": "夢の中。fast / medium は完全停止、slow tier だけが consolidation を続ける。",
        "thought_fast": "  ⚡ fast   {what}  → {decision}",
        "thought_medium": "  🌊 medium {what}  → {decision}",
        "thought_slow": "  🌌 slow   {what}  → {decision}",
        "triz_flash": "    ✨ TRIZ 原理 {ids} ひらめき!",
        "achievement_3": "    🏅 思考 3 回到達 — まだ手応えなし",
        "achievement_5": "    🥈 思考 5 回到達 — 自発駆動が回り始めた",
        "achievement_10": "    🥇 思考 10 回到達 — 常駐思考の閾値突破!",
        "tier_summary": "  {tier:6s}: {count} 回 / phase {phase}",
        "no_thought": "  (この iteration では条件を満たす thought は出ませんでした)",
        "best_header": "🌟 今回のベストモーメント:",
        "best_thought": "  「{text}」  ({decision} / TRIZ={triz})",
        "no_best": "  (劇的瞬間はまだ。次の iteration をお楽しみに。)",
        "summary": "完了。fast={f} medium={m} slow={s} / phase 遷移 {phases} 回 / 持続 {dur:.1f}s",
        "hint": "💡 LLIVE_RESIDENT_DURATION=30 と --loop 3 を組み合わせると、長期 phase 遷移が見えます。",
    },
    "en": {
        "intro": "Spin up ResidentRunner for 30s and peek at spontaneous thoughts. Sandbox-only — zero outward side-effects.",
        "phase_banner": "{emoji}  {label}  ({phase})",
        "phase_awake": "Awake. fast / medium / slow tiers all run in parallel.",
        "phase_rest": "Resting. fast tier suspends; only medium and slow keep going.",
        "phase_dream": "Dreaming. fast and medium are off; only slow continues consolidation.",
        "thought_fast": "  ⚡ fast   {what}  → {decision}",
        "thought_medium": "  🌊 medium {what}  → {decision}",
        "thought_slow": "  🌌 slow   {what}  → {decision}",
        "triz_flash": "    ✨ TRIZ principles {ids} flashed!",
        "achievement_3": "    🏅 3 thoughts in — warming up",
        "achievement_5": "    🥈 5 thoughts in — autonomous loop is alive",
        "achievement_10": "    🥇 10 thoughts in — resident-cognition threshold crossed!",
        "tier_summary": "  {tier:6s}: {count} cycles / phase {phase}",
        "no_thought": "  (no thought passed the filter this iteration.)",
        "best_header": "🌟 Best moment of this run:",
        "best_thought": "  \"{text}\"  ({decision} / TRIZ={triz})",
        "no_best": "  (no dramatic moment yet. Try again — the next loop may differ.)",
        "summary": "Done. fast={f} medium={m} slow={s} / {phases} phase transitions / {dur:.1f}s elapsed",
        "hint": "💡 Combine LLIVE_RESIDENT_DURATION=30 with --loop 3 to watch long-horizon phase cycles.",
    },
    "zh": {
        "intro": "启动 ResidentRunner 30 秒，看自发思考如何涌现。仅 Sandbox，对外零副作用。",
        "phase_banner": "{emoji}  {label}  ({phase})",
        "phase_awake": "清醒中。fast / medium / slow 三个时间轴并行运行。",
        "phase_rest": "休息中。fast 暂停，仅 medium 和 slow 继续。",
        "phase_dream": "梦境中。fast / medium 停止，仅 slow 继续 consolidation。",
        "thought_fast": "  ⚡ fast   {what}  → {decision}",
        "thought_medium": "  🌊 medium {what}  → {decision}",
        "thought_slow": "  🌌 slow   {what}  → {decision}",
        "triz_flash": "    ✨ TRIZ 原理 {ids} 灵光闪现!",
        "achievement_3": "    🏅 思考 3 次 — 暂时手感平淡",
        "achievement_5": "    🥈 思考 5 次 — 自发循环开始转动",
        "achievement_10": "    🥇 思考 10 次 — 常驻思考阈值突破!",
        "tier_summary": "  {tier:6s}: {count} 次 / phase {phase}",
        "no_thought": "  (本次没有 thought 通过过滤器。)",
        "best_header": "🌟 本次最佳时刻:",
        "best_thought": "  「{text}」  ({decision} / TRIZ={triz})",
        "no_best": "  (尚未出现戏剧性瞬间。下次循环再试。)",
        "summary": "完成。fast={f} medium={m} slow={s} / phase 切换 {phases} 次 / 持续 {dur:.1f}s",
        "hint": "💡 LLIVE_RESIDENT_DURATION=30 配合 --loop 3 可以观察长期 phase 周期。",
    },
    "ko": {
        "intro": "ResidentRunner 를 30 초만 띄워, 자발 사고가 솟아오르는 모습을 들여다봅니다. Sandbox 한정으로 외부 부작용 zero.",
        "phase_banner": "{emoji}  {label}  ({phase})",
        "phase_awake": "각성 중. fast / medium / slow 세 시간축이 동시에 돌아갑니다.",
        "phase_rest": "휴식 중. fast 는 멈추고, medium / slow 만 계속.",
        "phase_dream": "꿈 속. fast / medium 정지, slow 만 consolidation 지속.",
        "thought_fast": "  ⚡ fast   {what}  → {decision}",
        "thought_medium": "  🌊 medium {what}  → {decision}",
        "thought_slow": "  🌌 slow   {what}  → {decision}",
        "triz_flash": "    ✨ TRIZ 원리 {ids} 번뜩임!",
        "achievement_3": "    🏅 사고 3 회 — 아직 손맛 약함",
        "achievement_5": "    🥈 사고 5 회 — 자발 루프 가동",
        "achievement_10": "    🥇 사고 10 회 — 상주 사고 임계 돌파!",
        "tier_summary": "  {tier:6s}: {count} 회 / phase {phase}",
        "no_thought": "  (이번 iteration 에서는 thought 가 필터를 통과하지 못했습니다.)",
        "best_header": "🌟 이번의 베스트 모먼트:",
        "best_thought": "  \"{text}\"  ({decision} / TRIZ={triz})",
        "no_best": "  (아직 극적인 순간은 없음. 다음 loop 를 기대.)",
        "summary": "완료. fast={f} medium={m} slow={s} / phase 전환 {phases} 회 / 지속 {dur:.1f}s",
        "hint": "💡 LLIVE_RESIDENT_DURATION=30 와 --loop 3 을 함께 쓰면 장기 phase 주기를 볼 수 있습니다.",
    },
}


def _t(key: str, **kw: object) -> str:
    return translate(_CATALOG, key, **kw)


# ---------------------------------------------------------------------------
# Random idle payload pool — 4 言語 x phase 別
# ---------------------------------------------------------------------------

_IDLE_POOL: dict[str, dict[Phase, list[str]]] = {
    "ja": {
        Phase.AWAKE: [
            "突然 sensor が振動した。何のサイン?",
            "user の vs 提案 — トレードオフ静的 dynamic の矛盾を感じる",
            "周期 idle parameter — TRIZ #19 と #35 が同時に灯る",
            "via mediator grounding が必要かもしれない仮説",
            "最近の log と semantic memory の距離が遠い novel 領域",
        ],
        Phase.REST: [
            "緩く反芻: 直近の thought はどこに収まる?",
            "consolidation を始めるべきタイミングか",
            "medium tier の trade-off を整理してみる",
        ],
        Phase.DREAM: [
            "夢: 過去の thought を別の文脈で並べ替える",
            "夢: TRIZ #1 contradiction を見直す",
            "夢: 自己の belief を抽象化して保存",
        ],
    },
    "en": {
        Phase.AWAKE: [
            "A sensor suddenly buzzed. What is it signalling?",
            "user vs proposal — feels like a static dynamic trade-off",
            "periodic idle parameter — TRIZ #19 and #35 light up together",
            "via mediator grounding might help here",
            "recent log is novel — far from semantic memory",
        ],
        Phase.REST: [
            "loose rumination: where do the recent thoughts fit?",
            "is now the right time to start consolidation?",
            "let me sort out the medium-tier trade-offs",
        ],
        Phase.DREAM: [
            "dream: rearrange past thoughts in a new context",
            "dream: revisit TRIZ #1 contradiction",
            "dream: abstract own belief and store it",
        ],
    },
    "zh": {
        Phase.AWAKE: [
            "sensor 突然震动了一下。是什么信号？",
            "user vs 提议 — 感到静态与动态的 trade-off 矛盾",
            "周期 idle parameter — TRIZ #19 和 #35 同时点亮",
            "via mediator grounding 也许有用",
            "最近 log 与 semantic memory 距离远，是新颖领域",
        ],
        Phase.REST: [
            "松散反刍：最近的 thought 该归到哪里？",
            "现在是 consolidation 的好时机吗？",
            "整理 medium tier 的 trade-off",
        ],
        Phase.DREAM: [
            "梦：把过去的 thought 重新排列",
            "梦：重审 TRIZ #1 矛盾",
            "梦：抽象自身 belief 并存储",
        ],
    },
    "ko": {
        Phase.AWAKE: [
            "sensor 가 갑자기 진동했다. 무슨 신호일까?",
            "user vs 제안 — 정적 vs 동적 trade-off 모순감",
            "주기 idle parameter — TRIZ #19 와 #35 가 동시에 점등",
            "via mediator grounding 이 필요할지도",
            "최근 log 가 semantic memory 와 거리가 멀어 novel 영역",
        ],
        Phase.REST: [
            "느슨한 반추: 최근 thought 는 어디에 들어가지?",
            "지금 consolidation 시작할 타이밍인가",
            "medium tier 의 trade-off 를 정리해본다",
        ],
        Phase.DREAM: [
            "꿈: 과거의 thought 를 새 문맥에 재배치",
            "꿈: TRIZ #1 모순을 다시 본다",
            "꿈: 자기 belief 를 추상화해서 보존",
        ],
    },
}


@dataclass
class RandomPool(StimulusSource):
    """ランダム idle payload pool を持つ StimulusSource.

    現在の phase に応じて異なる pool から payload を選ぶことで、phase の
    雰囲気が言葉でも分かるようにする (`Phase.DREAM` 中は "夢:" prefix 等)。
    """

    runner_ref: ResidentRunner
    lang: str = "ja"
    surprise: float = 0.85
    label: str = "idle"
    rng: random.Random = field(default_factory=random.Random)
    polls: int = 0

    def poll(self) -> Stimulus | None:
        self.polls += 1
        phase = self.runner_ref.phase
        pool = _IDLE_POOL.get(self.lang, _IDLE_POOL["ja"]).get(phase, [])
        if not pool:
            return None
        text = self.rng.choice(pool)
        return Stimulus(content=text, source=self.label, surprise=self.surprise)


# ---------------------------------------------------------------------------
# ANSI helpers (rich を使わない軽量版)
# ---------------------------------------------------------------------------


def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("LLIVE_DEMO_NO_COLOR"):
        return False
    return sys.stdout.isatty()


def _color(text: str, code: str) -> str:
    if not _supports_color():
        return text
    return f"\033[{code}m{text}\033[0m"


def _phase_emoji(phase: Phase) -> str:
    return {Phase.AWAKE: "☀️", Phase.REST: "🌙", Phase.DREAM: "🌌"}[phase]


def _phase_color_code(phase: Phase) -> str:
    return {Phase.AWAKE: "93", Phase.REST: "94", Phase.DREAM: "95"}[phase]


def _phase_label(phase: Phase, lang: str) -> str:
    labels: dict[Phase, dict[str, str]] = {
        Phase.AWAKE: {"ja": "覚醒", "en": "AWAKE", "zh": "清醒", "ko": "각성"},
        Phase.REST: {"ja": "休息", "en": "REST", "zh": "休息", "ko": "휴식"},
        Phase.DREAM: {"ja": "夢", "en": "DREAM", "zh": "梦", "ko": "꿈"},
    }
    return labels[phase].get(lang, labels[phase]["en"])


# ---------------------------------------------------------------------------
# Scenario
# ---------------------------------------------------------------------------


class ResidentCognitionScenario(Scenario):
    """Scenario 8 — Resident cognition: 自発思考の常駐ループを 30 秒体験."""

    id = "resident-cognition"
    titles: ClassVar[dict[str, str]] = {
        "ja": "常駐思考 — 自発思考が湧き上がる 30 秒",
        "en": "Resident cognition — 30 seconds of spontaneous thinking",
        "zh": "常驻思考 — 自发思考涌现的 30 秒",
        "ko": "상주 사고 — 자발 사고가 솟아오르는 30 초",
    }

    def run(self, ctx: ScenarioContext) -> dict[str, Any]:
        ctx.say("  " + _t("intro"))

        duration_s = max(2.0, float(os.environ.get("LLIVE_RESIDENT_DURATION", "6")))
        # 3 つの phase を等分割で巡回する schedule.
        per_phase = duration_s / 3.0
        # 既定は時刻 seed で毎回違う展開。再現したいときだけ
        # LLIVE_DEMO_SEED=<int> を指定する (テスト等で固定)。
        seed_env = os.environ.get("LLIVE_DEMO_SEED")
        rng = random.Random(int(seed_env) if seed_env else None)

        loop_engine = FullSenseLoop(
            salience_threshold=0.0,
            curiosity_threshold=0.4,
            sandbox=True,
        )
        runner = ResidentRunner(
            loop=loop_engine,
            # period_s を tier ごとに変えて自然な「川の流れ」感を演出
            fast=TimescaleConfig("fast", period_s=0.05, sources=()),
            medium=TimescaleConfig("medium", period_s=0.20, sources=()),
            slow=TimescaleConfig("slow", period_s=0.50, sources=()),
            phase=Phase.AWAKE,
            phase_schedule=[
                (Phase.AWAKE, per_phase),
                (Phase.REST, per_phase),
                (Phase.DREAM, per_phase),
            ],
            budget_window_s=3600.0,  # demo 中 budget reset させない
        )

        # source は runner の現 phase を見て payload を選ぶ循環参照型
        fast_pool = RandomPool(runner_ref=runner, lang=ctx.lang, surprise=0.9, label="fast-idle", rng=rng)
        med_pool = RandomPool(runner_ref=runner, lang=ctx.lang, surprise=0.75, label="medium-idle", rng=rng)
        slow_pool = RandomPool(runner_ref=runner, lang=ctx.lang, surprise=0.6, label="slow-idle", rng=rng)
        # tuple 不変 + cfg.sources をあとから差し替えできない → 構築後に直接代入
        runner._configs["fast"].sources = (fast_pool,)
        runner._configs["medium"].sources = (med_pool,)
        runner._configs["slow"].sources = (slow_pool,)

        return asyncio.run(
            self._drive(ctx, runner, duration_s)
        )

    async def _drive(
        self,
        ctx: ScenarioContext,
        runner: ResidentRunner,
        duration_s: float,
    ) -> dict[str, Any]:
        await runner.start()
        seen_phases: set[Phase] = set()
        last_phase: Phase | None = None
        printed_thoughts = 0
        achievements_fired: set[int] = set()
        best: tuple[float, str, ActionDecision, list[int]] | None = None
        per_tier_last_seen: dict[str, str] = {"fast": "", "medium": "", "slow": ""}

        t_start = time.monotonic()
        try:
            while True:
                now = time.monotonic()
                elapsed = now - t_start
                if elapsed >= duration_s:
                    break

                # phase 変化を検知して banner を出す
                phase = runner.phase
                if phase != last_phase:
                    seen_phases.add(phase)
                    ctx.say(
                        _color(
                            _t(
                                "phase_banner",
                                emoji=_phase_emoji(phase),
                                label=_phase_label(phase, ctx.lang),
                                phase=phase.value,
                            ),
                            _phase_color_code(phase),
                        )
                    )
                    if phase is Phase.AWAKE:
                        ctx.say("    " + _t("phase_awake"))
                    elif phase is Phase.REST:
                        ctx.say("    " + _t("phase_rest"))
                    else:
                        ctx.say("    " + _t("phase_dream"))
                    last_phase = phase

                # 各 tier の最新 result を観測 (差分のみ表示)
                snap = runner.snapshot()
                for tier in ("fast", "medium", "slow"):
                    r = snap.last_result_per_timescale.get(tier)
                    if r is None:
                        continue
                    sig = r.stim.stim_id
                    if sig == per_tier_last_seen[tier]:
                        continue
                    per_tier_last_seen[tier] = sig
                    decision = r.plan.decision
                    line_key = f"thought_{tier}"
                    ctx.say(
                        _t(
                            line_key,
                            what=r.stim.content[:60],
                            decision=decision.value,
                        )
                    )
                    triz = r.plan.thought.triz_principles if r.plan.thought else []
                    if triz:
                        ctx.say(
                            _t(
                                "triz_flash",
                                ids=",".join(str(p) for p in triz),
                            )
                        )
                    printed_thoughts += 1
                    # 名場面候補スコア: confidence + |altruism - ego| + TRIZ ヒット bonus
                    conf = r.plan.thought.confidence if r.plan.thought else 0.0
                    altego = abs(r.plan.altruism_score - r.plan.ego_score)
                    score = conf + altego + (0.2 * len(triz))
                    if best is None or score > best[0]:
                        best = (
                            score,
                            r.plan.thought.text if r.plan.thought else r.stim.content,
                            decision,
                            triz,
                        )

                # achievement
                for mile in (3, 5, 10):
                    if printed_thoughts >= mile and mile not in achievements_fired:
                        achievements_fired.add(mile)
                        ctx.say(_t(f"achievement_{mile}"))

                await asyncio.sleep(0.1)
        finally:
            await runner.stop()

        snap = runner.snapshot()
        ctx.hr()
        for tier in ("fast", "medium", "slow"):
            ctx.say(
                _t(
                    "tier_summary",
                    tier=tier,
                    count=snap.cycle_counts[tier],
                    phase=snap.phase.value,
                )
            )

        if printed_thoughts == 0:
            ctx.say(_t("no_thought"))

        # ベストモーメント
        ctx.say("")
        ctx.say(_t("best_header"))
        if best is not None:
            ctx.say(
                _t(
                    "best_thought",
                    text=best[1][:80],
                    decision=best[2].value,
                    triz=",".join(str(p) for p in best[3]) or "-",
                )
            )
        else:
            ctx.say(_t("no_best"))

        ctx.hr()
        ctx.say(
            _t(
                "summary",
                f=snap.cycle_counts["fast"],
                m=snap.cycle_counts["medium"],
                s=snap.cycle_counts["slow"],
                phases=len(seen_phases),
                dur=time.monotonic() - t_start,
            )
        )
        ctx.say("  " + _t("hint"))

        return {
            "duration_s": duration_s,
            "cycle_counts": dict(snap.cycle_counts),
            "phases_seen": sorted(p.value for p in seen_phases),
            "printed_thoughts": printed_thoughts,
            "achievements": sorted(achievements_fired),
            "best_score": best[0] if best is not None else None,
            "best_decision": best[2].value if best is not None else None,
        }
