# SPDX-License-Identifier: Apache-2.0
"""MCP over Genome — :class:`MCPSubstrateAdapter` (llive v0.J skeleton).

llive v0.J — ゲノムを **MCP (Model Context Protocol) tool / resource として**
expose し, 越境 crossover / mutation / phylogeny 読み出しを JSON-RPC 経由で
行う skeleton. PoC + フィジビリティ判定で **条件付き OK** だった層 2-4
(cross-substrate 越境 / governance / phylogeny discovery) **のみ** をカバー
する. 層 1 (inner loop) は本 adapter を使わず, 既存 dataclass 直接で実装.

PoC 参照:
    - ``experiments/mcp_genome_poc/poc.py``
    - ``experiments/mcp_genome_poc/FEASIBILITY.md``

判定結果:
    - mock 経由 overhead = 6.7x (実 transport は 10-100x 重い honest disclosure)
    - 層 1 で使わず, 層 2-4 限定なら許容
    - Approval Bus 統合 / timeout / batch 化を **必須** とする

形式化 (要件 v0.J §A):

```python
class MCPSubstrateAdapter:
    substrate = Substrate.MCP_REMOTE  # 新規 enum (cross_substrate.py 側で追加)

    # MCP tools
    serve_tool_crossover(parent_a, parent_b) -> AbstractGenome
    serve_tool_mutate(individual) -> AbstractGenome
    serve_tool_evaluate_novelty(descriptor) -> float

    # MCP resources
    serve_resource_individual(id) -> bytes           # genome://individual/<id>
    serve_resource_population_manifest() -> bytes    # genome://population/manifest
    serve_resource_phylogeny_ancestors(id) -> bytes  # genome://phylogeny/<id>/ancestors

    # Approval Bus / Frozen Ethics 連携
    auth_elicitation(action) -> bool                 # MCP elicitation flow
```

設計方針:

- **Optional mcp SDK** — ``import mcp`` 失敗時も module は load 成功. SDK 接続
  本体は将来 (v0.J Phase 2 以降). 本 skeleton は **signature のみ確定**.
- **層 1 で呼ばれない** — :class:`SubstrateAdapter` Protocol の
  ``from_abstract`` / ``to_abstract`` / ``can_handle`` は層 2 越境用. 層 1
  の inner crossover は :mod:`llive.perf.evolutionary.cross_substrate` の
  dataclass 直接で行う (本 adapter は dispatch されない).
- **Approval Bus 統合の skeleton** — :meth:`auth_elicitation` は default で
  ``False`` を返す deny-by-default. 接続は将来 ApprovalBus client 経由.
- **Substrate.MCP_REMOTE** — 並列実装中の Agent と file 衝突を避けるため
  本 skeleton では ``Substrate`` enum への追加は **本ファイル外** で行う想定.
  本 file は ``getattr(Substrate, "MCP_REMOTE", None)`` で fallback 取得し,
  未追加でも import 落ちしない. 後続 commit で ``cross_substrate.py`` に
  enum 追加された後, 本 file の挙動が自動的に enum 整合となる.

References:

- llive ``experiments/mcp_genome_poc/FEASIBILITY.md`` — 8 項目判定で「条件付き OK」
- llive ``docs/requirements_v0.I_meta_evolution_and_cross_substrate.md`` §7
  (cross-substrate) — 本 adapter は §7 の MCP_REMOTE 拡張
- llive ``src/llive/perf/evolutionary/phylogeny.py`` (commit d00f499) —
  ``serve_resource_phylogeny_ancestors`` の back-end
- llive ``src/llive/perf/evolutionary/frozen_gene.py`` (commit 0875e58) —
  ``auth_elicitation`` の rules 評価
- Anthropic MCP spec — https://modelcontextprotocol.io/ (tool / resource /
  elicitation flow)

Status (2026-05-22 着地): skeleton only. 実 MCP server start / asyncio
event loop / Approval Bus client 接続 / batch RPC は将来.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from llive.perf.evolutionary.cross_substrate import (
    AbstractGenome,
    Substrate,
)

# ---------------------------------------------------------------------------
# Optional MCP SDK (skeleton では import 失敗を許容)
# ---------------------------------------------------------------------------

try:  # pragma: no cover - optional dep
    import mcp as _mcp_sdk  # type: ignore

    MCP_SDK_AVAILABLE: bool = True
except ImportError:  # pragma: no cover - skeleton fallback
    _mcp_sdk = None  # type: ignore
    MCP_SDK_AVAILABLE = False


# ---------------------------------------------------------------------------
# Substrate.MCP_REMOTE — 並列 file 編集と競合しない参照経路
# ---------------------------------------------------------------------------

#: ``Substrate.MCP_REMOTE`` の enum 値. ``cross_substrate.py`` 側で enum 追加
#: された場合は実 enum を, 未追加なら文字列 sentinel ``"mcp_remote"`` を返す.
#: 本 skeleton は **enum 未追加でも import 落ちしない** ことを保証する.
MCP_REMOTE_SUBSTRATE: Substrate | str = getattr(Substrate, "MCP_REMOTE", "mcp_remote")


# ---------------------------------------------------------------------------
# MCP resource URI scheme
# ---------------------------------------------------------------------------

#: MCP resource URI prefix. v0.J で確定した URI scheme.
GENOME_URI_SCHEME: str = "genome://"


def individual_uri(individual_id: str) -> str:
    """``genome://individual/<id>`` URI を組み立てる."""
    return f"{GENOME_URI_SCHEME}individual/{individual_id}"


def population_manifest_uri() -> str:
    """``genome://population/manifest`` URI を返す."""
    return f"{GENOME_URI_SCHEME}population/manifest"


def phylogeny_ancestors_uri(individual_id: str) -> str:
    """``genome://phylogeny/<id>/ancestors`` URI を組み立てる."""
    return f"{GENOME_URI_SCHEME}phylogeny/{individual_id}/ancestors"


# ---------------------------------------------------------------------------
# MCPSubstrateAdapter
# ---------------------------------------------------------------------------


@dataclass
class MCPSubstrateAdapter:
    """MCP over Genome — 個体を MCP server として expose する skeleton adapter.

    層 2 (cross-substrate 越境) + 層 3 (governance / approval) +
    層 4 (phylogeny discovery 読み出し) **専用**.

    層 1 (inner loop, in-process crossover) は本 adapter を **dispatch しない** —
    `Substrate.PYTHON` / `Substrate.RUST` 等の既存 adapter が直接処理する.

    本 skeleton は signature のみ確定. 実 MCP server start / asyncio /
    Approval Bus client 接続は将来 (v0.J Phase 2 以降). PoC + FEASIBILITY
    でフィジビリティ確認済.

    Attributes:
        substrate: この adapter が担当する substrate (``MCP_REMOTE``).
        timeout_s: 全 tool 呼出の default timeout (秒). FEASIBILITY.md 必須項目.
        require_approval: True の場合, 全 tool 呼出前に :meth:`auth_elicitation`
            が True を返さなければ deny. default True (deny-by-default).
    """

    substrate: Substrate | str = field(default_factory=lambda: MCP_REMOTE_SUBSTRATE)
    timeout_s: float = 30.0
    require_approval: bool = True

    # ----- SubstrateAdapter Protocol (layer 2 cross-substrate) -----------

    def from_abstract(self, g: AbstractGenome) -> dict[str, Any]:
        """abstract → MCP resource payload (JSON 化可能 dict).

        skeleton: ``AbstractGenome.to_dict()`` をそのまま返す. 将来 MCP の
        ``Resource`` 型 (mimeType=application/json + uri) で wrap する.
        """
        payload = g.to_dict()
        payload["_mcp"] = {
            "scheme": GENOME_URI_SCHEME,
            "uri": individual_uri(g.history_hash),
            "mime_type": "application/json",
        }
        return payload

    def to_abstract(self, phenotype: dict[str, Any]) -> AbstractGenome:
        """MCP payload → AbstractGenome (skeleton, ``_mcp`` field は drop)."""
        data = {k: v for k, v in phenotype.items() if k != "_mcp"}
        return AbstractGenome.from_dict(data)

    def can_handle(self, intended: Substrate) -> bool:
        """``intended`` が MCP_REMOTE substrate であれば True.

        skeleton: 文字列比較 fallback あり (enum 未追加でも動作).
        """
        target = intended.value if isinstance(intended, Substrate) else str(intended)
        own = (
            self.substrate.value
            if isinstance(self.substrate, Substrate)
            else str(self.substrate)
        )
        return target == own

    # ----- MCP tools (skeleton signatures) -------------------------------

    def serve_tool_crossover(
        self,
        parent_a: AbstractGenome,
        parent_b: AbstractGenome,
    ) -> AbstractGenome:
        """MCP tool ``genome/crossover`` — 越境 crossover.

        skeleton: ``NotImplementedError``. 実 MCP server 側 handler は将来.
        layer 2 でのみ呼ばれる前提 (layer 1 は dataclass 直接).
        """
        raise NotImplementedError(
            "MCPSubstrateAdapter.serve_tool_crossover is a skeleton — "
            "wire real MCP server in v0.J Phase 2 (asyncio + Approval Bus)"
        )

    def serve_tool_mutate(self, individual: AbstractGenome) -> AbstractGenome:
        """MCP tool ``genome/mutate`` — 越境 mutation.

        skeleton: ``NotImplementedError``.
        """
        raise NotImplementedError(
            "MCPSubstrateAdapter.serve_tool_mutate is a skeleton — "
            "wire real MCP server in v0.J Phase 2"
        )

    def serve_tool_evaluate_novelty(
        self,
        descriptor: tuple[float, ...],
    ) -> float:
        """MCP tool ``genome/evaluate_novelty`` — 越境 novelty score.

        skeleton: ``NotImplementedError``. 実装は :class:`NoveltyScorer` を
        裏で呼ぶ予定.
        """
        raise NotImplementedError(
            "MCPSubstrateAdapter.serve_tool_evaluate_novelty is a skeleton — "
            "wire real MCP server in v0.J Phase 2"
        )

    # ----- MCP resources (skeleton signatures) ---------------------------

    def serve_resource_individual(self, id_: str) -> bytes:
        """MCP resource ``genome://individual/<id>`` — 個体 1 体の content-addressable 読み出し.

        skeleton: ``NotImplementedError``. 実装は :class:`PhyTree` から取得予定.
        """
        raise NotImplementedError(
            "MCPSubstrateAdapter.serve_resource_individual is a skeleton — "
            f"would fetch {individual_uri(id_)} from PhyTree in v0.J Phase 2"
        )

    def serve_resource_population_manifest(self) -> bytes:
        """MCP resource ``genome://population/manifest`` — 現世代 manifest.

        skeleton: ``NotImplementedError``.
        """
        raise NotImplementedError(
            "MCPSubstrateAdapter.serve_resource_population_manifest is a "
            "skeleton — wire to Population in v0.J Phase 2"
        )

    def serve_resource_phylogeny_ancestors(self, id_: str) -> bytes:
        """MCP resource ``genome://phylogeny/<id>/ancestors`` — 祖先 DAG 読み出し.

        skeleton: ``NotImplementedError``. 実装は :class:`PhyTree` の ancestors
        traversal を呼ぶ予定.
        """
        raise NotImplementedError(
            "MCPSubstrateAdapter.serve_resource_phylogeny_ancestors is a "
            f"skeleton — would traverse PhyTree from {phylogeny_ancestors_uri(id_)} "
            "in v0.J Phase 2"
        )

    # ----- Approval Bus / Frozen Ethics 連携 -----------------------------

    def auth_elicitation(self, action: str) -> bool:
        """MCP elicitation flow — tool 呼出 / mutation 前の Approval Bus 照会.

        skeleton: **deny-by-default**. ``require_approval=True`` (default) の
        場合は常に False を返す. ``require_approval=False`` (テスト / dry-run
        のみ想定) なら True.

        v0.J Phase 2 で実 ApprovalBus client (gRPC or in-proc queue) に接続.
        frozen_gene の rules を MCP resource として expose し, 監査可能性を
        確保する.

        Args:
            action: 照会対象 action 識別子 (例: ``"crossover"``, ``"mutate"``,
                ``"resource_read:phylogeny"``)
        Returns:
            True = approved, False = denied (skeleton では常に False unless
            require_approval=False)
        """
        if not self.require_approval:
            return True
        # skeleton: deny-by-default. 実 ApprovalBus 接続は将来.
        return False


__all__ = [
    "GENOME_URI_SCHEME",
    "MCP_REMOTE_SUBSTRATE",
    "MCP_SDK_AVAILABLE",
    "MCPSubstrateAdapter",
    "individual_uri",
    "phylogeny_ancestors_uri",
    "population_manifest_uri",
]
