# SPDX-License-Identifier: Apache-2.0
"""Unit tests for llive.benchmark.runtime_metadata (llive v0.A ER-PROC-05)."""

from __future__ import annotations

import os

import pytest

from llive.benchmark.runtime_metadata import (
    collect_runtime_metadata,
    is_valid_for_publication,
    render_disclosure_block,
)


_ALL_KEYS = (
    "llama_cpp_sha",
    "llama_cpp_release_tag",
    "gguf_spec_version",
    "sampler_chain_spec",
    "kv_cache_quantization",
    "model_quant",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """各 test 前に LLIVE_BENCH_* 系 env を強制クリア."""
    for key in (
        "LLIVE_BENCH_LLAMA_CPP_SHA",
        "LLIVE_BENCH_LLAMA_CPP_RELEASE_TAG",
        "LLIVE_BENCH_GGUF_SPEC_VERSION",
        "LLIVE_BENCH_SAMPLER_CHAIN_SPEC",
        "LLIVE_BENCH_KV_CACHE_QUANT",
        "LLIVE_BENCH_MODEL_QUANT",
    ):
        monkeypatch.delenv(key, raising=False)


def test_defaults_all_unknown() -> None:
    md = collect_runtime_metadata()
    for key in _ALL_KEYS:
        assert md[key] == "unknown"


def test_env_overrides_each_field(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLIVE_BENCH_LLAMA_CPP_SHA", "abc1234")
    monkeypatch.setenv("LLIVE_BENCH_LLAMA_CPP_RELEASE_TAG", "b4501")
    monkeypatch.setenv("LLIVE_BENCH_GGUF_SPEC_VERSION", "3")
    monkeypatch.setenv("LLIVE_BENCH_SAMPLER_CHAIN_SPEC", "top_k=40 top_p=0.95")
    monkeypatch.setenv("LLIVE_BENCH_KV_CACHE_QUANT", "q8_0")
    monkeypatch.setenv("LLIVE_BENCH_MODEL_QUANT", "q4_k_m")

    md = collect_runtime_metadata()
    assert md["llama_cpp_sha"] == "abc1234"
    assert md["llama_cpp_release_tag"] == "b4501"
    assert md["gguf_spec_version"] == "3"
    assert md["sampler_chain_spec"] == "top_k=40 top_p=0.95"
    assert md["kv_cache_quantization"] == "q8_0"
    assert md["model_quant"] == "q4_k_m"


def test_empty_string_treated_as_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLIVE_BENCH_LLAMA_CPP_SHA", "   ")
    md = collect_runtime_metadata()
    assert md["llama_cpp_sha"] == "unknown"


def test_is_valid_only_when_all_set(monkeypatch: pytest.MonkeyPatch) -> None:
    md = collect_runtime_metadata()
    assert is_valid_for_publication(md) is False

    # 全 6 set すれば True
    for env_name in (
        "LLIVE_BENCH_LLAMA_CPP_SHA",
        "LLIVE_BENCH_LLAMA_CPP_RELEASE_TAG",
        "LLIVE_BENCH_GGUF_SPEC_VERSION",
        "LLIVE_BENCH_SAMPLER_CHAIN_SPEC",
        "LLIVE_BENCH_KV_CACHE_QUANT",
        "LLIVE_BENCH_MODEL_QUANT",
    ):
        monkeypatch.setenv(env_name, "set")
    md2 = collect_runtime_metadata()
    assert is_valid_for_publication(md2) is True


def test_is_valid_false_when_any_field_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    for env_name in (
        "LLIVE_BENCH_LLAMA_CPP_SHA",
        "LLIVE_BENCH_LLAMA_CPP_RELEASE_TAG",
        "LLIVE_BENCH_GGUF_SPEC_VERSION",
        "LLIVE_BENCH_SAMPLER_CHAIN_SPEC",
        "LLIVE_BENCH_KV_CACHE_QUANT",
        # LLIVE_BENCH_MODEL_QUANT は意図的に未設定
    ):
        monkeypatch.setenv(env_name, "set")
    md = collect_runtime_metadata()
    assert is_valid_for_publication(md) is False
    assert md["model_quant"] == "unknown"


def test_render_disclosure_block_contains_all_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLIVE_BENCH_LLAMA_CPP_SHA", "abc1234")
    md = collect_runtime_metadata()
    block = render_disclosure_block(md)
    assert "## Runtime metadata" in block
    for key in _ALL_KEYS:
        label = key.replace("_", " ")
        assert label in block
    assert "abc1234" in block
