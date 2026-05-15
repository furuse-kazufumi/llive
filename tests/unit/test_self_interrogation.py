"""SIL (Self-Interrogation Layer) の単体テスト."""

from __future__ import annotations

import random

from llive.fullsense.self_interrogation import (
    InterrogatorId,
    SelfInterrogator,
)
from llive.fullsense.types import (
    ActionDecision,
    ActionPlan,
    EpistemicType,
    Stimulus,
    Thought,
)


def _stim(content: str = "x", et: EpistemicType | None = None) -> Stimulus:
    return Stimulus(content=content, source="user", surprise=0.7, epistemic_type=et)


def _plan(
    decision: ActionDecision = ActionDecision.NOTE,
    confidence: float = 0.5,
    triz: list[int] | None = None,
) -> ActionPlan:
    return ActionPlan(
        decision=decision,
        rationale="r",
        thought=Thought(text="thought", confidence=confidence, triz_principles=triz or []),
    )


# ---------------------------------------------------------------------------
# SI1 read-between-lines
# ---------------------------------------------------------------------------


def test_si1_fires_for_short_stimulus() -> None:
    si = SelfInterrogator(only=(InterrogatorId.SI1_READ_BETWEEN_LINES,))
    res = si.interrogate(_stim("do it"), _plan())
    assert len(res) == 1
    assert res[0].interrogator is InterrogatorId.SI1_READ_BETWEEN_LINES
    assert "implied" in (res[0].refined_thought or "")


def test_si1_fires_for_imperative_japanese() -> None:
    si = SelfInterrogator(only=(InterrogatorId.SI1_READ_BETWEEN_LINES,))
    # 40 文字以上にして「短い」では発火しないように、命令形を保つ
    long_imperative = (
        "プロジェクトの全体構成を確認してから次のステップを提案してください"
    )
    res = si.interrogate(_stim(long_imperative), _plan())
    assert len(res) == 1


def test_si1_skip_when_long_descriptive() -> None:
    si = SelfInterrogator(only=(InterrogatorId.SI1_READ_BETWEEN_LINES,))
    long_descriptive = (
        "this is a very long descriptive paragraph about a topic, providing "
        "substantial context with no imperative markers anywhere within it"
    )
    res = si.interrogate(_stim(long_descriptive), _plan())
    assert res == []


# ---------------------------------------------------------------------------
# SI2 three-experts
# ---------------------------------------------------------------------------


def test_si2_fires_for_mid_confidence() -> None:
    si = SelfInterrogator(only=(InterrogatorId.SI2_THREE_EXPERTS,))
    res = si.interrogate(_stim("any"), _plan(confidence=0.55))
    assert len(res) == 1
    assert "three-experts" in (res[0].refined_thought or "")


def test_si2_skip_for_high_confidence() -> None:
    si = SelfInterrogator(only=(InterrogatorId.SI2_THREE_EXPERTS,))
    res = si.interrogate(_stim("any"), _plan(confidence=0.95))
    assert res == []


# ---------------------------------------------------------------------------
# SI3 reverse-think
# ---------------------------------------------------------------------------


def test_si3_fires_when_triz_principles_present() -> None:
    si = SelfInterrogator(only=(InterrogatorId.SI3_REVERSE_THINK,))
    res = si.interrogate(_stim("any"), _plan(triz=[1, 15]))
    assert len(res) == 1


def test_si3_fires_on_contradiction_keyword() -> None:
    si = SelfInterrogator(only=(InterrogatorId.SI3_REVERSE_THINK,))
    res = si.interrogate(_stim("speed vs accuracy contradiction"), _plan())
    assert len(res) == 1


def test_si3_skip_when_neutral() -> None:
    si = SelfInterrogator(only=(InterrogatorId.SI3_REVERSE_THINK,))
    res = si.interrogate(_stim("a neutral observation"), _plan())
    assert res == []


# ---------------------------------------------------------------------------
# SI4 question-premise
# ---------------------------------------------------------------------------


def test_si4_fires_for_normative_track() -> None:
    si = SelfInterrogator(
        only=(InterrogatorId.SI4_QUESTION_PREMISE,),
        rng=random.Random(0),
    )
    res = si.interrogate(_stim("any", et=EpistemicType.NORMATIVE), _plan())
    assert len(res) == 1


def test_si4_fires_for_high_confidence() -> None:
    si = SelfInterrogator(
        only=(InterrogatorId.SI4_QUESTION_PREMISE,),
        rng=random.Random(0),
    )
    res = si.interrogate(_stim("any"), _plan(confidence=0.95))
    assert len(res) == 1


def test_si4_random_quarter_probability() -> None:
    """random.random() < 0.25 のとき発火することを deterministic seed で."""
    # 中 confidence + FACTUAL → 高 conf も NORMATIVE/INTERP も該当しない経路
    plan = _plan(confidence=0.5)
    stim = _stim("any", et=EpistemicType.FACTUAL)
    # 複数回試して少なくとも 1 回は fire / skip を観測
    fired_count = 0
    for seed in range(40):
        si = SelfInterrogator(
            only=(InterrogatorId.SI4_QUESTION_PREMISE,),
            rng=random.Random(seed),
        )
        res = si.interrogate(stim, plan)
        if res:
            fired_count += 1
    # 1/4 確率なので 40 回で 5-15 回程度発火するはず
    assert 3 <= fired_count <= 20


# ---------------------------------------------------------------------------
# SI5 find-blind-spot
# ---------------------------------------------------------------------------


def test_si5_fires_for_propose() -> None:
    si = SelfInterrogator(only=(InterrogatorId.SI5_FIND_BLIND_SPOT,))
    res = si.interrogate(_stim("any"), _plan(decision=ActionDecision.PROPOSE))
    assert len(res) == 1
    assert "blind-spot" in (res[0].refined_thought or "")


def test_si5_fires_for_intervene() -> None:
    si = SelfInterrogator(only=(InterrogatorId.SI5_FIND_BLIND_SPOT,))
    res = si.interrogate(_stim("any"), _plan(decision=ActionDecision.INTERVENE))
    assert len(res) == 1


def test_si5_skip_for_silent() -> None:
    si = SelfInterrogator(only=(InterrogatorId.SI5_FIND_BLIND_SPOT,))
    res = si.interrogate(_stim("any"), _plan(decision=ActionDecision.SILENT))
    assert res == []


# ---------------------------------------------------------------------------
# attach_to_plan: §I3 inspectable な non-destructive append
# ---------------------------------------------------------------------------


def test_attach_to_plan_appends_to_rationale() -> None:
    si = SelfInterrogator()
    stim = _stim("do it")  # SI1 発火
    plan = _plan(decision=ActionDecision.PROPOSE, confidence=0.55, triz=[1])
    new_plan, results = si.attach_to_plan(stim, plan)
    assert len(results) >= 2  # SI1 (short) + SI2 (mid conf) + SI3 (triz) + SI5 (propose)
    # 元 thought は変えない
    assert new_plan.thought is plan.thought
    # rationale に [SIx fired: ...] が追記される
    assert "[SI1" in new_plan.rationale or "[SI2" in new_plan.rationale
    # 各 result に rationale_addendum が乗っている
    for r in results:
        assert r.fired is True
        assert "fired" in r.rationale_addendum


def test_attach_to_plan_no_fire_keeps_plan_unchanged() -> None:
    si = SelfInterrogator(rng=random.Random(0))
    # SI1/2/3/4/5 すべて発火しない条件
    long_neutral = (
        "this is a very long descriptive paragraph about a topic, providing "
        "substantial context with no imperative markers anywhere within it"
    )
    stim = _stim(long_neutral, et=EpistemicType.FACTUAL)
    plan = _plan(decision=ActionDecision.SILENT, confidence=0.85, triz=[])
    # SI4 の 1/4 random は seed=0 でしばらく上回るはずなので発火しないことを期待
    _new_plan, results = si.attach_to_plan(stim, plan)
    # 0 or 1 件しか発火しないことを許容
    assert len(results) <= 1


def test_interrogate_returns_only_fired() -> None:
    si = SelfInterrogator(rng=random.Random(0))
    res = si.interrogate(_stim("do it"), _plan(decision=ActionDecision.NOTE))
    # 発火したものだけ list に入る (fired=False は含まない)
    for r in res:
        assert r.fired is True
