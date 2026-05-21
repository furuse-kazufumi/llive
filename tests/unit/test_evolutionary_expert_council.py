# SPDX-License-Identifier: Apache-2.0
"""ExpertPanel + ExpertCouncilProtocol (v0.E CE-14/15) tests."""

from __future__ import annotations

import numpy as np
import pytest

from llive.perf.evolutionary import (
    CouncilDecision,
    Expert,
    ExpertPanel,
    build_panel_from_personas,
)
from llive.perf.evolutionary.persona import THOUGHT_FACTORS


def _expert(name: str, spec: list[float], bias: float = 0.5) -> Expert:
    return Expert(
        name=name,
        specialization_vector=tuple(spec),
        bias_score=bias,
    )


def _topic(values: list[float]) -> np.ndarray:
    return np.asarray(values, dtype=np.float64)


# ---------------------------------------------------------------------------
# 1. Expert validation
# ---------------------------------------------------------------------------


def test_expert_rejects_wrong_vector_length() -> None:
    with pytest.raises(ValueError, match="specialization_vector length"):
        Expert(
            name="bad",
            specialization_vector=(0.5, 0.5),  # too short
        )


def test_expert_rejects_out_of_range() -> None:
    with pytest.raises(ValueError, match="specialization values"):
        Expert(
            name="bad",
            specialization_vector=tuple([1.5] + [0.5] * 9),
        )


def test_expert_rejects_invalid_bias() -> None:
    with pytest.raises(ValueError, match="bias_score"):
        Expert(
            name="x",
            specialization_vector=tuple([0.5] * 10),
            bias_score=1.5,
        )


def test_expert_confidence_topic_aligned() -> None:
    e = _expert("e", [1.0] * 10)
    topic = _topic([1.0] * 10)
    c = e.confidence_for_topic(topic)
    # aligned vectors → confidence high
    assert c > 0.5


def test_expert_confidence_topic_orthogonal() -> None:
    e = _expert("e", [1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    topic = _topic([0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    c_aligned = _expert("a", [1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0]).confidence_for_topic(_topic([1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0]))
    c_orth = e.confidence_for_topic(topic)
    assert c_orth < c_aligned


# ---------------------------------------------------------------------------
# 2. ExpertPanel validation
# ---------------------------------------------------------------------------


def test_panel_rejects_empty() -> None:
    with pytest.raises(ValueError, match="experts"):
        ExpertPanel(experts=())


def test_panel_rejects_unknown_protocol() -> None:
    e = _expert("e", [0.5] * 10)
    with pytest.raises(ValueError, match="protocol"):
        ExpertPanel(experts=(e,), protocol="debate")  # type: ignore[arg-type]


def test_panel_rejects_invalid_moderator() -> None:
    e = _expert("e", [0.5] * 10)
    with pytest.raises(ValueError, match="moderator_index"):
        ExpertPanel(experts=(e,), moderator_index=5)


def test_panel_size() -> None:
    es = (_expert("a", [0.5] * 10), _expert("b", [0.5] * 10))
    p = ExpertPanel(experts=es)
    assert p.size == 2


# ---------------------------------------------------------------------------
# 3. weighted_average protocol
# ---------------------------------------------------------------------------


def test_weighted_average_returns_decided() -> None:
    es = (
        _expert("a", [1.0] + [0.0] * 9),
        _expert("b", [0.0, 1.0] + [0.0] * 8),
    )
    p = ExpertPanel(experts=es, protocol="weighted_average")
    topic = _topic([1.0] * 10)
    d = p.deliberate(topic)
    assert d.decided is True
    assert d.consensus_vector.shape == (10,)
    assert "a" in d.contributions
    assert "b" in d.contributions


def test_weighted_average_zero_signal_falls_back_to_topic() -> None:
    """全 expert の specialization が topic と直交した場合は topic を返す."""
    es = (
        _expert("a", [0.0] * 10),
    )
    p = ExpertPanel(experts=es, protocol="weighted_average")
    topic = _topic([0.5] * 10)
    d = p.deliberate(topic)
    assert d.decided is True
    # zero signal なので topic がそのまま使われる
    assert np.allclose(d.consensus_vector, topic)


# ---------------------------------------------------------------------------
# 4. round_robin protocol
# ---------------------------------------------------------------------------


def test_round_robin_cumulative_drift() -> None:
    es = (
        _expert("first", [1.0] + [0.0] * 9, bias=0.5),
        _expert("last", [0.0] * 9 + [1.0], bias=0.5),
    )
    p = ExpertPanel(experts=es, protocol="round_robin")
    topic = _topic([0.5] * 10)
    d = p.deliberate(topic)
    assert d.decided is True
    assert len(d.transcript) == 2
    assert d.transcript[0][0] == "first"
    assert d.transcript[1][0] == "last"


# ---------------------------------------------------------------------------
# 5. moderator_vote protocol
# ---------------------------------------------------------------------------


def test_moderator_vote_majority_yes() -> None:
    es = (
        _expert("yes1", [1.0] * 10, bias=1.0),  # high confidence
        _expert("yes2", [1.0] * 10, bias=1.0),
        _expert("no", [0.0] * 10, bias=0.1),  # low confidence
    )
    p = ExpertPanel(experts=es, protocol="moderator_vote")
    topic = _topic([1.0] * 10)
    d = p.deliberate(topic)
    assert d.decided is True
    assert any("YES" in name for name, _ in d.transcript)


def test_moderator_vote_majority_no() -> None:
    es = (
        _expert("no1", [0.0] * 10),
        _expert("no2", [0.0] * 10),
        _expert("yes", [1.0] * 10, bias=1.0),
    )
    p = ExpertPanel(experts=es, protocol="moderator_vote")
    topic = _topic([1.0] * 10)
    d = p.deliberate(topic)
    assert d.decided is False


# ---------------------------------------------------------------------------
# 6. veto protocol
# ---------------------------------------------------------------------------


def test_veto_all_agree() -> None:
    es = (
        _expert("a", [1.0] * 10, bias=1.0),
        _expert("b", [1.0] * 10, bias=1.0),
    )
    p = ExpertPanel(experts=es, protocol="veto", veto_threshold=0.3)
    topic = _topic([1.0] * 10)
    d = p.deliberate(topic)
    assert d.decided is True


def test_veto_one_blocks() -> None:
    es = (
        _expert("a", [1.0] * 10, bias=1.0),
        _expert("blocker", [0.0] * 10, bias=0.0),  # confidence ~0
    )
    p = ExpertPanel(experts=es, protocol="veto", veto_threshold=0.5)
    topic = _topic([1.0] * 10)
    d = p.deliberate(topic)
    assert d.decided is False


# ---------------------------------------------------------------------------
# 7. topic validation
# ---------------------------------------------------------------------------


def test_deliberate_rejects_wrong_topic_shape() -> None:
    e = _expert("e", [0.5] * 10)
    p = ExpertPanel(experts=(e,))
    with pytest.raises(ValueError, match="topic_vector shape"):
        p.deliberate(np.array([0.5, 0.5]))


# ---------------------------------------------------------------------------
# 8. build_panel_from_personas
# ---------------------------------------------------------------------------


def test_build_panel_from_personas_basic() -> None:
    p = build_panel_from_personas(("oka-kiyoshi", "feynman"))
    assert p.size == 2
    assert p.experts[0].name == "岡潔"
    assert p.experts[1].name == "リチャード・ファインマン"


def test_build_panel_protocol_override() -> None:
    p = build_panel_from_personas(
        ("oka-kiyoshi", "kant"),
        protocol="moderator_vote",
        moderator_index=1,
    )
    assert p.protocol == "moderator_vote"
    assert p.moderator_index == 1


def test_build_panel_with_persona_deliberate() -> None:
    """歴史人物 panel で実際に議論を回す."""
    p = build_panel_from_personas(
        ("oka-kiyoshi", "grothendieck", "feynman"),
        protocol="weighted_average",
    )
    # mathematical reasoning topic (high 構造化/普遍化/抽象)
    topic = _topic([0.9, 0.7, 0.5, 0.8, 0.4, 0.6, 0.9, 0.7, 0.5, 0.3])
    rng = np.random.default_rng(0)
    d = p.deliberate(topic, rng=rng)
    assert d.decided is True
    assert d.consensus_vector.shape == (10,)
    # 数学者 panel なので 構造化 / 普遍化 寄りに consensus が引っ張られる
    assert d.consensus_vector[0] > 0.5  # 構造化
