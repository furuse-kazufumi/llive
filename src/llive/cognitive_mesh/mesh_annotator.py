# SPDX-License-Identifier: Apache-2.0
"""COG-MESH-10 完成配線 — Mesh5W1H → Annotation Channel.

requirements_v0.8_cognitive_mesh.md §3 COG-MESH-10 で予告した
「Annotation Channel と統合」を行う adapter。

設計:
- ``annotate_5w1h(text)`` の戻り値 (5W1H ごとのキーワード dict) を
  AnnotationEmitter に流す。
- namespace = ``channel_name(node)`` (例: ``"mesh.who"``)。
- key = ``"keywords"`` (拡張時に ``"granularity"`` などを足す)。
- target_layer は ``"llove"`` をデフォルト (TUI 側 5W1H パネル想定)。
- emitter を外部から注入できる: 既存 BriefRunner の annotation 経路に
  そのまま流す用途。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from llive.annotations import AnnotationBundle, AnnotationEmitter
from llive.cognitive_mesh.mesh_5w1h import (
    Granularity,
    Mesh5W1HNode,
    annotate_5w1h,
    channel_name,
    granularity_of,
)


@dataclass
class Mesh5W1HAnnotator:
    """5W1H メッシュ解析結果を AnnotationEmitter に流す adapter.

    Attributes:
        target_layer: annotation の target_layer フィールド既定値.
            ``"llove"`` で TUI 側 5W1H パネルに到達する想定.
        emitter: 注入済 AnnotationEmitter (None なら新規生成).
    """

    target_layer: str = "llove"
    emitter: AnnotationEmitter = field(default_factory=AnnotationEmitter)

    def emit_from_text(self, text: str) -> dict[Mesh5W1HNode, list[str]]:
        """テキストを 5W1H 解析し、各 node の channel に annotation を追加.

        Returns:
            ``annotate_5w1h(text)`` の生結果 (caller が graph 構築等に使える形).
        """
        result = annotate_5w1h(text)
        for node, keywords in result.items():
            if not keywords:
                continue
            self.emitter.add(
                namespace=channel_name(node),
                key="keywords",
                value=list(keywords),
                target_layer=self.target_layer,
            )
        # 全文の粒度ヒントも一緒に流す (consumer 側で UI 階層化に使える)
        self.emitter.add(
            namespace="mesh.granularity",
            key="text",
            value=granularity_of(text).value,
            target_layer=self.target_layer,
        )
        return result

    def emit_node(self, node: Mesh5W1HNode, key: str, value: Any) -> None:
        """特定 5W1H node の channel に任意 (key, value) を流す.

        例: ``annotator.emit_node(Mesh5W1HNode.WHEN, "iso", "2026-05-19T07:00:00")``
        """
        self.emitter.add(
            namespace=channel_name(node),
            key=key,
            value=value,
            target_layer=self.target_layer,
        )

    def emit_granularity(self, token: str) -> Granularity:
        """token を粒度推定し annotation 化. Returns: 推定 Granularity."""
        g = granularity_of(token)
        self.emitter.add(
            namespace="mesh.granularity",
            key="token",
            value={"token": token, "granularity": g.value},
            target_layer=self.target_layer,
        )
        return g

    def freeze(self) -> AnnotationBundle:
        """internal emitter を freeze して immutable bundle を返す."""
        return self.emitter.freeze()


__all__ = ["Mesh5W1HAnnotator"]
