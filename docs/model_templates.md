# 公開 LLM のひな形 Model データ

> 公開された Decoder-only LLM を ContainerSpec / SubBlockSpec に書き起こし、Phase 1 MVR の起点として利用する。

## 1. 目的

- llive の **BaseModelAdapter** が「既存 LLM をラップする」と謳う FR-01 の **具体的なリファレンス実装**を持つ
- 既存 LLM の **共通骨格と差異**を明示することで、`llive` が抽象化すべきポイントを設計レベルで確定
- 後続 Phase の **構造進化候補生成**（mutation policy）が **学習データ**として活用
- 比較対象として **forgetting / pollution / route entropy** のベースライン取得を可能にする

## 2. テンプレート一覧

| ファイル | モデル | params | 主用途 | 採用理由 |
|---|---|---|---|---|
| [`qwen2_5_7b.yaml`](../specs/templates/qwen2_5_7b.yaml) | Qwen2.5-7B-Instruct | 7B | 多言語 (日中対応) | 日本語精度 |
| [`llama3_1_8b.yaml`](../specs/templates/llama3_1_8b.yaml) | Llama-3.1-8B-Instruct | 8B | 英語標準 | エコシステム |
| [`mistral_7b_v0_3.yaml`](../specs/templates/mistral_7b_v0_3.yaml) | Mistral-7B-Instruct-v0.3 | 7B | function calling | tool 連携 |
| [`phi_3_5_mini.yaml`](../specs/templates/phi_3_5_mini.yaml) | Phi-3.5-mini-instruct | 3.8B | 低 VRAM 高速 | 開発イテレーション |

## 3. 構造比較表

| 項目 | Qwen2.5-7B | Llama-3.1-8B | Mistral-7B-v0.3 | Phi-3.5-mini |
|---|---|---|---|---|
| Layers | 28 | 32 | 32 | 32 |
| Hidden size | 3584 | 4096 | 4096 | 3072 |
| FFN intermediate | 18944 | 14336 | 14336 | 8192 |
| Q / KV heads | 28 / 4 | 32 / 8 | 32 / 8 | 32 / 32 |
| Head dim | 128 | 128 | 128 | 96 |
| Norm | RMSNorm 1e-6 | RMSNorm 1e-5 | RMSNorm 1e-5 | RMSNorm 1e-5 |
| FFN | SwiGLU | SwiGLU | SwiGLU | SwiGLU |
| Position | RoPE θ=1M | RoPE θ=500K + llama3 scaling | RoPE θ=1M | RoPE θ=10K + longrope |
| Max ctx | 32k | 131k | 32k | 131k |
| Vocab | 151643 | 128256 | 32768 | 32064 |
| QKV bias | あり | なし | なし | なし (fused) |
| GQA / MHA | GQA | GQA | GQA | MHA |
| Sliding window | なし | なし | なし (v0.3) | なし |
| FFN intermediate / hidden | 5.29× | 3.50× | 3.50× | 2.67× |

## 4. 共通骨格 (llive が抽象化する対象)

```
1 Transformer block =
  pre_norm
  → attention (causal, RoPE)
  → residual_add
  → pre_norm
  → ffn (SwiGLU)
  → residual_add
```

これが **すべて**のメインストリーム 7B〜8B Decoder-only LLM で共通。差異は sub-block の **config** に閉じ込められる。

## 5. 差異の分類

| 差異カテゴリ | 例 | llive での吸収方法 |
|---|---|---|
| **Hyperparameter** | layer 数 / hidden / FFN size / head 構成 | ContainerSpec の繰り返し数 + SubBlockSpec の config |
| **Position encoding 変種** | RoPE θ / scaling / longrope / NTK | `position` sub-block の config (rope_theta, rope_scaling) |
| **Attention 変種** | MHA / GQA / sliding window / blocksparse | sub-block 型を `multi_head_attention` / `grouped_query_attention` / `sliding_window_attention` に分岐 |
| **Normalization 変種** | RMSNorm / LayerNorm / QK Norm | `pre_norm` config (method, eps, qk_norm) |
| **FFN 変種** | SwiGLU / GeGLU / GeLU+Linear / MoE | sub-block 型を `ffn_swiglu` / `ffn_geglu` / `ffn_gelu_linear` / `moe_ffn` に分岐 |
| **Bias 有無** | QKV bias, FFN bias | config の `bias_q` 等 |
| **Fusion 最適化** | fused QKV, fused gate_up | config `fused_qkv`, `fused_gate_up` (実装ヒント) |
| **Vocab / Tokenizer** | size / BPE / Tiktoken | `BaseModelAdapter` の tokenizer 抽象 |

## 6. 必要となる標準 SubBlockSpec セット

これらをひな形 Model データから逆算して定義（`specs/subblocks/` 配下に配置予定）:

| SubBlock | 必要根拠 |
|---|---|
| `pre_norm` | 全モデル必須 |
| `grouped_query_attention` | Qwen2.5 / Llama3.1 / Mistral |
| `multi_head_attention` | Phi-3.5-mini |
| `sliding_window_attention` | (将来) Mistral v0.1, Gemma |
| `ffn_swiglu` | 全モデル |
| `ffn_geglu` | (将来) PaLM 系, Gemma |
| `moe_ffn` | (将来) Mixtral, DeepSeek-V2 |
| `residual` | 全モデル |
| `rope_position` (attention 内部) | 全モデル |
| `qk_norm` | (将来) Gemma2, Llama3.2-vision |

## 7. llive 拡張点との対応

ひな形 Model データに、llive 固有 sub-block を **`optional_extensions`** として未有効状態で記載。

| 拡張 sub-block | 挿入候補位置 | 関連 FR |
|---|---|---|
| `memory_read` | attention 後 / FFN 前 | FR-05 |
| `cross_memory_attention` | memory_read 直後 | FR-05 |
| `memory_write` | block 末尾 | FR-06, FR-21 |
| `reflective_probe` | N block ごと | FR-04 |
| `compress` | memory_read 直後 | TRIZ #2 |
| `verifier_head` | 出力 head の直前 | FR-13 |
| `adapter` | attention or FFN 後 | FR-03, FR-18 |

## 8. 使い方

### 8.1 ContainerSpec をロードして実行

```python
from llive.container import BlockContainer
from llive.core import CoreModelAdapter

# Step 1: HF weight をロードしつつ、llive 形式の Container でラップ
adapter = CoreModelAdapter.from_template(
    "specs/templates/qwen2_5_7b.yaml",
    weights_source="hf:Qwen/Qwen2.5-7B-Instruct",
)

# Step 2: 推論
out = adapter.generate("こんにちは")
```

### 8.2 拡張 sub-block を有効化して candidate 生成

```python
from llive.evolution import CandidateBuilder

cand = CandidateBuilder.from_template("specs/templates/qwen2_5_7b.yaml")
cand.enable("memory_read", insert_after="self_attn", top_k=8)
cand.enable("memory_write", policy="surprise_gated")
cand.save("candidates/cand_qwen_mem_v1.yaml")
```

### 8.3 構造比較ベンチ

```bash
llive bench compare-templates \
  --templates qwen2_5_7b llama3_1_8b mistral_7b_v0_3 phi_3_5_mini \
  --bench bench/mini \
  --out runs/template_comparison/
```

## 9. ひな形データの検証手順

各テンプレートの正確性は **HF config.json と一致** することで確認できる。検証スクリプト:

```python
# scripts/inspect_hf_model.py
import json
from pathlib import Path
import yaml
from transformers import AutoConfig

MAPPING = {
    "specs/templates/qwen2_5_7b.yaml":    "Qwen/Qwen2.5-7B-Instruct",
    "specs/templates/llama3_1_8b.yaml":   "meta-llama/Meta-Llama-3.1-8B-Instruct",
    "specs/templates/mistral_7b_v0_3.yaml": "mistralai/Mistral-7B-Instruct-v0.3",
    "specs/templates/phi_3_5_mini.yaml":  "microsoft/Phi-3.5-mini-instruct",
}

for tpl, hf_id in MAPPING.items():
    cfg = AutoConfig.from_pretrained(hf_id)
    tmpl = yaml.safe_load(Path(tpl).read_text())
    meta = tmpl["model_metadata"]
    # 主要キーを照合
    assert cfg.num_hidden_layers == meta["num_hidden_layers"], tpl
    assert cfg.hidden_size == meta["hidden_size"], tpl
    assert cfg.intermediate_size == meta["intermediate_size"], tpl
    # ... etc.
    print(f"OK {tpl}")
```

Phase 1 で実装する `BaseModelAdapter` がこの検証を自動化。

## 10. 次に追加すべきテンプレート（候補）

| 候補モデル | 採用理由 | 優先度 |
|---|---|---|
| `mixtral_8x7b.yaml` | MoE 構造の参照 | 中 |
| `gemma2_9b.yaml` | QK Norm の参照 | 中 |
| `deepseek_v2_lite.yaml` | MLA (Multi-head Latent Attention) | 中 |
| `qwen2_5_0_5b.yaml` | unit test 用に小型 | **高** |
| `tinyllama_1_1b.yaml` | CI で回せる小型 | **高** |
| `mamba2_2_7b.yaml` | non-Transformer 比較 | 低 |

特に **小型モデル** (0.5B / 1.1B) は **CI / 開発の高速化** に必須。Phase 1 ではこちらを優先する案を推奨。
