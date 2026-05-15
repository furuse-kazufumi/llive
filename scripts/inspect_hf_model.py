# SPDX-License-Identifier: Apache-2.0
"""Verify llive Model Templates against HuggingFace config.json.

llive のひな形 Model データ (`specs/templates/*.yaml`) が、実際の HF モデルの
config.json と整合していることを確認する。

Phase 1 で `BaseModelAdapter` がこの検証を自動化する前段の手動 / CI 用ツール。

Usage:
    python scripts/inspect_hf_model.py            # all templates
    python scripts/inspect_hf_model.py qwen2_5_7b # one template
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

try:
    from transformers import AutoConfig
except ImportError as e:
    print("ERROR: transformers が必要です。`pip install transformers` してください。", file=sys.stderr)
    raise

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT / "specs" / "templates"

# template basename -> HF model id
MAPPING: dict[str, str] = {
    "qwen2_5_7b":     "Qwen/Qwen2.5-7B-Instruct",
    "llama3_1_8b":    "meta-llama/Meta-Llama-3.1-8B-Instruct",
    "mistral_7b_v0_3": "mistralai/Mistral-7B-Instruct-v0.3",
    "phi_3_5_mini":   "microsoft/Phi-3.5-mini-instruct",
}

# template の model_metadata と AutoConfig の attribute 名の対応
ATTR_MAP: dict[str, str] = {
    "num_hidden_layers":        "num_hidden_layers",
    "hidden_size":              "hidden_size",
    "intermediate_size":        "intermediate_size",
    "num_attention_heads":      "num_attention_heads",
    "num_key_value_heads":      "num_key_value_heads",
    "max_position_embeddings":  "max_position_embeddings",
    "vocab_size":               "vocab_size",
    "tie_word_embeddings":      "tie_word_embeddings",
    "rope_theta":               "rope_theta",
    "norm_eps":                 "rms_norm_eps",
}


def verify_template(template_path: Path, hf_id: str) -> list[str]:
    """Returns list of mismatch messages. Empty list = OK."""
    template = yaml.safe_load(template_path.read_text(encoding="utf-8"))
    meta = template.get("model_metadata", {})
    cfg = AutoConfig.from_pretrained(hf_id, trust_remote_code=True)

    mismatches: list[str] = []
    for tmpl_key, cfg_key in ATTR_MAP.items():
        if tmpl_key not in meta:
            continue
        actual = getattr(cfg, cfg_key, None)
        expected = meta[tmpl_key]
        if actual is None:
            mismatches.append(f"  - {tmpl_key}: cfg has no `{cfg_key}` attr")
            continue
        if actual != expected:
            mismatches.append(f"  - {tmpl_key}: template={expected!r} vs cfg={actual!r}")
    return mismatches


def main(argv: list[str]) -> int:
    targets = argv[1:] or list(MAPPING.keys())
    fail = 0
    for name in targets:
        hf_id = MAPPING.get(name)
        if hf_id is None:
            print(f"[SKIP] unknown template: {name}")
            continue
        path = TEMPLATES_DIR / f"{name}.yaml"
        if not path.exists():
            print(f"[FAIL] template file missing: {path}")
            fail += 1
            continue
        try:
            mm = verify_template(path, hf_id)
        except Exception as e:
            print(f"[ERR ] {name}: {e}")
            fail += 1
            continue
        if mm:
            print(f"[FAIL] {name} ({hf_id})")
            for m in mm:
                print(m)
            fail += 1
        else:
            print(f"[OK  ] {name} ({hf_id})")
    return fail


if __name__ == "__main__":
    sys.exit(main(sys.argv))
