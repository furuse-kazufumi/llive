# SPDX-License-Identifier: Apache-2.0
"""variant_runner — Phase 2 subprocess 起動先の単体テスト."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from llive.perf.evolutionary import (
    Genome,
    LIVE_VARIANT_GENOME_BOUNDS,
    LIVE_VARIANT_GENOME_LABELS,
    LlivVariantBuilder,
)
from llive.variant_runner import (
    config_to_genome,
    evaluate_variant,
    load_variant_config,
    main,
)


def _make_config_json(tmp_path: Path) -> Path:
    rng = np.random.default_rng(0)
    genome = Genome.random(LIVE_VARIANT_GENOME_BOUNDS, rng, labels=LIVE_VARIANT_GENOME_LABELS)
    cfg = LlivVariantBuilder().build_config(genome, variant_id="vtest123")
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg.to_dict(), ensure_ascii=False), encoding="utf-8")
    return path


def test_load_variant_config_roundtrip(tmp_path: Path) -> None:
    cfg_path = _make_config_json(tmp_path)
    cfg = load_variant_config(cfg_path)
    assert cfg.variant_id == "vtest123"
    assert len(cfg.thought_factor_weights) == 10
    assert cfg.backend_name in ("mock", "openai", "anthropic", "mamba", "rwkv")


def test_config_to_genome_roundtrip_preserves_factor_weights() -> None:
    rng = np.random.default_rng(1)
    original = Genome.random(LIVE_VARIANT_GENOME_BOUNDS, rng, labels=LIVE_VARIANT_GENOME_LABELS)
    cfg = LlivVariantBuilder().build_config(original, variant_id="r1")
    restored = config_to_genome(cfg)
    # 思考因子 (10 dim) は厳密に一致するはず
    for i in range(10):
        assert restored.values[i] == pytest.approx(original.values[i], abs=1e-6)
    # backend_id は離散化される (4.99 → 4 → "rwkv" → 4.0)
    # なので原値とは可逆ではない部分があるので check しない


def test_evaluate_variant_mock_returns_full_result(tmp_path: Path) -> None:
    cfg_path = _make_config_json(tmp_path)
    cfg = load_variant_config(cfg_path)
    result = evaluate_variant(cfg, transport="mock")
    assert result["variant_id"] == "vtest123"
    assert result["transport"] == "mock"
    assert 0.0 <= result["score"] <= 1.0
    for key in (
        "latency_ms", "quality", "stability", "safety", "honesty",
        "factor_coverage", "memory_efficiency", "proactive_balance",
    ):
        assert key in result["breakdown"]
    # 6 runtime metadata SHA
    for key in (
        "llama_cpp_sha", "llama_cpp_release_tag", "gguf_spec_version",
        "sampler_chain_spec", "kv_cache_quantization", "model_quant",
    ):
        assert key in result["runtime_metadata"]
    assert result["elapsed_seconds"] >= 0.0


def test_evaluate_variant_in_process_not_implemented(tmp_path: Path) -> None:
    cfg_path = _make_config_json(tmp_path)
    cfg = load_variant_config(cfg_path)
    with pytest.raises(NotImplementedError):
        evaluate_variant(cfg, transport="in_process")


def test_evaluate_variant_unknown_transport(tmp_path: Path) -> None:
    cfg_path = _make_config_json(tmp_path)
    cfg = load_variant_config(cfg_path)
    with pytest.raises(ValueError):
        evaluate_variant(cfg, transport="quantum")


def test_main_writes_result_json(tmp_path: Path) -> None:
    cfg_path = _make_config_json(tmp_path)
    out_path = tmp_path / "result.json"
    code = main(["--config-json", str(cfg_path), "--output-json", str(out_path)])
    assert code == 0
    assert out_path.exists()
    result = json.loads(out_path.read_text(encoding="utf-8"))
    assert "score" in result
    assert "breakdown" in result


def test_main_returns_2_when_config_missing(tmp_path: Path) -> None:
    out_path = tmp_path / "result.json"
    code = main(["--config-json", str(tmp_path / "nope.json"), "--output-json", str(out_path)])
    assert code == 2


def test_main_returns_3_when_config_malformed(tmp_path: Path) -> None:
    bad_cfg = tmp_path / "bad.json"
    bad_cfg.write_text("not json {{{", encoding="utf-8")
    out_path = tmp_path / "result.json"
    code = main(["--config-json", str(bad_cfg), "--output-json", str(out_path)])
    assert code == 3
