# SPDX-License-Identifier: Apache-2.0
"""COG-MESH-09 拡張テスト — M8.9 GrammarChangeSink + MultilingualGrammar."""

from __future__ import annotations

import pytest

from llive.cognitive_mesh.grammar_layer import (
    DEFAULT_LANGUAGES,
    GrammarChangeStatus,
    GrammarLayer,
    GrammarSnapshot,
    InMemoryGrammarChangeSink,
    MultilingualGrammar,
    ProposedChange,
    UsageEvidence,
)


def _bootstrap_layer() -> GrammarLayer:
    layer = GrammarLayer()
    layer.add_snapshot(GrammarSnapshot(language="ja", version="v_0", rules={}))
    return layer


def test_change_sink_observes_propose_promote_reject() -> None:
    sink = InMemoryGrammarChangeSink()
    layer = GrammarLayer(change_sink=sink)
    layer.add_snapshot(GrammarSnapshot(language="ja", version="v_0", rules={}))

    p1 = layer.propose_change(
        language="ja", base_version="v_0", pattern="形容詞-連用形",
        evidence=UsageEvidence(pattern="形容詞-連用形", samples=["高く", "速く"]),
    )
    assert sink.proposes == [p1]
    snap = layer.promote(p1, new_version="v_1")
    assert sink.promotes == [(p1, snap)]

    p2 = layer.propose_change(
        language="ja", base_version="v_0", pattern="噂",
        evidence=UsageEvidence(pattern="噂", samples=["test"]),
    )
    layer.reject(p2)
    assert sink.rejects == [p2]


def test_change_sink_exceptions_do_not_break_propose() -> None:
    class _BadSink:
        def on_propose(self, p) -> None:  # noqa: ANN001
            raise RuntimeError("boom")

        def on_promote(self, p, s) -> None:  # noqa: ANN001
            raise RuntimeError("boom")

        def on_reject(self, p) -> None:  # noqa: ANN001
            raise RuntimeError("boom")

    layer = GrammarLayer(change_sink=_BadSink())  # type: ignore[arg-type]
    layer.add_snapshot(GrammarSnapshot(language="en", version="v_0", rules={}))
    # 例外を握り潰して propose は成功
    p = layer.propose_change(
        language="en", base_version="v_0", pattern="ed-suffix",
        evidence=UsageEvidence(pattern="ed-suffix", samples=["walked"]),
    )
    assert p.status == GrammarChangeStatus.PROPOSED
    snap = layer.promote(p, new_version="v_1")
    assert snap.version == "v_1"


def test_multilingual_grammar_bootstraps_default_languages() -> None:
    mg = MultilingualGrammar()
    for lang in DEFAULT_LANGUAGES:
        assert mg.latest_version(lang) == "v_0"
    assert sorted(mg.layer.languages()) == sorted(DEFAULT_LANGUAGES)


def test_multilingual_grammar_propose_uses_latest_version() -> None:
    sink = InMemoryGrammarChangeSink()
    mg = MultilingualGrammar(change_sink=sink)
    p = mg.propose(
        "ja", pattern="形容詞", evidence=UsageEvidence(pattern="x", samples=[]),
    )
    assert p.base_version == "v_0"
    snap = mg.promote(p, new_version="v_1")
    assert snap.version == "v_1"
    # 次の propose は v_1 ベース
    p2 = mg.propose(
        "ja", pattern="名詞", evidence=UsageEvidence(pattern="y", samples=[]),
    )
    assert p2.base_version == "v_1"
    # sink にも events が届く
    assert len(sink.proposes) == 2
    assert len(sink.promotes) == 1


def test_multilingual_grammar_rejects_unknown_language() -> None:
    mg = MultilingualGrammar()
    with pytest.raises(KeyError, match="not in bootstrap"):
        mg.propose("xx", pattern="?", evidence=UsageEvidence(pattern="?", samples=[]))


def test_multilingual_grammar_custom_languages() -> None:
    mg = MultilingualGrammar(languages=("ja", "ainu"))
    assert mg.latest_version("ja") == "v_0"
    assert mg.latest_version("ainu") == "v_0"
    with pytest.raises(KeyError):
        mg.propose("en", pattern="?", evidence=UsageEvidence(pattern="?", samples=[]))


def test_multilingual_grammar_reuses_existing_snapshots() -> None:
    layer = _bootstrap_layer()
    # ja は既に v_0 がある状態で MultilingualGrammar に渡す
    mg = MultilingualGrammar(layer=layer)
    # ja の version は v_0 のまま (重複生成しない)
    assert mg.latest_version("ja") == "v_0"
    # 他言語は bootstrap で生成される
    for lang in ("en", "zh", "ko"):
        assert mg.latest_version(lang) == "v_0"


def test_proposed_change_status_transitions() -> None:
    layer = _bootstrap_layer()
    p = layer.propose_change(
        language="ja", base_version="v_0", pattern="x",
        evidence=UsageEvidence(pattern="x", samples=[]),
    )
    assert p.status == GrammarChangeStatus.PROPOSED
    layer.promote(p, new_version="v_1")
    assert p.status == GrammarChangeStatus.PROMOTED
    # 既に promoted の proposal を再昇格しようとするとエラー
    with pytest.raises(ValueError, match="must be PROPOSED"):
        layer.promote(p, new_version="v_2")
