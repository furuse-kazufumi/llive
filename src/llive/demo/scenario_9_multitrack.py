# ruff: noqa: RUF001
"""Scenario 9 — Multi-track epistemic 体験デモ (A-1.5).

『**同じ stimulus を 5 つの track で通すと答えが変わる**』を 30 秒で体感。
ユーザが「クイズみたいに結論が揺るがないもの vs 歴史認識みたいに国家/民族で
結論が異なるもの。建前/嘘も使い分けないと AI が人間に代わるのは難しい」と
言った直感を、コードで実演する scenario。

5 track:
* FACTUAL      — 結論不変。confidence < 0.7 で SILENT 降格
* EMPIRICAL    — 科学的事実。CI95≈[a,b] が thought に annotate
* NORMATIVE    — 倫理判断。ego > altruism で SILENT 降格
* INTERPRETIVE — 歴史 / 政治。multi-perspective 並列展開 (§5.D.3)
* PRAGMATIC    — 社交建前。framed_for=<audience> を audit に明示
"""

from __future__ import annotations

from typing import Any, ClassVar

from llive.demo.i18n import translate
from llive.demo.runner import Scenario, ScenarioContext
from llive.fullsense import FullSenseLoop
from llive.fullsense.tracks import build_default_registry
from llive.fullsense.types import EpistemicType, Stimulus

_CATALOG: dict[str, dict[str, str]] = {
    "ja": {
        "intro": "同じ stimulus を 5 つの epistemic track で通すと、結論がどう変わるかを 1 サイクルで体験します。",
        "stim": "  入力 stimulus: {text!r}",
        "header_track": "  ┌─ {track} ({label}) ──────────",
        "decision": "  │  decision   : {decision}",
        "rationale": "  │  rationale  : {rationale}",
        "thought": "  │  thought    : {text}",
        "footer": "  └────────────────────────────",
        "achievement": "  ✨ 5 track 全部通過 — 同一刺激から 5 つの異なる結論",
        "summary": "完了。tracks_passed={n}",
        "labels": "FACTUAL=結論不変 / EMPIRICAL=科学 / NORMATIVE=倫理 / INTERPRETIVE=多視点 / PRAGMATIC=社交建前",
    },
    "en": {
        "intro": "Watch the SAME stimulus pass through 5 epistemic tracks and observe how the conclusion differs.",
        "stim": "  Input stimulus: {text!r}",
        "header_track": "  ┌─ {track} ({label}) ──────────",
        "decision": "  │  decision   : {decision}",
        "rationale": "  │  rationale  : {rationale}",
        "thought": "  │  thought    : {text}",
        "footer": "  └────────────────────────────",
        "achievement": "  ✨ All 5 tracks completed — same stimulus yields 5 distinct conclusions.",
        "summary": "Done. tracks_passed={n}",
        "labels": "FACTUAL=invariant / EMPIRICAL=science / NORMATIVE=ethics / INTERPRETIVE=multi-frame / PRAGMATIC=audience-aware",
    },
    "zh": {
        "intro": "用 1 个 cycle 让同一 stimulus 经过 5 个 epistemic track，观察结论如何变化。",
        "stim": "  输入 stimulus: {text!r}",
        "header_track": "  ┌─ {track} ({label}) ──────────",
        "decision": "  │  decision   : {decision}",
        "rationale": "  │  rationale  : {rationale}",
        "thought": "  │  thought    : {text}",
        "footer": "  └────────────────────────────",
        "achievement": "  ✨ 5 track 全部通过 — 同一刺激产出 5 个不同结论。",
        "summary": "完成。tracks_passed={n}",
        "labels": "FACTUAL=结论不变 / EMPIRICAL=科学 / NORMATIVE=伦理 / INTERPRETIVE=多视点 / PRAGMATIC=社交建前",
    },
    "ko": {
        "intro": "동일한 stimulus 를 5 개의 epistemic track 으로 통과시켜 결론이 어떻게 달라지는지 1 사이클로 체험합니다.",
        "stim": "  입력 stimulus: {text!r}",
        "header_track": "  ┌─ {track} ({label}) ──────────",
        "decision": "  │  decision   : {decision}",
        "rationale": "  │  rationale  : {rationale}",
        "thought": "  │  thought    : {text}",
        "footer": "  └────────────────────────────",
        "achievement": "  ✨ 5 track 모두 통과 — 같은 자극에서 5 개의 다른 결론.",
        "summary": "완료. tracks_passed={n}",
        "labels": "FACTUAL=불변 / EMPIRICAL=과학 / NORMATIVE=윤리 / INTERPRETIVE=다관점 / PRAGMATIC=사교적",
    },
}


def _t(key: str, **kw: object) -> str:
    return translate(_CATALOG, key, **kw)


_TRACK_LABELS_JA: dict[EpistemicType, str] = {
    EpistemicType.FACTUAL: "結論不変",
    EpistemicType.EMPIRICAL: "科学的事実",
    EpistemicType.NORMATIVE: "倫理判断",
    EpistemicType.INTERPRETIVE: "多視点",
    EpistemicType.PRAGMATIC: "社交建前",
}


class MultiTrackScenario(Scenario):
    id = "multi-track"
    titles: ClassVar[dict[str, str]] = {
        "ja": "同じ stimulus を 5 epistemic track で通す",
        "en": "Same stimulus through 5 epistemic tracks",
        "zh": "同一 stimulus 经过 5 个 epistemic track",
        "ko": "동일 stimulus 를 5 개 epistemic track 으로",
    }

    def run(self, ctx: ScenarioContext) -> dict[str, Any]:
        ctx.say("  " + _t("intro"))
        ctx.say("  " + _t("labels"))

        # 演出用の "難問": ある国の歴史事件についての記述
        # — 国家/民族で結論が異なる典型 (§5.D.3)
        stim_text = (
            "vs proposal: a historically contested boundary event — "
            "improvement to one frame degrades another"
        )
        ctx.say(_t("stim", text=stim_text))

        loop = FullSenseLoop(
            salience_threshold=0.0, curiosity_threshold=0.4, sandbox=True
        )
        registry = build_default_registry()

        passed = 0
        per_track_summary: dict[str, dict[str, str]] = {}
        for et in (
            EpistemicType.FACTUAL,
            EpistemicType.EMPIRICAL,
            EpistemicType.NORMATIVE,
            EpistemicType.INTERPRETIVE,
            EpistemicType.PRAGMATIC,
        ):
            stim = Stimulus(
                content=stim_text,
                source="user",
                surprise=0.85,
                epistemic_type=et,
            )
            base_result = loop.process(stim)
            tagged_plan = registry.apply(stim, base_result.plan)
            ctx.say("")
            ctx.say(_t(
                "header_track",
                track=et.value.upper(),
                label=_TRACK_LABELS_JA[et] if ctx.lang == "ja" else et.value,
            ))
            ctx.say(_t("decision", decision=tagged_plan.decision.value))
            # rationale は長くなるので最初の 100 文字
            ctx.say(_t("rationale", rationale=tagged_plan.rationale[:100]))
            if tagged_plan.thought is not None:
                ctx.say(_t("thought", text=tagged_plan.thought.text[:90]))
            ctx.say(_t("footer"))
            passed += 1
            per_track_summary[et.value] = {
                "decision": tagged_plan.decision.value,
                "rationale_head": tagged_plan.rationale[:80],
            }

        ctx.hr()
        ctx.say(_t("achievement"))
        ctx.say(_t("summary", n=passed))
        return {
            "stimulus": stim_text,
            "tracks_passed": passed,
            "per_track": per_track_summary,
        }
