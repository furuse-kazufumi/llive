"""Bridge registry — 短絡ルール (high-confidence で他層 skip).

各 Bridge は ``(LayerName, predicate, skip_layers)`` を持ち、predicate が
True を返したら次の skip_layers を実際に実行せずに通す。これにより
O(N^k) → O(N^{k-b}) を実現する。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

# A bridge predicate: 現在の layer 結果 (任意の dict) を見て発火するか判定
BridgePredicate = Callable[[dict[str, object]], bool]


@dataclass
class Bridge:
    """1 つの bridge ルール."""

    name: str
    """この bridge の識別子."""

    trigger_layer: str
    """この layer の結果を見て発火判定する."""

    predicate: BridgePredicate
    """layer 結果に対する判定関数."""

    skip_layers: tuple[str, ...] = ()
    """発火時にスキップする後続 layer 名."""


@dataclass
class BridgeRegistry:
    """複数 bridge をまとめて適用する."""

    bridges: list[Bridge] = field(default_factory=list)

    def register(self, b: Bridge) -> None:
        self.bridges.append(b)

    def skipped_layers_for(
        self, trigger_layer: str, layer_result: dict[str, object]
    ) -> set[str]:
        """ある layer の結果を渡されて、発火した bridge から得た skip 集合を返す."""
        out: set[str] = set()
        for b in self.bridges:
            if b.trigger_layer != trigger_layer:
                continue
            try:
                if b.predicate(layer_result):
                    out.update(b.skip_layers)
            except Exception:
                # bridge predicate の例外で coordinator を殺さない
                continue
        return out


__all__ = ["Bridge", "BridgePredicate", "BridgeRegistry"]
