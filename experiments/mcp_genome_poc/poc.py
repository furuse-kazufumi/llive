#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""v0.J PoC — MCP over Genome の最小フィジビリティ検証.

ユーザー指摘 (2026-05-22 深夜):
    「ゲノムが MCP を介して相互に連結されるような構造は優位性がありますかね?」

主要 Claude 側分析の結論:
    層 1 (inner loop, in-process crossover) は MCP 不要 (RTT 重すぎ).
    層 2 (cross-substrate 越境) / 層 3 (governance) / 層 4 (phylogeny discovery)
    は MCP 適切 — JSON-RPC + Approval Bus 統合 + 別 process 隔離が活きる.

本 PoC の目的:
    上記「層 2-4 限定なら許容できる」仮説を **実測 timing で検証** する.
    内側ループ (in-process crossover, dict-only) と MCP 越し crossover
    (同一 process / asyncio loop / JSON-RPC round-trip) を 50 世代 × 10 個体
    で比較し, overhead 比 (× factor) を出す.

判定基準 (実測前の hypothesis):
    1. 内側 / MCP 比 < 100x: 層 2-4 用途に許容
    2. 100x <= 比 < 1000x: 条件付き (バッチ化 or 越境のみ)
    3. 比 >= 1000x or MCP server crash: 設計やり直し or 別 transport (stdio/sse)

実装メモ:
    - MCP SDK は anthropic `mcp` (公式) を使用. なければ ImportError を honest
      report. SSE/stdio transport は PoC では使わず, **in-memory JSON-RPC
      mock** で round-trip コストを下限見積りする (SDK 仕様不適合のリスクは
      FEASIBILITY.md に honest 記載).
    - PoC は CI で動かない (mcp sdk が optional). 単独 run 前提.

Run:
    py -3.11 experiments/mcp_genome_poc/poc.py

Output:
    - stdout: 内側 / MCP の timing + ratio
    - experiments/mcp_genome_poc/poc_result.json
    - experiments/mcp_genome_poc/FEASIBILITY.md (本スクリプトでは生成しない;
      手動で feasibility 判定を残す)

References:
    - llive [[project_idea_predictive_verification]] — Z3/TLA+ 前段ゲート
    - feedback_benchmark_honest_disclosure — 異常に速い / 遅い結果は内訳を疑う
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import pathlib
import random
import statistics
import sys
import time
from typing import Any

# llive を import path に追加
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from llive.perf.evolutionary.cross_substrate import (  # noqa: E402
    AbstractGenome,
    Substrate,
)

# ---------------------------------------------------------------------------
# Optional MCP SDK (honest disclosure: 無くても本 PoC は動く)
# ---------------------------------------------------------------------------

try:
    import mcp  # type: ignore

    _MCP_AVAILABLE = True
    _MCP_PATH = mcp.__file__
except ImportError:  # pragma: no cover - PoC 実環境ガード
    mcp = None  # type: ignore
    _MCP_AVAILABLE = False
    _MCP_PATH = None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_genome(seed_int: int) -> AbstractGenome:
    """deterministic 個体生成 (PoC 用)."""
    rng = random.Random(seed_int)
    intent = tuple(rng.uniform(-1.0, 1.0) for _ in range(16))
    seed_bytes = f"poc:{seed_int}:{intent}".encode()
    return AbstractGenome(
        intent=intent,
        capabilities=("reason", "plan"),
        rules=("no_self_modify_without_approval",),
        history_hash=hashlib.sha256(seed_bytes).hexdigest(),
        intended_substrate=Substrate.PYTHON,
    )


def _crossover_inproc(a: AbstractGenome, b: AbstractGenome) -> AbstractGenome:
    """層 1 想定の in-process crossover (dict 直接).

    AbstractGenome を frozen dataclass のまま blend する. JSON 経路を通さない
    ため, MCP 越し版と timing 差を作る基準線になる.
    """
    new_intent = tuple((x + y) * 0.5 for x, y in zip(a.intent, b.intent, strict=True))
    new_caps = tuple(sorted(set(a.capabilities) | set(b.capabilities)))
    new_rules = tuple(sorted(set(a.rules) | set(b.rules)))
    # parent hash chain
    seed = f"x:{a.history_hash}:{b.history_hash}:{new_intent}".encode()
    new_hash = hashlib.sha256(seed).hexdigest()
    return AbstractGenome(
        intent=new_intent,
        capabilities=new_caps,
        rules=new_rules,
        history_hash=new_hash,
        intended_substrate=a.intended_substrate,
        intent_dim=a.intent_dim,
    )


# ---------------------------------------------------------------------------
# MCP-style transport mock (in-memory JSON-RPC)
# ---------------------------------------------------------------------------


class _InMemoryJsonRpcTransport:
    """JSON-RPC over in-memory queue を mock.

    実 MCP SDK の stdio/sse transport は subprocess + pipe / asyncio + httpx で
    更に重い. ここでは **下限見積り** として serialize + deserialize + dict
    dispatch のみ実測. 実 transport は本 mock の 10-100x 重いと想定.
    """

    def __init__(self, handlers: dict[str, Any]) -> None:
        self._handlers = handlers
        self._req_id = 0

    def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._req_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._req_id,
            "method": method,
            "params": params,
        }
        # serialize -> wire -> deserialize (mock の核)
        wire = json.dumps(request).encode("utf-8")
        decoded = json.loads(wire.decode("utf-8"))
        handler = self._handlers[decoded["method"]]
        result = handler(decoded["params"])
        # response も serialize 経由
        response = {"jsonrpc": "2.0", "id": decoded["id"], "result": result}
        wire2 = json.dumps(response).encode("utf-8")
        return json.loads(wire2.decode("utf-8"))


def _crossover_mcp(
    transport: _InMemoryJsonRpcTransport,
    a: AbstractGenome,
    b: AbstractGenome,
) -> AbstractGenome:
    """層 2 想定の MCP 越し crossover (JSON-RPC mock)."""
    params = {
        "parent_a": a.to_dict(),
        "parent_b": b.to_dict(),
    }
    response = transport.call("genome/crossover", params)
    return AbstractGenome.from_dict(response["result"])


def _server_handler_crossover(params: dict[str, Any]) -> dict[str, Any]:
    """MCP server 側 handler 想定. JSON dict in/out."""
    a = AbstractGenome.from_dict(params["parent_a"])
    b = AbstractGenome.from_dict(params["parent_b"])
    child = _crossover_inproc(a, b)
    return child.to_dict()


# ---------------------------------------------------------------------------
# PoC main
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class PocResult:
    generations: int
    population_size: int
    inproc_total_s: float
    inproc_per_op_us: float
    mcp_total_s: float
    mcp_per_op_us: float
    overhead_ratio: float
    mcp_sdk_available: bool
    mcp_sdk_path: str | None
    verdict: str  # "ok" / "conditional" / "redesign"


def run_poc(generations: int = 50, population_size: int = 10) -> PocResult:
    """50 世代 × 10 個体で 2 経路の timing 比較."""
    rng = random.Random(0)
    population = [_make_genome(i) for i in range(population_size)]

    # ----- 内側ループ (in-proc) -----
    t0 = time.perf_counter()
    inproc_count = 0
    for _g in range(generations):
        next_gen: list[AbstractGenome] = []
        for _i in range(population_size):
            a, b = rng.sample(population, 2)
            child = _crossover_inproc(a, b)
            next_gen.append(child)
            inproc_count += 1
        population = next_gen
    t_inproc = time.perf_counter() - t0

    # ----- MCP 越し (in-memory transport mock) -----
    rng_mcp = random.Random(0)
    population_mcp = [_make_genome(i) for i in range(population_size)]
    transport = _InMemoryJsonRpcTransport(
        handlers={"genome/crossover": _server_handler_crossover}
    )
    t1 = time.perf_counter()
    mcp_count = 0
    for _g in range(generations):
        next_gen = []
        for _i in range(population_size):
            a, b = rng_mcp.sample(population_mcp, 2)
            child = _crossover_mcp(transport, a, b)
            next_gen.append(child)
            mcp_count += 1
        population_mcp = next_gen
    t_mcp = time.perf_counter() - t1

    inproc_per_us = (t_inproc / inproc_count) * 1e6
    mcp_per_us = (t_mcp / mcp_count) * 1e6
    ratio = t_mcp / t_inproc if t_inproc > 0 else float("inf")

    if ratio < 100:
        verdict = "ok"
    elif ratio < 1000:
        verdict = "conditional"
    else:
        verdict = "redesign"

    return PocResult(
        generations=generations,
        population_size=population_size,
        inproc_total_s=t_inproc,
        inproc_per_op_us=inproc_per_us,
        mcp_total_s=t_mcp,
        mcp_per_op_us=mcp_per_us,
        overhead_ratio=ratio,
        mcp_sdk_available=_MCP_AVAILABLE,
        mcp_sdk_path=_MCP_PATH,
        verdict=verdict,
    )


def main() -> int:
    print(f"[poc] mcp sdk available: {_MCP_AVAILABLE} ({_MCP_PATH})")

    # 3 回測って中央値 (warm-up + GC ノイズ緩和)
    results: list[PocResult] = []
    for trial in range(3):
        r = run_poc(generations=50, population_size=10)
        results.append(r)
        print(
            f"[poc] trial={trial} inproc={r.inproc_per_op_us:.2f}us "
            f"mcp={r.mcp_per_op_us:.2f}us ratio={r.overhead_ratio:.1f}x"
        )

    median_ratio = statistics.median(r.overhead_ratio for r in results)
    median_inproc = statistics.median(r.inproc_per_op_us for r in results)
    median_mcp = statistics.median(r.mcp_per_op_us for r in results)

    if median_ratio < 100:
        verdict = "ok"
    elif median_ratio < 1000:
        verdict = "conditional"
    else:
        verdict = "redesign"

    summary = {
        "generations": 50,
        "population_size": 10,
        "trials": 3,
        "inproc_per_op_us_median": median_inproc,
        "mcp_per_op_us_median": median_mcp,
        "overhead_ratio_median": median_ratio,
        "verdict": verdict,
        "mcp_sdk_available": _MCP_AVAILABLE,
        "mcp_sdk_path": _MCP_PATH,
        "trials_raw": [dataclasses.asdict(r) for r in results],
        "honest_disclosure": [
            "in-memory JSON-RPC mock (not real MCP stdio/sse transport)",
            "real MCP transport is 10-100x heavier (subprocess pipe / asyncio httpx)",
            "ratio here is LOWER BOUND of actual MCP overhead",
        ],
    }
    out = pathlib.Path(__file__).parent / "poc_result.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[poc] median ratio={median_ratio:.1f}x verdict={verdict}")
    print(f"[poc] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
