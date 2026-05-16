# Proposal — CABT-01: Reference-based Attention with Metadata

> **Status:** design draft (2026-05-17). スパイラル S2 で試作予定。
> **依存:** CABT-01 は S1 (BriefGrounder, 実装済) の次段。
> **動機:** ユーザー指示「マトリクスの値ベース並べ替えを参照ベースに置換し、付加情報を持たせる」を Transformer attention に適用。

## Why

現状の attention は `softmax(QK^T/√d) · V` で **V 行列の値そのもの** を重み付き加算する。これだと:

1. **付加情報を持たせる場所がない** — V は実数 [batch, seq, hidden] のテンソル。各 token に provenance / trust_score / epistemic_type / timestamp を貼り付けるには列を追加する必要があるが、softmax は実数前提でメタ情報を破壊する
2. **参照不能** — どの token をどれだけ参照したかは attention weights に出るが、参照先 token の **由来** までは追跡不能
3. **llive 既存資産との断絶** — `memory/provenance.py` / Quarantined Memory / Ed25519 Signed Adapter は token に紐付かない

**提案**: attention の対象を「値の混合」ではなく「参照 (pointer) の選択 + metadata 集約」に置換。設計パターン: **Mediator** (TRIZ 24) + **Bridge** (GoF) + **Provenance** (DDD)。

## Non-goals

- 完全な model 重み再学習 (LoRA 以上) — S2 では **forward hook で挙動だけ** 注入
- attention 自体の数学的置換 (Mamba / Hyena) — それは別の研究
- 動的な KV cache 形式変更 — 既存 KV cache はそのまま、bias 加算のみ

## Architecture

```
[Input tokens]
   │ (token_id, metadata)
   ▼
[HFAdapter._model]                  ← 既存 (重み凍結)
   │
   ├─ Embedding layer
   │
   ├─ TransformerBlock 0
   │    │
   │    ├─ self_attn  ←─── forward_hook (CABT-01) registered here
   │    │    │
   │    │    └─ output: attn_output
   │    │       ↓ hook 経由で metadata bias 加算
   │    │       attn_output' = attn_output + α · metadata_bias
   │    │
   │    └─ mlp
   │
   ├─ ... (N layers)
   │
   ▼
[LM head → token]
```

### Hook 仕様

```python
# src/llive/cabt/hooks.py
from __future__ import annotations

import torch
from typing import Callable, Sequence

class ReferenceAttentionHook:
    """forward post-hook for Llama-family attention modules.

    HF Llama / Qwen2 系の ``LlamaAttention.forward`` の戻り値は
    ``(attn_output, attn_weights, past_key_value)``。本 hook は ``attn_output``
    に metadata bias を加算する。
    """

    def __init__(
        self,
        metadata_provider: Callable[[torch.Tensor], torch.Tensor],
        *,
        strength: float = 0.1,
        layer_filter: Sequence[int] | None = None,
    ) -> None:
        self._provider = metadata_provider
        self._strength = float(strength)
        self._layer_filter = set(layer_filter or [])
        self._handles: list[torch.utils.hooks.RemovableHandle] = []

    def attach(self, model: torch.nn.Module) -> None:
        for i, layer in enumerate(_iter_transformer_blocks(model)):
            if self._layer_filter and i not in self._layer_filter:
                continue
            attn = getattr(layer, "self_attn", None) or getattr(layer, "attention", None)
            if attn is None:
                continue
            handle = attn.register_forward_hook(self._on_attention)
            self._handles.append(handle)

    def detach(self) -> None:
        for h in self._handles:
            h.remove()
        self._handles.clear()

    def _on_attention(self, module, inputs, outputs):
        attn_output = outputs[0]  # [batch, seq, hidden]
        bias = self._provider(attn_output)  # [batch, seq, hidden]
        if bias.shape != attn_output.shape:
            return outputs  # silent fail-safe
        return (attn_output + self._strength * bias, *outputs[1:])
```

### Metadata column

各 token に **6 列の metadata** を持たせる:

| 列 | 値域 | 由来 |
|---|---|---|
| `provenance_id` | int | `memory/provenance.py` のレコード ID |
| `trust_score` | float [0, 1] | Quarantined Memory Zone の trust 値 |
| `epistemic_type` | int (0-9) | `EpistemicType` enum (FACTUAL=0, ..., RESERVED_5=9) |
| `timestamp_norm` | float [0, 1] | 入力 token の時系列正規化 |
| `source_domain_id` | int | RAD 49 分野の ID |
| `surprise_score` | float [0, 1] | `BayesianSurpriseGate.compute_surprise` 出力 |

これは `[batch, seq, 6]` の整数/実数テンソルとして hidden_states と並走。`metadata_provider(attn_output)` は metadata から `[batch, seq, hidden]` の bias を生成する小 MLP (CABT-01 では random init or identity)。

### llive 思考層との接続点

- **Salience-gated** (CABT-04): `surprise_score` 列で `strength` を per-token に動的化
- **Stage-aware** (CABT-02): `epistemic_type` 列で stage 切替
- **TRIZ-conditioned** (CABT-05): TRIZ citation を `source_domain_id` 経由で hook に伝達
- **Approval-gated** (CABT-06): `trust_score` 列が閾値以下の token は bias を逆方向に (推論抑制)
- **Memory-augmented** (CABT-07): `provenance_id` 経由で 4 層メモリ embedding を bias に注入

## Test plan (S2)

1. **Unit (CPU only)**:
   - `tests/unit/test_cabt_hooks.py` — `nn.Linear` の dummy module に hook を attach/detach、bias が加算されることを確認
   - metadata_provider が shape 不一致を返したら fail-safe で原 output を返す
   - `strength=0.0` なら attn_output が変化しない

2. **Smoke (要 torch + 小型モデル, opt-in)**:
   - Tiny Llama / Qwen2.5-0.5B に hook を attach
   - 同 prompt で hook 有/無の出力を比較、確率的に異なる token 列が出ることを確認 (バグでない動作)

3. **Benchmark (Brief API 経由)**:
   - Brief API + grounder=BriefGrounder() + HFAdapter + hook の経路で進む
   - `docs/benchmarks/2026-05-17-cabt01-prototype/` に matrix.json
   - 観察ポイント: thought_chars / 出力 token の TRIZ 原理引用率 / RAD doc citation 率

## Risk register (スパイラル評価軸)

| Risk | 確率 | 影響 | 緩和 |
|---|---|---|---|
| HF Llama の forward 戻り値が version で変わる | 中 | 中 | `transformers>=4.40` を pin、戻り値 tuple サイズチェック |
| metadata_provider の shape mismatch | 高 | 低 | fail-safe で原 output を返す設計 |
| Hook が GPU メモリを過剰消費 | 中 | 中 | layer_filter で N 層に限定 |
| LoRA 学習が必要になる (品質維持) | 高 | 高 | S2 は random init OK、S3 で LoRA 検討 |
| Approval Bus 同期が hot path で遅延 | 中 | 高 | CABT-06 は decoding 時のみ起動、attention 内では非同期 |

## Effort estimate

| Step | Effort |
|---|---|
| Hook skeleton + CPU mock テスト | 0.5 day |
| HFAdapter `attach_hook(...)` 統合 | 0.5 day |
| Smoke test (tiny model, opt-in) | 0.5 day |
| Brief API 経由ベンチランナー | 0.5 day |
| Document + measurement matrix | 0.5 day |
| **Total** | **~2.5 days for S2 deliverable** |

## Out of scope (parked for S3+)

- `epistemic_type` per-token tagging の自動推論 (S3 = CABT-03)
- 動的 `strength` (surprise gate 同期, S3 = CABT-04)
- LoRA 学習 ループ (要 GPU, 別 Phase)
- Soft-MoE stage router (S4 = CABT-02)

## 関連先行研究 (S2 着手前に RAD で当てる)

- **Pointer Networks** (Vinyals et al., 2015)
- **Memorizing Transformers** (Wu et al., ICLR 2022)
- **RETRO** (Borgeaud et al., DeepMind 2022)
- **kNN-LM** (Khandelwal et al., 2020)
- **MoE for attention** (Zoph et al., 2022)
- **Hyena Operator** (Poli et al., 2023)
- **Mamba** (Gu & Dao, 2023)

RAD コーパスに該当分野が揃っているか `rad-research` で確認すべき (機械学習・retrieval_augmented・state_space_models)。

## クロス参照

- 要件: REQUIREMENTS.md v0.8 セクション (CABT-01〜07)
- ロードマップ: ROADMAP.md Phase 8
- 前段: `src/llive/brief/grounding.py` (S1 実装、citation を ledger に固定)
- 既存 adapter: `src/llive/core/adapter.py` (HFAdapter)
- 既存 memory: `src/llive/memory/provenance.py` (metadata 由来)
