"""TLB — Thought Layer Bridging.

思考層が増えたときの指数膨張対策。Bridge (高 confidence 層 short-circuit)
+ Coordinator (aggregate score で早期 termination) + ManifoldCache (semantic
hash で過去組合せ memo) の 3 部品で O(N^k) を O(N^{k-b}) に降下させる。
"""

from llive.fullsense.bridges.coordinator import (
    GlobalCoordinator,
    LayerScore,
)
from llive.fullsense.bridges.manifold_cache import ManifoldCache
from llive.fullsense.bridges.registry import Bridge, BridgeRegistry

__all__ = [
    "Bridge",
    "BridgeRegistry",
    "GlobalCoordinator",
    "LayerScore",
    "ManifoldCache",
]
