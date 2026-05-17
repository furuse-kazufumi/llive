# SPDX-License-Identifier: Apache-2.0
"""IND-04 — Annotation channel for cross-layer additive composition.

llive 単体で価値を出しつつ、llove / llmesh / 別 agent が「居れば付加価値を出せる」
ためのヒントを構造化メタデータとして emit する仕組み。

設計の核:

* :class:`Annotation` — 1 つのヒント (namespace + key + value + target_layer)
* :class:`AnnotationBundle` — Annotation の immutable コレクション
* :class:`AnnotationEmitter` — emit-side 助走 (component 内で使う簡易ビルダー)

emit-side は consumer を知らず、consumer-side は emit を強制しない。両方とも
optional で、片方が居なくても動作不変。

JSON-friendly のみ (value は str/int/float/bool/None/list/dict)。MCP/HTTP に
そのまま流せる。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator, Mapping


# Closed-ish namespace registry — namespace 文字列は自由だが、合意済 prefix を
# ここに列挙して衝突防止。未登録 namespace でも動くが warning 推奨。
KNOWN_NAMESPACES: tuple[str, ...] = (
    "core",     # llive 全体共通 (renderable, replay_id, etc.)
    "vrb",      # PromptLint / Premortem / EvalSpec / Render
    "oka",      # Essence / Notebook / Orchestrator / Explanation / InsightScore
    "cog",      # COG-01〜04 (uncertainty triple / governance / trace_graph / perspectives)
    "math",     # MathVerifier / constants / units / calculator
    "creat",    # KJ / MindMap / Synectics / Structurize / SixHats
    "sec",      # SEC-03 hash chain
    "eval",     # 外部評価系
)


def _check_json_friendly(value: Any) -> None:
    """Best-effort guard — JSON-friendly でない値は raise。"""
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, (list, tuple)):
        for v in value:
            _check_json_friendly(v)
        return
    if isinstance(value, Mapping):
        for k, v in value.items():
            if not isinstance(k, str):
                raise TypeError(f"annotation map keys must be str, got {type(k).__name__}")
            _check_json_friendly(v)
        return
    raise TypeError(
        f"annotation value must be JSON-friendly (str/int/float/bool/None/list/dict), "
        f"got {type(value).__name__}"
    )


@dataclass(frozen=True)
class Annotation:
    """1 件のクロスレイヤヒント.

    Examples:
        Annotation(namespace="vrb", key="lint_score", value=0.8, target_layer="llove")
        Annotation(namespace="cog", key="consensus", value="proceed")  # any consumer
        Annotation(namespace="oka", key="essence_card", value={"summary": "..."}, target_layer="llove")
    """

    namespace: str
    key: str
    value: Any = None
    target_layer: str | None = None  # "llove" / "llmesh" / "agent" / None=any

    def __post_init__(self) -> None:
        if not self.namespace:
            raise ValueError("namespace must be non-empty")
        if not self.key:
            raise ValueError("key must be non-empty")
        _check_json_friendly(self.value)
        if self.target_layer is not None and not isinstance(self.target_layer, str):
            raise TypeError("target_layer must be str or None")

    def to_payload(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "key": self.key,
            "value": self.value,
            "target_layer": self.target_layer,
        }


@dataclass(frozen=True)
class AnnotationBundle:
    """Immutable collection of :class:`Annotation` objects.

    Designed to live inside response dataclasses (BriefResult, CoreEssence, ...).
    Consumers filter via :meth:`for_layer` / :meth:`by_namespace` / :meth:`get`.
    """

    items: tuple[Annotation, ...] = ()

    def __iter__(self) -> Iterator[Annotation]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    @classmethod
    def empty(cls) -> "AnnotationBundle":
        return cls()

    @classmethod
    def of(cls, *annotations: Annotation) -> "AnnotationBundle":
        return cls(items=tuple(annotations))

    def for_layer(self, layer: str) -> "AnnotationBundle":
        """Return annotations targeted at ``layer`` or ``None`` (any)."""
        return AnnotationBundle(items=tuple(
            a for a in self.items if a.target_layer in (layer, None)
        ))

    def by_namespace(self, namespace: str) -> "AnnotationBundle":
        return AnnotationBundle(items=tuple(a for a in self.items if a.namespace == namespace))

    def get(self, namespace: str, key: str, default: Any = None) -> Any:
        for a in self.items:
            if a.namespace == namespace and a.key == key:
                return a.value
        return default

    def to_payload(self) -> list[dict[str, Any]]:
        return [a.to_payload() for a in self.items]

    def merged_with(self, other: "AnnotationBundle | Iterable[Annotation]") -> "AnnotationBundle":
        """Return a new bundle = self.items + other."""
        if isinstance(other, AnnotationBundle):
            extra = other.items
        else:
            extra = tuple(other)
        return AnnotationBundle(items=self.items + extra)

    def to_html_comments(self, *, prefix: str = "llive") -> str:
        """Render the bundle as HTML/Markdown comments — invisible when rendered.

        Designed for the "邪魔にならない" requirement (2026-05-17): embedding
        these into a Markdown/HTML output yields zero visible artefacts in a
        renderer (browser, Markdown viewer), yet a consumer that parses the
        raw text can recover the annotations deterministically.

        Format::

            <!-- {prefix}:{namespace}.{key}={json_value} target={layer} -->

        Multiple comments are joined with ``\\n``. Empty bundle returns ``""``.
        """
        import json
        lines: list[str] = []
        for a in self.items:
            value_str = json.dumps(a.value, ensure_ascii=False, sort_keys=True)
            target = f" target={a.target_layer}" if a.target_layer else ""
            lines.append(
                f"<!-- {prefix}:{a.namespace}.{a.key}={value_str}{target} -->"
            )
        return "\n".join(lines)

    @classmethod
    def from_html_comments(cls, text: str, *, prefix: str = "llive") -> "AnnotationBundle":
        """Parse :meth:`to_html_comments` output back into a bundle.

        Lines that don't match the expected format are skipped silently —
        consumers shouldn't blow up on hand-edited Markdown.
        """
        import json
        import re

        pattern = re.compile(
            r"<!--\s*"
            + re.escape(prefix)
            + r":([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)=(.+?)(?:\s+target=([A-Za-z0-9_]+))?\s*-->"
        )
        items: list[Annotation] = []
        for m in pattern.finditer(text):
            ns, key, raw_value, target = m.groups()
            try:
                value = json.loads(raw_value)
            except json.JSONDecodeError:
                continue
            items.append(Annotation(
                namespace=ns, key=key, value=value, target_layer=target,
            ))
        return cls(items=tuple(items))


class AnnotationEmitter:
    """Mutable builder used inside emit-side components.

    component 内で `.add(...)` を繰り返して、最後に :meth:`freeze` で
    immutable :class:`AnnotationBundle` を取り出す。
    """

    def __init__(self) -> None:
        self._buf: list[Annotation] = []

    def add(
        self,
        namespace: str,
        key: str,
        value: Any = None,
        *,
        target_layer: str | None = None,
    ) -> "AnnotationEmitter":
        self._buf.append(Annotation(
            namespace=namespace, key=key, value=value, target_layer=target_layer,
        ))
        return self

    def extend(self, annotations: Iterable[Annotation]) -> "AnnotationEmitter":
        self._buf.extend(annotations)
        return self

    def freeze(self) -> AnnotationBundle:
        return AnnotationBundle(items=tuple(self._buf))


__all__ = [
    "Annotation",
    "AnnotationBundle",
    "AnnotationEmitter",
    "KNOWN_NAMESPACES",
]
