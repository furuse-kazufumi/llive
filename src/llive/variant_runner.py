# SPDX-License-Identifier: Apache-2.0
"""llive variant_runner — v0.C Phase 2 subprocess 起動先 skeleton.

Usage::

    py -3.11 -m llive.variant_runner \\
        --config-json /tmp/llive-variants/<id>/config.json \\
        --output-json /tmp/llive-variants/<id>/result.json \\
        [--prompts-json /tmp/llive-variants/<id>/prompts.json] \\
        [--max-wallclock 300]

責務:

1. config.json (LlivVariantConfig.to_dict 互換) を読む
2. mock or 実 LlivKernel で評価する
3. result.json (FitnessReport の dict 化 + 追加 metadata) を書く

実 LlivKernel spawn は credential / 環境準備後. 現状は **mock baseline**
で shape を確定し, Phase 2 で実装を差し替える.

設計判断:
- 単発 subprocess なので global state を気にしなくて良い
- timeout は呼び出し元 (PromptfooRunner 等の subprocess.run) が握る. ここでは
  --max-wallclock を hint として受け取るだけ (内部 timer はオプション).
- 失敗時は exit code != 0 + stderr に friendly error. result.json は
  書かない or partial.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from llive.benchmark.runtime_metadata import collect_runtime_metadata
from llive.perf.evolutionary.individual import FitnessReport
from llive.perf.evolutionary.llive_variant import (
    LIVE_VARIANT_GENOME_BOUNDS,
    LIVE_VARIANT_GENOME_LABELS,
    LlivVariantBuilder,
    LlivVariantConfig,
    mock_variant_fitness_factory,
)
from llive.perf.evolutionary.genome import Genome


def load_variant_config(path: Path) -> LlivVariantConfig:
    """config.json を LlivVariantConfig に復元.

    入力 schema (Phase 2 interface spec §2.2):

    ```json
    {
      "variant_id": "...",
      "data_dir": "...",
      "thought_factor_weights": {...},
      "memory_thresholds": {...},
      "backend_name": "mamba",
      "sampler": {"temperature": ..., "top_p": ..., "kv_quant": "q8_0"},
      "proactive": {"gift_value_threshold": ..., "cooldown_minutes": ...}
    }
    ```
    """
    data: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    return LlivVariantConfig(
        thought_factor_weights=dict(data["thought_factor_weights"]),
        memory_thresholds=dict(data["memory_thresholds"]),
        backend_name=str(data["backend_name"]),
        sampler=dict(data["sampler"]),
        proactive=dict(data["proactive"]),
        variant_id=str(data.get("variant_id", "")),
        data_dir=str(data.get("data_dir", "")),
    )


def config_to_genome(config: LlivVariantConfig) -> Genome:
    """LlivVariantConfig → Genome 逆変換 (mock fitness 再評価用).

    Phase 2 で実 LlivKernel を spawn する際, この経路を経由しないでも config
    を直接渡せるが, mock 評価との parity 確認のために用意する.
    """
    factor_values = [
        config.thought_factor_weights[label] for label in LIVE_VARIANT_GENOME_LABELS[:10]
    ]
    memory_values = [
        config.memory_thresholds["semantic_threshold"],
        config.memory_thresholds["episodic_threshold"],
        config.memory_thresholds["structural_decay"],
    ]
    backend_ids = {"mock": 0.0, "openai": 1.0, "anthropic": 2.0, "mamba": 3.0, "rwkv": 4.0}
    kv_ids = {"f16": 0.0, "q8_0": 1.0, "q4_0": 2.0}
    backend_value = backend_ids.get(config.backend_name, 0.0)
    sampler_values = [
        float(config.sampler.get("temperature", 0.7)),
        float(config.sampler.get("top_p", 0.95)),
        kv_ids.get(config.sampler.get("kv_quant", "f16"), 0.0),
    ]
    proactive_values = [
        float(config.proactive.get("gift_value_threshold", 0.6)),
        float(config.proactive.get("cooldown_minutes", 30.0)),
    ]
    all_values = (
        factor_values
        + memory_values
        + [backend_value]
        + sampler_values
        + proactive_values
    )
    return Genome.from_values(
        all_values,
        bounds=LIVE_VARIANT_GENOME_BOUNDS,
        labels=LIVE_VARIANT_GENOME_LABELS,
    )


def evaluate_variant(
    config: LlivVariantConfig,
    *,
    transport: str = "mock",
) -> dict[str, Any]:
    """1 派生を評価する main entry.

    Parameters
    ----------
    config : LlivVariantConfig
    transport : str
        ``"mock"`` (default, credential 不要) or ``"in_process"``
        (Phase 2 で実装, LlivKernel が必要).

    Returns
    -------
    dict
        result.json に書き出される dict. Phase 2 interface spec §2.2 準拠.
    """
    start = time.perf_counter()
    if transport == "mock":
        genome = config_to_genome(config)
        fitness_fn = mock_variant_fitness_factory()
        report: FitnessReport = fitness_fn(genome)
    elif transport == "in_process":
        # Phase 2 で実装: from llive.kernel import LlivKernel
        # kernel = LlivKernel.from_variant_config(config)
        # report = kernel.run_eval_briefs(STANDARD_PROMPTS).to_fitness_report()
        raise NotImplementedError(
            "transport='in_process' is reserved for Phase 2 (実 LlivKernel spawn)"
        )
    else:
        raise ValueError(f"unknown transport: {transport!r}")
    elapsed = time.perf_counter() - start

    return {
        "variant_id": config.variant_id,
        "transport": transport,
        "score": report.score,
        "breakdown": dict(report.breakdown),
        "runtime_metadata": dict(report.runtime_metadata or collect_runtime_metadata()),
        "n_samples": report.n_samples,
        "notes": report.notes,
        "elapsed_seconds": float(elapsed),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="llive.variant_runner")
    parser.add_argument("--config-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--prompts-json", type=Path, default=None,
                        help="standard prompts (Phase 2 で使用)")
    parser.add_argument("--max-wallclock", type=float, default=None,
                        help="呼び出し元の subprocess.run timeout に従う想定. hint only.")
    parser.add_argument("--transport", default="mock", choices=["mock", "in_process"])
    args = parser.parse_args(argv)

    try:
        config = load_variant_config(args.config_json)
        result = evaluate_variant(config, transport=args.transport)
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return 0
    except FileNotFoundError as e:
        print(f"variant_runner: input not found: {e}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"variant_runner: invalid config.json: {e}", file=sys.stderr)
        return 3
    except NotImplementedError as e:
        print(f"variant_runner: {e}", file=sys.stderr)
        return 4
    except Exception:
        print("variant_runner: unexpected error:", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
