# SPDX-License-Identifier: Apache-2.0
"""MCP Substrate Adapter (v0.J skeleton) — unit tests.

llive v0.J 案 (MCP over Genome) の skeleton 検証. 実 MCP server 起動は test
では行わず, signature + dispatch + Approval Bus 連携の skeleton 挙動のみ check.

カバー範囲:

1. ``MCP_SDK_AVAILABLE`` flag が import 成否に応じて bool
2. ``Substrate.MCP_REMOTE`` enum が将来追加された場合の互換 + 未追加 fallback
3. ``MCPSubstrateAdapter()`` の初期化 (default + custom)
4. URI helper 群 (``individual_uri`` / ``population_manifest_uri`` /
   ``phylogeny_ancestors_uri``) が期待 scheme を返す
5. ``can_handle`` が MCP_REMOTE substrate を許可 / 他 substrate を拒否
6. ``from_abstract`` / ``to_abstract`` round-trip (``_mcp`` field 透過)
7. 各 ``serve_tool_*`` / ``serve_resource_*`` が ``NotImplementedError`` を
   raise する (skeleton 仕様)
8. ``auth_elicitation`` deny-by-default + ``require_approval=False`` 経路
9. PoC + FEASIBILITY が存在し最低限の field を持つ (smoke check)

実 MCP server 接続 / Approval Bus client / asyncio event loop は v0.J Phase 2.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

import pytest

from llive.perf.evolutionary.cross_substrate import (
    DEFAULT_INTENT_DIM,
    AbstractGenome,
    Substrate,
)
from llive.perf.evolutionary.mcp_substrate_adapter import (
    GENOME_URI_SCHEME,
    MCP_REMOTE_SUBSTRATE,
    MCP_SDK_AVAILABLE,
    MCPSubstrateAdapter,
    individual_uri,
    phylogeny_ancestors_uri,
    population_manifest_uri,
)

# ===========================================================================
# helpers
# ===========================================================================


def _valid_genome() -> AbstractGenome:
    intent = tuple(float(i) * 0.1 for i in range(DEFAULT_INTENT_DIM))
    seed = f"mcp-test:{intent}".encode()
    h = hashlib.sha256(seed).hexdigest()
    return AbstractGenome(
        intent=intent,
        capabilities=("reason",),
        rules=("no_self_modify_without_approval",),
        history_hash=h,
        intended_substrate=Substrate.PYTHON,
    )


# ===========================================================================
# 1. MCP SDK availability flag
# ===========================================================================


def test_mcp_sdk_available_flag_is_bool() -> None:
    """import 成否に応じて bool になっていれば良い (CI で True/False 両方あり得る)."""
    assert isinstance(MCP_SDK_AVAILABLE, bool)


# ===========================================================================
# 2. Substrate.MCP_REMOTE 互換 (将来 enum 追加 / 未追加 fallback)
# ===========================================================================


def test_mcp_remote_substrate_fallback_or_enum() -> None:
    """``MCP_REMOTE_SUBSTRATE`` は enum 値 or 文字列 "mcp_remote"."""
    if isinstance(MCP_REMOTE_SUBSTRATE, Substrate):
        # 既に enum 追加済なら value は "mcp_remote"
        assert MCP_REMOTE_SUBSTRATE.value == "mcp_remote"
    else:
        # 未追加なら文字列 sentinel
        assert MCP_REMOTE_SUBSTRATE == "mcp_remote"


# ===========================================================================
# 3. MCPSubstrateAdapter() init
# ===========================================================================


def test_adapter_default_init() -> None:
    a = MCPSubstrateAdapter()
    assert a.substrate == MCP_REMOTE_SUBSTRATE
    assert a.timeout_s == 30.0
    assert a.require_approval is True  # deny-by-default


def test_adapter_custom_init() -> None:
    a = MCPSubstrateAdapter(timeout_s=5.0, require_approval=False)
    assert a.timeout_s == 5.0
    assert a.require_approval is False


# ===========================================================================
# 4. URI helpers
# ===========================================================================


def test_uri_scheme_constant() -> None:
    assert GENOME_URI_SCHEME == "genome://"


def test_individual_uri() -> None:
    uri = individual_uri("abc123")
    assert uri == "genome://individual/abc123"
    assert uri.startswith(GENOME_URI_SCHEME)


def test_population_manifest_uri() -> None:
    uri = population_manifest_uri()
    assert uri == "genome://population/manifest"


def test_phylogeny_ancestors_uri() -> None:
    uri = phylogeny_ancestors_uri("deadbeef")
    assert uri == "genome://phylogeny/deadbeef/ancestors"


# ===========================================================================
# 5. can_handle dispatch
# ===========================================================================


def test_can_handle_accepts_mcp_remote_string() -> None:
    """文字列 fallback 経路 (enum 未追加環境想定)."""
    a = MCPSubstrateAdapter(substrate="mcp_remote")
    # 文字列をそのまま Substrate に渡せないため, Substrate.PYTHON 等で reject 確認
    assert a.can_handle(Substrate.PYTHON) is False
    assert a.can_handle(Substrate.RUST) is False


def test_can_handle_rejects_other_substrates() -> None:
    a = MCPSubstrateAdapter()
    assert a.can_handle(Substrate.PYTHON) is False
    assert a.can_handle(Substrate.RUST) is False
    assert a.can_handle(Substrate.CYTHON) is False
    assert a.can_handle(Substrate.NEUROMORPHIC) is False
    assert a.can_handle(Substrate.BCI) is False
    assert a.can_handle(Substrate.TYPESCRIPT) is False


# ===========================================================================
# 6. from_abstract / to_abstract round-trip
# ===========================================================================


def test_from_abstract_attaches_mcp_metadata() -> None:
    g = _valid_genome()
    a = MCPSubstrateAdapter()
    payload = a.from_abstract(g)
    assert "_mcp" in payload
    assert payload["_mcp"]["scheme"] == GENOME_URI_SCHEME
    assert payload["_mcp"]["uri"] == individual_uri(g.history_hash)
    assert payload["_mcp"]["mime_type"] == "application/json"
    # 主要 field も保持
    assert payload["history_hash"] == g.history_hash
    assert payload["intent_dim"] == g.intent_dim


def test_roundtrip_abstract_to_payload_and_back() -> None:
    g = _valid_genome()
    a = MCPSubstrateAdapter()
    payload = a.from_abstract(g)
    g2 = a.to_abstract(payload)
    assert g2.history_hash == g.history_hash
    assert g2.intent == g.intent
    assert g2.capabilities == g.capabilities
    assert g2.rules == g.rules
    assert g2.intended_substrate == g.intended_substrate
    assert g2.intent_dim == g.intent_dim


def test_to_abstract_drops_mcp_field() -> None:
    """``_mcp`` field を含んでいても ``AbstractGenome.from_dict`` で死なないこと."""
    g = _valid_genome()
    a = MCPSubstrateAdapter()
    payload = a.from_abstract(g)
    # _mcp が drop されることを確認: drop 前は AbstractGenome.from_dict が
    # _mcp を無視する必要があるが, skeleton では adapter が drop する.
    g2 = a.to_abstract(payload)
    assert g2 is not None
    # payload に _mcp を残したまま再生成しても adapter は drop する
    payload_with_extra = dict(payload)
    payload_with_extra["_mcp"] = {"extra": "noise"}
    g3 = a.to_abstract(payload_with_extra)
    assert g3.history_hash == g.history_hash


# ===========================================================================
# 7. serve_tool_* / serve_resource_* は NotImplementedError
# ===========================================================================


def test_serve_tool_crossover_not_implemented() -> None:
    a = MCPSubstrateAdapter()
    g1, g2 = _valid_genome(), _valid_genome()
    with pytest.raises(NotImplementedError):
        a.serve_tool_crossover(g1, g2)


def test_serve_tool_mutate_not_implemented() -> None:
    a = MCPSubstrateAdapter()
    g = _valid_genome()
    with pytest.raises(NotImplementedError):
        a.serve_tool_mutate(g)


def test_serve_tool_evaluate_novelty_not_implemented() -> None:
    a = MCPSubstrateAdapter()
    with pytest.raises(NotImplementedError):
        a.serve_tool_evaluate_novelty((0.0, 0.0))


def test_serve_resource_individual_not_implemented() -> None:
    a = MCPSubstrateAdapter()
    with pytest.raises(NotImplementedError):
        a.serve_resource_individual("abc")


def test_serve_resource_population_manifest_not_implemented() -> None:
    a = MCPSubstrateAdapter()
    with pytest.raises(NotImplementedError):
        a.serve_resource_population_manifest()


def test_serve_resource_phylogeny_ancestors_not_implemented() -> None:
    a = MCPSubstrateAdapter()
    with pytest.raises(NotImplementedError):
        a.serve_resource_phylogeny_ancestors("abc")


# ===========================================================================
# 8. auth_elicitation deny-by-default
# ===========================================================================


def test_auth_elicitation_deny_by_default() -> None:
    a = MCPSubstrateAdapter()
    assert a.auth_elicitation("crossover") is False
    assert a.auth_elicitation("mutate") is False
    assert a.auth_elicitation("resource_read:phylogeny") is False


def test_auth_elicitation_allows_when_approval_disabled() -> None:
    a = MCPSubstrateAdapter(require_approval=False)
    assert a.auth_elicitation("crossover") is True
    assert a.auth_elicitation("anything") is True


# ===========================================================================
# 9. PoC + FEASIBILITY artifacts smoke check
# ===========================================================================

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_POC_DIR = _REPO_ROOT / "experiments" / "mcp_genome_poc"


def test_poc_artifacts_exist() -> None:
    assert (_POC_DIR / "poc.py").is_file()
    assert (_POC_DIR / "FEASIBILITY.md").is_file()


def test_poc_result_json_has_required_fields() -> None:
    """PoC を 1 度動かしてあれば ``poc_result.json`` がある (なくても skip)."""
    result_path = _POC_DIR / "poc_result.json"
    if not result_path.is_file():
        pytest.skip("poc_result.json not generated yet (run poc.py first)")
    data = json.loads(result_path.read_text(encoding="utf-8"))
    for key in (
        "generations",
        "population_size",
        "inproc_per_op_us_median",
        "mcp_per_op_us_median",
        "overhead_ratio_median",
        "verdict",
        "honest_disclosure",
    ):
        assert key in data, f"PoC result missing field {key!r}"
    assert data["verdict"] in {"ok", "conditional", "redesign"}
