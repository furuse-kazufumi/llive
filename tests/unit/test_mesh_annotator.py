# SPDX-License-Identifier: Apache-2.0
"""COG-MESH-10 完成配線テスト — Mesh5W1HAnnotator ↔ AnnotationEmitter."""

from __future__ import annotations

from llive.annotations import AnnotationEmitter
from llive.cognitive_mesh.mesh_5w1h import Granularity, Mesh5W1HNode, channel_name
from llive.cognitive_mesh.mesh_annotator import Mesh5W1HAnnotator


def test_emit_from_text_populates_all_detected_channels() -> None:
    annotator = Mesh5W1HAnnotator()
    text = "Why did Alice go there today? Because she needed to."
    result = annotator.emit_from_text(text)

    bundle = annotator.freeze()
    namespaces = {a.namespace for a in bundle.items}

    # WHO ("alice" not in keyword list, but "I "/"you" 等 → 検出されない)
    # WHY ("why", "because" 検出)
    # WHEN ("today" 検出)
    # WHERE ("there" 検出)
    assert channel_name(Mesh5W1HNode.WHY) in namespaces
    assert channel_name(Mesh5W1HNode.WHEN) in namespaces
    assert channel_name(Mesh5W1HNode.WHERE) in namespaces
    # 全文 granularity 注釈は必ず 1 件入る
    assert "mesh.granularity" in namespaces
    # raw result も返ってくる
    assert "why" in result[Mesh5W1HNode.WHY]
    assert "because" in result[Mesh5W1HNode.WHY]


def test_emit_from_text_target_layer_default_llove() -> None:
    annotator = Mesh5W1HAnnotator()
    annotator.emit_from_text("when is today?")
    bundle = annotator.freeze()
    for a in bundle.items:
        assert a.target_layer == "llove"


def test_emit_from_text_custom_target_layer() -> None:
    annotator = Mesh5W1HAnnotator(target_layer="llmesh")
    annotator.emit_from_text("when is today?")
    bundle = annotator.freeze()
    for a in bundle.items:
        assert a.target_layer == "llmesh"


def test_emit_from_text_no_keywords_emits_only_granularity() -> None:
    annotator = Mesh5W1HAnnotator()
    annotator.emit_from_text("xyzzy plugh")
    bundle = annotator.freeze()
    namespaces = [a.namespace for a in bundle.items]
    # 5W1H namespace は無く、granularity のみ
    assert namespaces == ["mesh.granularity"]


def test_emit_node_targets_specific_channel() -> None:
    annotator = Mesh5W1HAnnotator()
    annotator.emit_node(Mesh5W1HNode.WHEN, "iso", "2026-05-19T07:00:00")
    bundle = annotator.freeze()
    assert len(bundle.items) == 1
    a = bundle.items[0]
    assert a.namespace == "mesh.when"
    assert a.key == "iso"
    assert a.value == "2026-05-19T07:00:00"


def test_emit_granularity_records_token_class() -> None:
    annotator = Mesh5W1HAnnotator()
    g = annotator.emit_granularity("short")
    assert g == Granularity.WORD
    bundle = annotator.freeze()
    assert any(a.namespace == "mesh.granularity" for a in bundle.items)
    granular = [a for a in bundle.items if a.namespace == "mesh.granularity"]
    assert granular[0].value == {"token": "short", "granularity": "word"}


def test_emitter_injection_reuses_external_buffer() -> None:
    """外部 emitter を注入すると同じ buffer に書き込まれる."""
    external = AnnotationEmitter()
    external.add(namespace="other", key="x", value=1)
    annotator = Mesh5W1HAnnotator(emitter=external)
    annotator.emit_from_text("why now?")
    bundle = external.freeze()
    namespaces = [a.namespace for a in bundle.items]
    # 元の other annotation も残り、5W1H も加わる
    assert "other" in namespaces
    assert "mesh.why" in namespaces
