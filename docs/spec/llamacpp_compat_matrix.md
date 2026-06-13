# llama.cpp 互換性マトリクス (llive ↔ external runtime)

**Drafted:** 2026-05-21
**Status:** **single source of truth** — `docs/requirements_v0.A_external_runtime_tracking.md` ER-PROC-04 で参照される.
**Update cadence:** **月 1 回** (毎月 1 日 JST, ER-PROC-01).

> 公開ベンチ / Honest Disclosure 報告で **stable SHA を必ず明記** する.
> `feedback_llamacpp_tracking` memory にも 1 行記録する.

---

## 1. pin 3 段階

| 段階 | 用途 | pin 強度 | 切替判断 |
|---|---|---|---|
| **stable** | 公開ベンチ / Honest Disclosure 報告 | strict (SHA) | smoke 全 GREEN + 2 週間 rolling 経験 |
| **rolling** | 開発 / 試行 | loose (release tag) | 月次レビューで毎月更新 |
| **edge** | 新機能 PoC | なし | smoke 通過のみ条件 |

---

## 2. matrix (本体)

`| 月 | stable_sha | stable_tag | rolling_tag | gguf_spec | sampler_chain_spec | kv_cache_quant_default | smoke_result | breaking_changes_observed |`

| 月 | stable_sha | stable_tag | rolling_tag | gguf_spec | sampler_chain_spec | kv_cache_quant_default | smoke_result | breaking_changes_observed |
|---|---|---|---|---|---|---|---|---|
| 2026-05 | _TBD_ | _TBD_ | _TBD_ | v3 | top_k=40 top_p=0.95 min_p=0.05 typ_p=1.0 temp=0.7 | q8_0 (default化観測) | _PENDING (ER-PROC-03 を回す)_ | (初版, 過去 1 か月分は次回ベース化時に埋める) |

### 列の意味

| 列 | 意味 |
|---|---|
| `month` | 観測月 (YYYY-MM, JST) |
| `stable_sha` | 公開ベンチに使う commit SHA |
| `stable_tag` | 同 SHA の release tag (例 `b4501`) |
| `rolling_tag` | 開発で動かす release tag (毎月入替) |
| `gguf_spec` | GGUF metadata spec version |
| `sampler_chain_spec` | sampler chain の文字列表現 (param order を含む) |
| `kv_cache_quant_default` | KV cache 量子化の default 値 |
| `smoke_result` | `tests/contract/test_llamacpp_smoke.py` の結果 (GREEN/YELLOW/RED) |
| `breaking_changes_observed` | 月次レビューで気付いた破壊変更. 無ければ "—" |

---

## 3. smoke test カバレッジ (ER-PROC-03)

`tests/contract/test_llamacpp_smoke.py` (要新規 skeleton) で以下を最小カバー:

| Smoke # | 確認内容 | failure → matrix |
|---|---|---|
| S-1 | `/v1/chat/completions` で 1 ターン応答 | RED |
| S-2 | `stop` token が効く | RED |
| S-3 | streaming (`stream=true`) で chunk が来る | YELLOW (一部運用は不要) |
| S-4 | JSON mode (`response_format={"type":"json_object"}`) で valid JSON | YELLOW |
| S-5 | token usage が返る (`usage.{prompt,completion}_tokens`) | YELLOW (bench で必要) |
| S-6 | `tools` / function calling 呼び出し (新 SHA で対応版なら) | edge のみ必須 |

判定:

- S-1 + S-2 fail → **RED**
- S-1 + S-2 pass, S-3〜S-5 のいずれか fail → **YELLOW**
- 全 pass → **GREEN**

---

## 4. GGUF model 推奨 (運用上の参考)

bench で常用する推奨 model を **GGUF spec version とともに pin**:

| 用途 | 推奨 model | quant | gguf_spec | 出所 |
|---|---|---|---|---|
| coding | qwen2.5-coder-7b-instruct | q4_k_m | v3 | HF: Qwen/Qwen2.5-Coder-7B-Instruct-GGUF |
| general | qwen2.5-7b-instruct | q4_k_m | v3 | HF: Qwen/Qwen2.5-7B-Instruct-GGUF |
| small | llama-3.2-3b-instruct | q4_k_m | v3 | HF: bartowski/Llama-3.2-3B-Instruct-GGUF |
| vlm (将来) | qwen2-vl-7b-instruct | q4_k_m | v3 | HF: bartowski/Qwen2-VL-7B-Instruct-GGUF |

> 推奨 model は **必須ではない** — ユーザー任意. 上記は bench で再現性を取るための
> 既知値. Qwen 依存リスクは [[feedback-qwen-commercial-barrier]] 参照, 商用配布 model は別途検討.

---

## 5. 矛盾解決のルール

- **stable_sha と rolling_tag が分岐したとき**: 公開ベンチは必ず stable_sha で取り直す.
  rolling のベンチ値は publish しない.
- **GGUF spec version が上がったとき**: 推奨 model 表の `gguf_spec` を更新.
  互換性が切れる場合は **stable_sha も同月で更新** (rolling 経験を待たない).
- **sampler chain spec が変わったとき**: `bench_*.py` の出力 JSON の
  `sampler_chain_spec` 列が以前と differ する → Honest Disclosure 上, 比較不能とマーク.

---

## 6. 関連

- `docs/requirements_v0.A_external_runtime_tracking.md` — 本 matrix を駆動する運用要件
- [[feedback-llamacpp-tracking]] — 月次レビューの memory 化
- [[feedback-benchmark-honest-disclosure]] — 「変に速い」内訳
- [[feedback-benchmark-progressive-tokens]] — progressive size curve
- llama.cpp releases: <https://github.com/ggml-org/llama.cpp/releases>
- GGUF spec: <https://github.com/ggml-org/ggml/blob/master/docs/gguf.md>
