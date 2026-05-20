# SPDX-License-Identifier: Apache-2.0
"""Runtime metadata helper for bench output (llive v0.A ER-PROC-05).

bench_*.py / low_spec.py から呼んで, 出力 JSON に **6 種類の runtime metadata**
を必須で差し込めるようにする. これが無い bench は honest_disclosure 上
INVALID とする (llive `docs/requirements_v0.A_external_runtime_tracking.md`).

6 metadata:

* ``llama_cpp_sha``           — commit SHA
* ``llama_cpp_release_tag``   — release tag (例 ``b4501``)
* ``gguf_spec_version``       — GGUF metadata spec version
* ``sampler_chain_spec``      — sampler chain の文字列表現
* ``kv_cache_quantization``   — KV cache quant default (例 ``q8_0``)
* ``model_quant``             — model quant (例 ``q4_k_m``)

Usage:

    from llive.benchmark.runtime_metadata import collect_runtime_metadata

    md = collect_runtime_metadata()
    bench_result["runtime_metadata"] = md
    json.dump(bench_result, fh)

env で上書きできる (CI / 月次レビューで明示的にセットする想定):

    LLIVE_BENCH_LLAMA_CPP_SHA
    LLIVE_BENCH_LLAMA_CPP_RELEASE_TAG
    LLIVE_BENCH_GGUF_SPEC_VERSION
    LLIVE_BENCH_SAMPLER_CHAIN_SPEC
    LLIVE_BENCH_KV_CACHE_QUANT
    LLIVE_BENCH_MODEL_QUANT

env が無い場合は ``"unknown"`` を返す. **bench publish 前に operator が必ず
埋める**.
"""

from __future__ import annotations

import os
from typing import TypedDict


class RuntimeMetadata(TypedDict, total=True):
    """6 metadata の TypedDict. すべて str (JSON 化容易).

    値が未設定の場合は ``"unknown"``. publish 前に operator が埋める.
    """

    llama_cpp_sha: str
    llama_cpp_release_tag: str
    gguf_spec_version: str
    sampler_chain_spec: str
    kv_cache_quantization: str
    model_quant: str


_ENV_MAP: dict[str, str] = {
    "llama_cpp_sha": "LLIVE_BENCH_LLAMA_CPP_SHA",
    "llama_cpp_release_tag": "LLIVE_BENCH_LLAMA_CPP_RELEASE_TAG",
    "gguf_spec_version": "LLIVE_BENCH_GGUF_SPEC_VERSION",
    "sampler_chain_spec": "LLIVE_BENCH_SAMPLER_CHAIN_SPEC",
    "kv_cache_quantization": "LLIVE_BENCH_KV_CACHE_QUANT",
    "model_quant": "LLIVE_BENCH_MODEL_QUANT",
}


def collect_runtime_metadata() -> RuntimeMetadata:
    """Return current runtime metadata (env-driven, defaults to ``"unknown"``).

    bench 出力に必ず差し込むこと.
    """
    result: dict[str, str] = {}
    for key, env_name in _ENV_MAP.items():
        result[key] = os.environ.get(env_name, "unknown").strip() or "unknown"
    return RuntimeMetadata(**result)  # type: ignore[typeddict-item]


def is_valid_for_publication(metadata: RuntimeMetadata) -> bool:
    """Return True iff all 6 fields are non-"unknown".

    Bench 出力を公開する前 ([[feedback-benchmark-honest-disclosure]]) に
    呼び出して False なら publish を **拒否** する.
    """
    return all(metadata[key] != "unknown" for key in _ENV_MAP)


def render_disclosure_block(metadata: RuntimeMetadata) -> str:
    """Markdown ブロックで disclosure 行を返す (bench report 末尾に貼る用).

    例::

        ## Runtime metadata
        - llama.cpp SHA: abc1234
        - llama.cpp release tag: b4501
        - GGUF spec: 3
        - sampler chain: top_k=40 top_p=0.95 ...
        - KV cache quant: q8_0
        - model quant: q4_k_m
    """
    lines = ["## Runtime metadata"]
    for key in _ENV_MAP:
        label = key.replace("_", " ")
        lines.append(f"- {label}: `{metadata[key]}`")
    return "\n".join(lines) + "\n"


__all__ = [
    "RuntimeMetadata",
    "collect_runtime_metadata",
    "is_valid_for_publication",
    "render_disclosure_block",
]
