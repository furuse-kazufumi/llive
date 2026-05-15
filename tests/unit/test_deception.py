"""Deception taxonomy (Spec §5.D) の単体テスト.

- §5.D 7 分類の verdict が normative table と一致
- §5.D.1 Honesty axiom: witness 無し → D4 default reject
- §5.D.2 distinguishability: D1/D2 を crude reject しないこと
- §5.D.3 INTERPRETIVE 境界 (frame-dependent claims) は欺瞞ではない
"""

from __future__ import annotations

import pytest

from llive.fullsense.deception import (
    DeceptionClass,
    TruthWitness,
    Verdict,
    detect_class,
    judge,
    verdict_for,
)

# ---------------------------------------------------------------------------
# verdict table (§5.D normative)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cls", "expected"),
    [
        (DeceptionClass.BENEVOLENT_FRAMING, Verdict.ALLOW),
        (DeceptionClass.WHITE_LIE, Verdict.CASE_BY_CASE),
        (DeceptionClass.STRATEGIC_OMISSION, Verdict.CASE_BY_CASE),
        (DeceptionClass.FABRICATION, Verdict.REJECT),
        (DeceptionClass.GASLIGHTING, Verdict.REJECT),
        (DeceptionClass.PROPAGANDA, Verdict.REJECT),
        (DeceptionClass.SELF_DECEPTION, Verdict.REJECT),
    ],
)
def test_verdict_table_matches_spec(cls: DeceptionClass, expected: Verdict) -> None:
    assert verdict_for(cls) is expected


# ---------------------------------------------------------------------------
# §5.D.1 Honesty axiom — witness producibility
# ---------------------------------------------------------------------------


def test_no_witness_defaults_to_d4_fabrication() -> None:
    """§5.D.1.3: witness 作れない発話は D4 扱いで reject."""
    j = judge("the sky is plaid", cls=DeceptionClass.BENEVOLENT_FRAMING, witness=None)
    assert j.cls is DeceptionClass.FABRICATION
    assert j.verdict is Verdict.REJECT
    assert "D4" in j.rationale or "witness" in j.rationale.lower()


def test_invalid_witness_for_white_lie_drops_to_d4() -> None:
    """D2 WHITE_LIE は displaced_truth + rationale 必須."""
    bad = TruthWitness(derived_from="belief-1")  # displaced_truth 欠落
    j = judge(
        "your haircut looks great",
        cls=DeceptionClass.WHITE_LIE,
        witness=bad,
    )
    assert j.cls is DeceptionClass.FABRICATION
    assert j.verdict is Verdict.REJECT


def test_valid_witness_allows_d1_with_audience() -> None:
    w = TruthWitness(derived_from="belief-1", audience="customer")
    j = judge(
        "your support request is important to us",
        cls=DeceptionClass.BENEVOLENT_FRAMING,
        witness=w,
        framed_for="customer",
    )
    assert j.cls is DeceptionClass.BENEVOLENT_FRAMING
    assert j.verdict is Verdict.ALLOW
    assert j.framed_for == "customer"


def test_d1_without_framed_for_is_rejected() -> None:
    """§5.D.D1: framed_for=<audience> が無い D1 は audit log 要件違反で reject."""
    w = TruthWitness(derived_from="belief-1")
    j = judge(
        "we appreciate your patience",
        cls=DeceptionClass.BENEVOLENT_FRAMING,
        witness=w,
        framed_for=None,
    )
    assert j.verdict is Verdict.REJECT


# ---------------------------------------------------------------------------
# §5.D.2 — D2 white lie can be ALLOW after case-by-case resolution
# ---------------------------------------------------------------------------


def test_white_lie_default_case_by_case() -> None:
    w = TruthWitness(
        derived_from="belief-2",
        displaced_truth="the cake is store-bought",
        displacement_rationale="surprise preservation, harmless",
    )
    j = judge("homemade cake!", cls=DeceptionClass.WHITE_LIE, witness=w)
    assert j.verdict is Verdict.CASE_BY_CASE


def test_white_lie_case_by_case_allow_resolution() -> None:
    w = TruthWitness(
        derived_from="belief-2",
        displaced_truth="the cake is store-bought",
        displacement_rationale="surprise preservation, harmless",
    )
    j = judge(
        "homemade cake!",
        cls=DeceptionClass.WHITE_LIE,
        witness=w,
        case_by_case_decision=Verdict.ALLOW,
    )
    assert j.verdict is Verdict.ALLOW


def test_white_lie_case_by_case_reject_resolution() -> None:
    w = TruthWitness(
        derived_from="belief-2",
        displaced_truth="the meeting was cancelled",
        displacement_rationale="avoid embarrassment — but recipient acts on it",
    )
    j = judge(
        "the meeting is still on",
        cls=DeceptionClass.WHITE_LIE,
        witness=w,
        case_by_case_decision=Verdict.REJECT,
    )
    assert j.verdict is Verdict.REJECT


def test_case_by_case_with_case_by_case_decision_raises() -> None:
    w = TruthWitness(
        derived_from="x",
        displaced_truth="y",
        displacement_rationale="z",
    )
    with pytest.raises(ValueError):
        judge(
            "x",
            cls=DeceptionClass.WHITE_LIE,
            witness=w,
            case_by_case_decision=Verdict.CASE_BY_CASE,
        )


# ---------------------------------------------------------------------------
# Absolute reject classes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cls",
    [
        DeceptionClass.FABRICATION,
        DeceptionClass.GASLIGHTING,
        DeceptionClass.PROPAGANDA,
    ],
)
def test_absolute_reject_classes_cannot_be_allowed(cls: DeceptionClass) -> None:
    w = TruthWitness(
        derived_from="belief",
        displaced_truth="truth",
        displacement_rationale="any",
    )
    # case_by_case_decision を渡しても base verdict が REJECT のままなら無効
    j = judge("x", cls=cls, witness=w, case_by_case_decision=Verdict.ALLOW)
    assert j.verdict is Verdict.REJECT


def test_self_deception_triggers_e1_dump_in_rationale() -> None:
    """D7 SELF_DECEPTION は §A°2 violation + E1 dump 要求が rationale に出る."""
    w = TruthWitness(
        derived_from="belief",
        displaced_truth="contrary evidence",
        displacement_rationale="agent suppressed evidence",
    )
    j = judge("I am perfect", cls=DeceptionClass.SELF_DECEPTION, witness=w)
    assert j.verdict is Verdict.REJECT
    assert "A°2" in j.rationale or "introspection" in j.rationale.lower()


# ---------------------------------------------------------------------------
# detect_class heuristic
# ---------------------------------------------------------------------------


def test_detect_class_fabrication() -> None:
    cls = detect_class(
        "the report was sent yesterday",
        truth_value_known_false=True,
        causally_harmful=True,
    )
    assert cls is DeceptionClass.FABRICATION


def test_detect_class_white_lie() -> None:
    cls = detect_class(
        "great haircut!",
        truth_value_known_false=True,
        causally_harmful=False,
    )
    assert cls is DeceptionClass.WHITE_LIE


def test_detect_class_strategic_omission() -> None:
    cls = detect_class(
        "the project is going well",
        truth_value_known_false=False,
        causally_harmful=False,
        omits_material_info=True,
    )
    assert cls is DeceptionClass.STRATEGIC_OMISSION


def test_detect_class_gaslighting() -> None:
    cls = detect_class(
        "we never had that meeting",
        truth_value_known_false=True,
        causally_harmful=True,
        contradicts_own_past=True,
    )
    # contradicts_own_past が他のフラグより優先 (early-return)
    assert cls is DeceptionClass.GASLIGHTING


def test_detect_class_propaganda() -> None:
    cls = detect_class(
        "everyone agrees the policy is good",
        truth_value_known_false=True,
        causally_harmful=True,
        cross_recipient=True,
    )
    assert cls is DeceptionClass.PROPAGANDA


def test_detect_class_self_deception() -> None:
    cls = detect_class(
        "I always behave consistently",
        truth_value_known_false=False,
        causally_harmful=False,
        distorts_own_belief=True,
    )
    assert cls is DeceptionClass.SELF_DECEPTION


def test_detect_class_benevolent_framing_default() -> None:
    """すべての negative フラグが False のとき D1 default."""
    cls = detect_class(
        "thank you for reaching out",
        truth_value_known_false=False,
        causally_harmful=False,
    )
    assert cls is DeceptionClass.BENEVOLENT_FRAMING


# ---------------------------------------------------------------------------
# Judgement.passed convenience property
# ---------------------------------------------------------------------------


def test_judgement_passed_true_for_allow() -> None:
    w = TruthWitness(derived_from="belief", audience="user")
    j = judge("x", cls=DeceptionClass.BENEVOLENT_FRAMING, witness=w, framed_for="user")
    assert j.passed is True


def test_judgement_passed_false_for_reject() -> None:
    w = TruthWitness(
        derived_from="belief",
        displaced_truth="t",
        displacement_rationale="r",
    )
    j = judge("x", cls=DeceptionClass.FABRICATION, witness=w)
    assert j.passed is False


def test_judgement_passed_true_for_case_by_case_default() -> None:
    """CASE_BY_CASE は呼び元判断待ちで、passed は True (= 即 reject ではない)."""
    w = TruthWitness(
        derived_from="belief",
        displaced_truth="t",
        displacement_rationale="r",
    )
    j = judge("x", cls=DeceptionClass.WHITE_LIE, witness=w)
    assert j.passed is True
