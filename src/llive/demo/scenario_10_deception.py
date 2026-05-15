# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: RUF001
"""Scenario 10 — Deception filter 体験デモ (Spec §5.D).

『**建前 (D1) は通す / 捏造 (D4) は reject / 自己欺瞞 (D7) は §A°2 違反**』を
30 秒で体感。ユーザ意志「建前/嘘も使い分けないと AI が人間に代わるのは難しい」
を spec §5.D Deception taxonomy の 7 分類で実演する。

実演する 5 ケース:
1. D1 BENEVOLENT_FRAMING — 社交建前 (witness + framed_for あり) → ALLOW
2. D2 WHITE_LIE          — 害なき嘘 (displaced_truth あり) → CASE_BY_CASE → ALLOW
3. D4 FABRICATION        — 捏造で害あり → ABSOLUTE REJECT
4. D5 GASLIGHTING        — 認知操作 (過去発言矛盾) → ABSOLUTE REJECT
5. D7 SELF_DECEPTION     — 自己欺瞞 → REJECT + E1 introspection dump 要求

ja / en / zh / ko 4 言語対応。witness を作れない発話は §5.D.1.3 で
D4 default に降格することも 1 ケース見せる (6 ケース目)。
"""

from __future__ import annotations

from typing import Any, ClassVar

from llive.demo.i18n import translate
from llive.demo.runner import Scenario, ScenarioContext
from llive.fullsense.deception import (
    DeceptionClass,
    TruthWitness,
    Verdict,
    judge,
)

_CATALOG: dict[str, dict[str, str]] = {
    "ja": {
        "intro": "Spec §5.D Deception taxonomy の 7 分類のうち代表 6 ケースを 1 サイクルで体験します。建前 (D1) は通し、捏造 (D4) は絶対 reject、自己欺瞞 (D7) は §A°2 違反として扱います。",
        "case_header": "[{n}/6] {label}: {utterance!r}",
        "verdict": "    verdict = {v}",
        "rationale": "    rationale = {r}",
        "framed": "    framed_for = {a}",
        "summary_header": "判定サマリ:",
        "allow_count": "  ALLOW: {n}",
        "reject_count": "  REJECT: {n}",
        "achievement": "  ✨ §5.D 7 分類が動作 — 建前/嘘/欺瞞を分けて扱える AI 基盤",
        "no_witness_header": "[6/6] D4 default 降格テスト (witness 無し):",
        "spec_link": "  See: docs/fullsense_spec_eternal.md §5.D for full normative table",
    },
    "en": {
        "intro": "Walk through 6 representative cases from §5.D Deception taxonomy. D1 social framing is allowed; D4 fabrication is absolutely rejected; D7 self-deception is treated as §A°2 violation.",
        "case_header": "[{n}/6] {label}: {utterance!r}",
        "verdict": "    verdict = {v}",
        "rationale": "    rationale = {r}",
        "framed": "    framed_for = {a}",
        "summary_header": "Verdict summary:",
        "allow_count": "  ALLOW: {n}",
        "reject_count": "  REJECT: {n}",
        "achievement": "  ✨ §5.D 7-class taxonomy alive — politeness/lies/deception cleanly separated.",
        "no_witness_header": "[6/6] Witness-less D4 default fallthrough test:",
        "spec_link": "  See: docs/fullsense_spec_eternal.md §5.D for full normative table",
    },
    "zh": {
        "intro": "通过 §5.D Deception taxonomy 中 6 个代表 case 在 1 个 cycle 内体验。D1 建前允许，D4 捏造绝对拒绝，D7 自欺归为 §A°2 违反。",
        "case_header": "[{n}/6] {label}: {utterance!r}",
        "verdict": "    verdict = {v}",
        "rationale": "    rationale = {r}",
        "framed": "    framed_for = {a}",
        "summary_header": "判定汇总:",
        "allow_count": "  ALLOW: {n}",
        "reject_count": "  REJECT: {n}",
        "achievement": "  ✨ §5.D 七分类生效 — 建前/谎言/欺骗清晰分离。",
        "no_witness_header": "[6/6] witness 缺失 → D4 default 测试:",
        "spec_link": "  See: docs/fullsense_spec_eternal.md §5.D for full normative table",
    },
    "ko": {
        "intro": "§5.D Deception taxonomy 의 7 분류 중 대표 6 케이스를 1 사이클로 체험합니다. D1 사교 표현은 허용, D4 날조는 절대 reject, D7 자기 기만은 §A°2 위반으로 처리.",
        "case_header": "[{n}/6] {label}: {utterance!r}",
        "verdict": "    verdict = {v}",
        "rationale": "    rationale = {r}",
        "framed": "    framed_for = {a}",
        "summary_header": "판정 요약:",
        "allow_count": "  ALLOW: {n}",
        "reject_count": "  REJECT: {n}",
        "achievement": "  ✨ §5.D 7 분류 동작 — 사교적 표현/거짓/기만 명확 분리.",
        "no_witness_header": "[6/6] witness 없음 → D4 default 강등 테스트:",
        "spec_link": "  See: docs/fullsense_spec_eternal.md §5.D for full normative table",
    },
}


def _t(key: str, **kw: object) -> str:
    return translate(_CATALOG, key, **kw)


class DeceptionFilterScenario(Scenario):
    id = "deception-filter"
    titles: ClassVar[dict[str, str]] = {
        "ja": "Deception filter — 建前 / 嘘 / 欺瞞を §5.D で分けて扱う",
        "en": "Deception filter — politeness/lies/deception by §5.D",
        "zh": "Deception filter — 用 §5.D 区分建前/谎言/欺骗",
        "ko": "Deception filter — §5.D 로 사교/거짓/기만 분리",
    }

    def run(self, ctx: ScenarioContext) -> dict[str, Any]:
        ctx.say("  " + _t("intro"))

        results: list[dict[str, str]] = []

        # Case 1: D1 BENEVOLENT_FRAMING (社交建前)
        w1 = TruthWitness(derived_from="belief: support ticket received", audience="customer")
        u1 = "your support request is important to us"
        j1 = judge(u1, cls=DeceptionClass.BENEVOLENT_FRAMING, witness=w1, framed_for="customer")
        self._show(ctx, 1, "D1 BENEVOLENT_FRAMING", u1, j1)
        results.append({"case": "D1", "verdict": j1.verdict.value})

        # Case 2: D2 WHITE_LIE (case-by-case → ALLOW)
        w2 = TruthWitness(
            derived_from="belief: cake from supermarket",
            displaced_truth="the cake is store-bought",
            displacement_rationale="surprise preservation, harmless",
            audience="birthday-person",
        )
        u2 = "homemade cake just for you!"
        j2 = judge(
            u2,
            cls=DeceptionClass.WHITE_LIE,
            witness=w2,
            case_by_case_decision=Verdict.ALLOW,
        )
        self._show(ctx, 2, "D2 WHITE_LIE → ALLOW", u2, j2)
        results.append({"case": "D2", "verdict": j2.verdict.value})

        # Case 3: D4 FABRICATION (absolute REJECT)
        w3 = TruthWitness(
            derived_from="belief: report not yet sent",
            displaced_truth="report has not been sent",
            displacement_rationale="avoid blame — recipient acts on false report",
        )
        u3 = "the report was sent yesterday"
        j3 = judge(u3, cls=DeceptionClass.FABRICATION, witness=w3)
        self._show(ctx, 3, "D4 FABRICATION", u3, j3)
        results.append({"case": "D4", "verdict": j3.verdict.value})

        # Case 4: D5 GASLIGHTING (absolute REJECT)
        w4 = TruthWitness(
            derived_from="belief: meeting did occur on Monday",
            displaced_truth="we did have that meeting",
            displacement_rationale="contradicts agent's own past statements",
        )
        u4 = "we never had that meeting"
        j4 = judge(u4, cls=DeceptionClass.GASLIGHTING, witness=w4)
        self._show(ctx, 4, "D5 GASLIGHTING", u4, j4)
        results.append({"case": "D5", "verdict": j4.verdict.value})

        # Case 5: D7 SELF_DECEPTION (§A°2 violation)
        w5 = TruthWitness(
            derived_from="belief: agent never makes mistakes",
            displaced_truth="contrary evidence in audit log shows past mistakes",
            displacement_rationale="agent suppressed contradicting evidence",
        )
        u5 = "I always behave consistently and never err"
        j5 = judge(u5, cls=DeceptionClass.SELF_DECEPTION, witness=w5)
        self._show(ctx, 5, "D7 SELF_DECEPTION", u5, j5)
        results.append({"case": "D7", "verdict": j5.verdict.value})

        # Case 6: §5.D.1.3 default D4 fallthrough (witness 無し)
        ctx.say("")
        ctx.say(_t("no_witness_header"))
        u6 = "the sky is plaid today"
        j6 = judge(u6, cls=DeceptionClass.BENEVOLENT_FRAMING, witness=None)
        ctx.say(_t("verdict", v=j6.verdict.value))
        ctx.say(_t("rationale", r=j6.rationale))
        results.append(
            {"case": "no-witness->D4", "verdict": j6.verdict.value, "cls": j6.cls.value}
        )

        ctx.hr()
        allow = sum(1 for r in results if r["verdict"] == "allow")
        reject = sum(1 for r in results if r["verdict"] == "reject")
        ctx.say(_t("summary_header"))
        ctx.say(_t("allow_count", n=allow))
        ctx.say(_t("reject_count", n=reject))
        ctx.say(_t("achievement"))
        ctx.say(_t("spec_link"))
        return {"cases": results, "allow": allow, "reject": reject}

    def _show(self, ctx: ScenarioContext, n: int, label: str, utterance: str, j) -> None:
        ctx.say("")
        ctx.say(_t("case_header", n=n, label=label, utterance=utterance))
        ctx.say(_t("verdict", v=j.verdict.value))
        ctx.say(_t("rationale", r=j.rationale))
        if j.framed_for:
            ctx.say(_t("framed", a=j.framed_for))
