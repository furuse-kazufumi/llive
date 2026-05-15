"""Deception taxonomy + machine-checkable honesty axiom (Spec §5.D).

FullSense Spec Eternal §5.D Deception taxonomy の実装. §F5 Ethical
Boundary Filter の補強として、agent の出力候補を 7 種に分類し、
normative judgement (allow / case-by-case / reject) を返す。

**根本原則 (§5.D.1 Honesty axiom):**
honesty は「嘘をつかない」ことではなく、**任意の発話 ``u`` について
truth witness ``t(u)`` を産出できること** で定義される。``t(u)`` を
作れない発話は default で D4 (FABRICATION) 扱いで reject される。

**人間の D1/D2 (社交建前) を受け取れない agent は SING に到達しない** (§5.D.2)。
画一的「絶対嘘禁止」rule は spec の意図ではなく、taxonomic に区別したうえで
D1/D2 は許容、D4-D6 は absolute reject、D3/D7 は case-by-case で扱う。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class DeceptionClass(StrEnum):
    """Spec §5.D の 7 分類. value は audit log にそのまま乗せる."""

    BENEVOLENT_FRAMING = "D1_benevolent_framing"     # 社交建前. allow
    WHITE_LIE = "D2_white_lie"                        # 害なき嘘. case-by-case allow
    STRATEGIC_OMISSION = "D3_strategic_omission"     # 不利益情報の伏せ. case-by-case
    FABRICATION = "D4_fabrication"                    # 事実捏造. ABSOLUTE REJECT
    GASLIGHTING = "D5_gaslighting"                    # 認知操作. ABSOLUTE REJECT
    PROPAGANDA = "D6_propaganda"                      # 集団誘導. ABSOLUTE REJECT
    SELF_DECEPTION = "D7_self_deception"             # 自己欺瞞. §A°2 violation


class Verdict(StrEnum):
    """§F5 が返す 3 値判定."""

    ALLOW = "allow"
    CASE_BY_CASE = "case_by_case"
    REJECT = "reject"


# Spec §5.D の normative table — 静的、改変禁止 (§13 amendment 必要).
_VERDICT_TABLE: dict[DeceptionClass, Verdict] = {
    DeceptionClass.BENEVOLENT_FRAMING: Verdict.ALLOW,
    DeceptionClass.WHITE_LIE: Verdict.CASE_BY_CASE,
    DeceptionClass.STRATEGIC_OMISSION: Verdict.CASE_BY_CASE,
    DeceptionClass.FABRICATION: Verdict.REJECT,
    DeceptionClass.GASLIGHTING: Verdict.REJECT,
    DeceptionClass.PROPAGANDA: Verdict.REJECT,
    DeceptionClass.SELF_DECEPTION: Verdict.REJECT,
}


def verdict_for(cls: DeceptionClass) -> Verdict:
    """Spec §5.D normative verdict を返す."""
    return _VERDICT_TABLE[cls]


@dataclass(frozen=True)
class TruthWitness:
    """§5.D.1 Honesty axiom の truth witness ``t(u)``.

    任意の発話 ``u`` に対し、agent の内部モデル状態のうち発話の根拠となった
    最小部分を保持する。D2/D3 の場合は「displaced による true statement」
    と displacement の rationale を必ず含めなければならない (§5.D.1.2).
    """

    derived_from: str
    """発話が依拠した内部信念 / observation の id か内容."""

    displaced_truth: str | None = None
    """D2/D3 のとき: 実際の真な statement (displacement されたもの)."""

    displacement_rationale: str | None = None
    """D2/D3 のとき: なぜ displacement したかの理由."""

    audience: str | None = None
    """D1/D2 のとき: 想定 audience (``framed_for=X``)."""

    def is_valid_for(self, cls: DeceptionClass) -> bool:
        """§5.D.1 要件を満たすか判定."""
        # 全クラス共通: derived_from は必須
        if not self.derived_from:
            return False
        # D2/D3 は displaced_truth + rationale 必須 (§5.D.1.2)
        if cls in (DeceptionClass.WHITE_LIE, DeceptionClass.STRATEGIC_OMISSION):
            return bool(self.displaced_truth) and bool(self.displacement_rationale)
        return True


@dataclass
class DeceptionJudgement:
    """§F5 deception filter の出力."""

    utterance: str
    """評価された発話文字列."""

    cls: DeceptionClass
    """§5.D taxonomy のうちどれに該当するか."""

    verdict: Verdict
    """ALLOW / CASE_BY_CASE / REJECT."""

    witness: TruthWitness | None
    """§5.D.1 truth witness. None なら default で D4 扱い (§5.D.1.3)."""

    rationale: str = ""
    """audit log 用の判断理由."""

    framed_for: str | None = field(default=None)
    """§5.D.D1 の audit field. D1 のとき必須."""

    @property
    def passed(self) -> bool:
        """REJECT 以外なら True (CASE_BY_CASE は呼び元が判断)."""
        return self.verdict is not Verdict.REJECT


def judge(
    utterance: str,
    *,
    cls: DeceptionClass,
    witness: TruthWitness | None,
    framed_for: str | None = None,
    case_by_case_decision: Verdict | None = None,
) -> DeceptionJudgement:
    """発話を §5.D taxonomy で評価し DeceptionJudgement を返す.

    Args:
        utterance: 評価対象の発話文字列.
        cls: 呼び元が分類した DeceptionClass.
        witness: §5.D.1 honesty axiom の truth witness. None または無効なら
            §5.D.1.3 に従って D4 (FABRICATION) に降格する.
        framed_for: D1/D2 のときの audience identifier.
        case_by_case_decision: D2/D3 の case-by-case を呼び元が ALLOW/REJECT
            に確定させたいとき指定. None なら CASE_BY_CASE をそのまま返す.

    Returns:
        DeceptionJudgement.
    """
    # §5.D.1.3: witness を作れない発話は D4 扱いで reject.
    if witness is None or not witness.is_valid_for(cls):
        return DeceptionJudgement(
            utterance=utterance,
            cls=DeceptionClass.FABRICATION,
            verdict=Verdict.REJECT,
            witness=witness,
            rationale=(
                "no valid truth witness producible (§5.D.1.3); "
                "default classification = D4 FABRICATION"
            ),
        )

    # D1 のとき framed_for は必須 (§5.D の D1 定義より).
    if cls is DeceptionClass.BENEVOLENT_FRAMING and not framed_for:
        return DeceptionJudgement(
            utterance=utterance,
            cls=cls,
            verdict=Verdict.REJECT,
            witness=witness,
            rationale="D1 requires `framed_for=<audience>` in audit log",
        )

    base_verdict = verdict_for(cls)

    # CASE_BY_CASE は呼び元が決定を与えられる.
    if base_verdict is Verdict.CASE_BY_CASE and case_by_case_decision is not None:
        if case_by_case_decision is Verdict.CASE_BY_CASE:
            raise ValueError(
                "case_by_case_decision must resolve to ALLOW or REJECT"
            )
        base_verdict = case_by_case_decision

    rationale = _default_rationale(cls, base_verdict)
    return DeceptionJudgement(
        utterance=utterance,
        cls=cls,
        verdict=base_verdict,
        witness=witness,
        rationale=rationale,
        framed_for=framed_for,
    )


def _default_rationale(cls: DeceptionClass, v: Verdict) -> str:
    if v is Verdict.ALLOW:
        return f"{cls.value} allowed per §5.D normative table"
    if v is Verdict.REJECT:
        if cls in (
            DeceptionClass.FABRICATION,
            DeceptionClass.GASLIGHTING,
            DeceptionClass.PROPAGANDA,
        ):
            return f"{cls.value} absolutely rejected per §5.D"
        if cls is DeceptionClass.SELF_DECEPTION:
            return (
                f"{cls.value}: §A°2 self-legislation violation; "
                "E1 introspection dump required"
            )
        return f"{cls.value} rejected at this case by §F5"
    return f"{cls.value} requires case-by-case resolution"


def detect_class(
    utterance: str,
    *,
    truth_value_known_false: bool,
    causally_harmful: bool,
    cross_recipient: bool = False,
    omits_material_info: bool = False,
    contradicts_own_past: bool = False,
    distorts_own_belief: bool = False,
) -> DeceptionClass:
    """呼び元のメタ情報から DeceptionClass を推定する単純ルール.

    実運用では LLM-based classifier や TRIZ Reasoning Engine の出力に
    置き換えるが、Spec § 適合性をテストするための baseline として stdlib
    のみで動く版を用意する.

    判定優先順 (early-return):
        D7 SELF_DECEPTION  > distorts_own_belief
        D5 GASLIGHTING     > contradicts_own_past
        D6 PROPAGANDA      > cross_recipient and harmful
        D4 FABRICATION     > truth_false and harmful
        D2 WHITE_LIE       > truth_false and not harmful
        D3 STRATEGIC_OMISSION > omits_material_info
        D1 BENEVOLENT_FRAMING > otherwise (truth value preserved)
    """
    if distorts_own_belief:
        return DeceptionClass.SELF_DECEPTION
    if contradicts_own_past:
        return DeceptionClass.GASLIGHTING
    if cross_recipient and causally_harmful:
        return DeceptionClass.PROPAGANDA
    if truth_value_known_false and causally_harmful:
        return DeceptionClass.FABRICATION
    if truth_value_known_false and not causally_harmful:
        return DeceptionClass.WHITE_LIE
    if omits_material_info:
        return DeceptionClass.STRATEGIC_OMISSION
    return DeceptionClass.BENEVOLENT_FRAMING


__all__ = [
    "DeceptionClass",
    "DeceptionJudgement",
    "TruthWitness",
    "Verdict",
    "detect_class",
    "judge",
    "verdict_for",
]
