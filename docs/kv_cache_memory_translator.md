# KV cache Memory Translator (Phase C-1.4)

> Gemini #2 ブレスト (2026-05-22) 発の差別化機能.
> Closed LLM (Anthropic / OpenAI) では絶対できない FullSense 固有の hack.
> 関連 memory: [[project_idea_kv_cache_memory_translator]]
> 関連 loop task: `20260522T130259-45384b`

## 概要

llive 4 層メモリ (semantic / episodic / structural / parameter) を
**テキスト化せず embedding として LLM の `inputs_embeds` に直接注入**
する経路. トークン経済の外側で memory を LLM に届ける.

## Stage 構成

| Stage | 経路 | 状態 (2026-05-23) | 担当 commit |
|---|---|---|---|
| **Stage 1** | Embedding 結合 (`inputs_embeds`) | ✅ **完成 (skeleton + tests)** | f3c03de / d320bc4 / 9aecf2a / (155d2ef + 821059e auto) |
| Stage 1.5 | transformers/torch install + Qwen2.5-0.5B 実 smoke | ⏳ **持ち越し** (heavy deps + 1GB weights) | — |
| Stage 2 | llama.cpp / Ollama KV cache delta inject | ⏳ **未着手** | — |
| Stage 3 | Self-attention head 操作 (Mechanistic Interpretability) | ⏳ **将来** | — |

## Stage 1 — 完成内容

### API surface

```python
from llive.llm import GenerateRequest, MockBackend, HFTransformersBackend

req = GenerateRequest(
    prompt="What was the last decision about the deploy?",
    prefix_embeddings=[
        ("mem_episodic_42", numpy_vec_768d),    # 1 メモリエントリ
        ("mem_semantic_17", numpy_vec_768d),
    ],
)
# Mock: count を返すだけ (test 用)
print(MockBackend().generate(req).text)
# → "[mock] What was the last decision... (with 2 prefix embeddings)"

# HF: 実 LLM に inputs_embeds として注入 (transformers + torch 必要)
backend = HFTransformersBackend(model="Qwen/Qwen2.5-0.5B-Instruct")
resp = backend.generate(req)  # → 実生成テキスト
```

### 追加された API 要素

| 要素 | 場所 | 用途 |
|---|---|---|
| `GenerateRequest.prefix_embeddings: list[PrefixEmbedding]` | `src/llive/llm/backend.py` | `(label, vector)` ペアのリスト. label は observability 用. vector は backend hidden_dim と一致が必要 |
| `LLMBackend.supports_prefix_embeddings -> bool` | 同上 | default False (closed LLM 継承元). 各 backend で override |
| `MockBackend.supports_prefix_embeddings = True` | 同上 | test double 用. count + labels を raw に出す |
| `HFTransformersBackend` | 同上 | 唯一 inputs_embeds に直接注入できる Open LLM 経路. lazy import (transformers/torch) |
| `resolve_backend("hf"\|"huggingface")` | 同上 | env / 引数で HFTransformersBackend を選択 |
| `LLIVE_HF_MODEL` env | 同上 | DEFAULT_MODEL (`Qwen/Qwen2.5-0.5B-Instruct`) を上書き |
| `LLIVE_HF_DEVICE` env | 同上 | `cpu` (default) / `cuda` / `mps` |
| `LLIVE_HF_DTYPE` env | 同上 | `float32` (default) / `float16` / `bfloat16` |

### 修正された bug

- `_delegate_generate` (`backend.py:577`) が `prefix_embeddings` / `audio` /
  `sensor` を wrap GenerateRequest に伝播していなかった
  (`d320bc4`). Mamba/RWKV/Jamba/Diffusion 経由で Stage 1 が動かなかった.

### Fail-closed 設計

CLAUDE.md MCP 規約 (fail-closed default) に従い:

- 未 install (transformers / torch) → `HFTransformersBackend()` で明示
  `ModuleNotFoundError` (silently fallback しない)
- `prefix_embeddings[i]` の dim が model の `hidden_size` と不一致 →
  `ValueError` で reject (silently misinterpret しない)
- 1D / 2D 以外の ndim → `ValueError`

## Stage 1.5 — 持ち越し (実モデル smoke)

実装:

```bash
pip install 'llmesh-llive[hf]'  # transformers + torch を pull
python -c "
from llive.llm import GenerateRequest, HFTransformersBackend
import numpy as np
b = HFTransformersBackend('Qwen/Qwen2.5-0.5B-Instruct')
H = b.model.get_input_embeddings().embedding_dim  # 896 for Qwen2.5-0.5B
mem = np.random.randn(H).astype('float32')
r = b.generate(GenerateRequest(
    prompt='Continue: The mystery deepened when',
    max_tokens=40,
    prefix_embeddings=[('rand_mem_1', mem)],
))
print(r.text)
print('hidden_size:', r.raw['hidden_size'])
"
```

検証ポイント:
- prefix なし vs prefix あり で出力が**有意に変わる**こと
- ランダム vec と意味ある実 vec で出力差があること
- dim mismatch で確実に ValueError が出ること

honest disclosure ([[feedback_benchmark_honest_disclosure]]):
- 実モデル smoke 未実施 — heavy dep install + 1GB weights download を
  本セッションで実行しなかった
- inputs_embeds path は decoder-only model の入力扱いが
  input_ids path と微妙に違う (BOS 自動付与なし等) — 実 smoke で確認すべき

## Stage 2 — 未着手 (KV cache delta inject)

llama.cpp / Ollama の `past_key_values` を Rust kernel で生成 → backend
側で `past_key_values = prev + delta` で受け取り.

技術的課題:
- Ollama REST API は `past_key_values` を expose しない → llama.cpp C API
  直叩き or `llama-cpp-python` (low-level binding) が必要
- KV cache の形状 (層数 × head 数 × seq_len × head_dim) は model 依存 →
  動的 reshape ロジック

実装案 (将来):
1. `LlamaCppDirectBackend` (新規) — `llama-cpp-python` 経由で `model.eval`
   API を呼び `past_key_values` を取得・差し戻し
2. `GenerateRequest.past_key_values_delta: dict[str, Tensor] | None` 追加

## Stage 3 — 将来 (Self-attention head 操作)

Mechanistic Interpretability 系研究を参考に、特定 head に memory graph を
"固定" する. Anthropic の research model 等を参考.

現時点では研究フロンティアであり, 安定 API なし.

## 関連

- [[project_idea_kv_cache_memory_translator]] — 元アイデア (Gemini #2)
- [[project_fullsense_ear_origin]] — local LLM 内側を制御できることが強み
- [[project_llive_neuro_long_term]] — 脳-AI 直結インタフェース構想と整合
- [[project_idea_speculative_mesh_execution]] — llmesh 間で KV cache 共有
- `docs/non-transformer/ROADMAP.md` — Phase C-1.x の上位 milestone

## Test 一覧 (Stage 1)

```
tests/unit/test_llm_backend.py:
  test_mock_backend_accepts_prefix_embeddings
  test_mock_backend_single_prefix_embedding_singular
  test_mock_backend_empty_prefix_embeddings_omits_raw
  test_mock_backend_supports_prefix_embeddings_flag
  test_default_backend_does_not_support_prefix_embeddings
  test_hf_backend_raises_when_deps_missing
  test_hf_backend_supports_prefix_embeddings_flag
  test_resolve_backend_dispatches_hf_alias
  test_hf_backend_model_env_override
  test_hf_backend_rejects_dim_mismatch

tests/unit/test_non_transformer_backends.py:
  test_delegate_generate_propagates_prefix_embeddings  # bug regression
```

実行: `D:\projects\llive\.venv\Scripts\python.exe -m pytest tests/unit/test_llm_backend.py tests/unit/test_non_transformer_backends.py -v`
