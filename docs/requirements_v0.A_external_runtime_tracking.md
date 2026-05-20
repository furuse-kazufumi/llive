# llive 要件定義 v0.A — 外部 LLM ランタイム追従 (llama.cpp / GGUF / sampler)

**Drafted:** 2026-05-21
**Status:** **運用要件追加** (機能要件ではなく **追従プロセス** を固定する)
**Type:** Operational requirement / external dependency tracking
**Trigger:** ユーザ指摘 (2026-05-20) — 「llama.cpp の更新が激しいみたいですね」「定期的に更新に合わせて追従するようにした方が良いでしょう」

> v0.A は機能 vertical ではなく **横断する運用ルール**. アルファベット連番で
> v0.1〜v0.9 (機能要件) と区別する.

---

## 1. 動機

llive は on-prem LLM を一次走者にする FullSense 哲学 (`feedback_llive_measurement_purity`) のため,
`llama.cpp` / `llama-server` (OpenAI compat API) 経由運用が **性能 + 品質 + 互換性** の
全方位に直結する.

直近の llama.cpp の更新ペースから以下が観測された:

1. **GGUF メタ format の破壊的変更** が複数回発生. 「先週まで動いた quant model」
   が読めなくなる事故が再発しうる.
2. **sampler chain API 刷新** (samplers config の構造変更). `repeat_penalty` / `min_p` /
   `top_n_sigma` 系の挙動が version で微妙に変わる → ベンチが「変に速い/遅い」になる
   ([[feedback-benchmark-honest-disclosure]] の盲点).
3. **`/v1/chat/completions` の tools / function calling / JSON mode 強化**.
   `OpenAIBackend` 経由で出力契約が変動する可能性.
4. **KV cache 量子化が default 化**. low-spec PC 運用が現実的になり,
   `bench/low_spec.py` の測定基準が変動.
5. **MoE / multimodal 対応の急速拡張** (LLaVA, Qwen-VL, MiniCPM, mtmd).
   VLM-FX ([[project-llive-vlm-future]]) の実装難度が下がる反面, runtime spec の
   moving target 化.
6. **speculative decoding / draft model** 周りが production 候補になりつつある.

**追従しないと**: (a) 突然動かない (b) ベンチが嘘になる (c) 新機能を取り損ねる.
**追従しすぎると**: (d) 不安定な edge を踏む (e) 工数発散.

→ 中庸として **月次追従 + commit SHA pin + smoke test 強制** をルール化する.

---

## 2. 監視対象と粒度

| # | 対象 | 監視粒度 | 影響先 |
|---|---|---|---|
| ER-01 | `llama.cpp` 本体 | 月 1 回 release notes + master HEAD diff | `OpenAIBackend` / `low_spec` bench |
| ER-02 | `llama-server` (`server.cpp`) | `/v1/chat/completions` の挙動差分 | `OpenAIBackend` smoke test |
| ER-03 | GGUF spec version | breaking change の都度 | 同梱 model 推奨 + bench artifact |
| ER-04 | sampler chain API | breaking change の都度 | `OpenAIBackend` config + bench |
| ER-05 | KV cache 量子化 default | 月次 | `bench/low_spec.py` baseline |
| ER-06 | multimodal (LLaVA / mtmd / Qwen-VL) | 四半期 | VLM-FX 着手判断 |
| ER-07 | speculative decoding / draft model | 四半期 | Phase 5 以降の最適化候補 |
| ER-08 | python-side wrapper (`llama-cpp-python`, `ctransformers`) | 月次 | 代替 backend 経路 |

監視は **自動化を後回しにして, 人間が release notes 読みでも回せる粒度** とする
(月 1 回 = 15-30 分).

---

## 3. 追従ルール (運用)

### ER-PROC-01: 月次レビュー (毎月 1 日, JST)

1. `https://github.com/ggml-org/llama.cpp/releases` の **直近 1 か月分の release** を
   ざっと読む.
2. `docs/spec/llamacpp_compat_matrix.md` に 1 行追加 (matrix 形式, 後述).
3. **breaking change** が含まれている場合は `feedback_llamacpp_tracking` memory に
   1 行追記.
4. smoke test を回す (ER-PROC-03).

### ER-PROC-02: commit SHA pin

`docs/spec/llamacpp_compat_matrix.md` に **動作確認済 commit SHA** を pin する.
矛盾を避けるため pin は以下の 3 段階で運用:

| 段階 | 用途 | pin 強度 |
|---|---|---|
| **stable** | 公開ベンチで使う SHA. 必ず pin. | strict |
| **rolling** | 開発 / 試行用. 月次レビューで毎月更新. | loose |
| **edge** | 新機能 PoC 用. random commit, smoke test 通過のみ条件. | none |

bench 結果と Honest Disclosure 報告には **stable SHA を必ず明記**
(`feedback-benchmark-honest-disclosure` 拡張).

### ER-PROC-03: smoke test (`OpenAIBackend` contract)

新 llama-server SHA で動作確認するための **contract test** を 1 本固定する:

```bash
# llama-server (新 SHA) を別 terminal で起動
./llama-server -m model.gguf --port 8080

# llive 側 smoke (env 名は OpenAI SDK の慣例に合わせる)
$env:OPENAI_BASE_URL = "http://localhost:8080/v1"
$env:OPENAI_API_KEY = "dummy-for-llamacpp"   # llama-server は任意の dummy で OK
$env:LLIVE_OPENAI_MODEL = "qwen2.5-coder-7b-instruct-q4_k_m"  # 任意
py -3.11 -m pytest tests/contract/test_llamacpp_smoke.py -v
```

`tests/contract/test_llamacpp_smoke.py` (要新規) は以下を最小カバー:

- `/v1/chat/completions` で 1 ターン応答が返る
- `stop` token が効く
- streaming (`stream=true`) で chunks が来る
- JSON mode (`response_format={"type": "json_object"}`) が壊れない
- token usage が返る

これが全部 pass → matrix の status を **GREEN** に.

### ER-PROC-04: 互換性 matrix の更新

`docs/spec/llamacpp_compat_matrix.md` を **single source of truth** とする
(matrix 雛形は別ファイル).

### ER-PROC-05: bench への必須 metadata 注入

`bench_run.py` / `bench_vlm.py` / `bench/low_spec.py` の出力 JSON に以下を **必須** 化:

```json
{
  "llama_cpp_sha": "abc1234",
  "llama_cpp_release_tag": "b4501",
  "gguf_spec_version": 3,
  "sampler_chain_spec": "top_k=40 top_p=0.95 ...",
  "kv_cache_quantization": "q8_0",
  "model_quant": "q4_k_m"
}
```

これが無いベンチは **honest_disclosure 上 INVALID** とする
([[feedback-benchmark-honest-disclosure]] 強化).

### ER-PROC-06: lleval との連携 (portal 側)

`portal/docs/spec/lleval_v0_1_implementation_notes.md` の Honest Disclosure
5 因子 (warmup / token-norm / RTT / attach / load) に **runtime metadata** を
追加因子として乗せる. lleval CI でこの metadata が無い場合 BLOCK.

---

## 4. 影響範囲 (現状コード)

| ファイル / モジュール | 触る理由 |
|---|---|
| `src/llive/llm/backend.py` (`OpenAIBackend`) | sampler / endpoint 仕様変更時の互換 |
| `bench_*.py` 系 | metadata 注入 |
| `tests/contract/test_llamacpp_smoke.py` | 新規, 月次 smoke の足場 |
| `docs/spec/llamacpp_compat_matrix.md` | 新規, single source of truth |
| `docs/requirements_v0.A_external_runtime_tracking.md` | 本ファイル |

---

## 5. リスクと緩和

| リスク | 影響 | 緩和 |
|---|---|---|
| llama.cpp 月次 release が極端な breaking | rolling SHA が壊れる | stable SHA は保守的に, rolling は smoke pass を条件 |
| GGUF 旧 quant がサポート切れ | 同梱推奨 model が読めない | matrix で `model_gguf_min_version` を pin, model 移行 PR を別建てに |
| smoke test に時間がかかり月次が破綻 | 運用継続性 | smoke を 30 秒以内に限定. heavy bench は別タスク |
| llama.cpp に致命バグ → silent quality 劣化 | ベンチ品質低下 | bench に **token-by-token logprob diff** を比較 step として追加 (v0.A の次フェーズ候補) |

---

## 6. 追加要件 (将来候補)

- **ER-09**: `llama-cpp-python` 経由運用の追加 (現状は `OpenAIBackend` 一択). subprocess より低 RTT.
- **ER-10**: alternative runtime (`ollama`, `vLLM`, `mlx-lm`, `TGI`) の同型 contract test 横展開.
- **ER-11**: speculative decoding (draft + target model) を `OpenAIBackend` 経由で smoke test.
- **ER-12**: K/V 量子化前後の **A/B bench** を progressive matrix (`lleval` LE-02) と連結.

---

## 7. 関連

- [[feedback-benchmark-honest-disclosure]] — 「変に速い」が出たら内訳を疑う
- [[feedback-benchmark-progressive-tokens]] — xs/s/m/l/xl curve
- [[feedback-llive-measurement-purity]] — on-prem 一次走者 / cloud 直接呼びと分離
- [[project-llive-openai-model-env]] — `LLIVE_OPENAI_MODEL` 経由運用 (commit 6a7f89f)
- [[project-llive-vlm-future]] — VLM-FX
- [[project-llmesh-neuro-long-term]] — low-spec 運用文脈
- portal `docs/spec/lleval_v0_1_implementation_notes.md` — Honest Disclosure 5 因子拡張
- portal `docs/spec/llamacpp_compat_matrix.md` (new, llive ↔ portal の SSoT は llive 側 specs/ に最終的に同期する候補)

---

## 8. 即時アクション (本要件追加に伴うフォローアップ)

| # | アクション | 所要 | 着手判断 |
|---|---|---|---|
| A-1 | `docs/spec/llamacpp_compat_matrix.md` 雛形作成 (本要件と同 commit) | 10 min | auto |
| A-2 | `tests/contract/test_llamacpp_smoke.py` skeleton (実行は手動 ON で良い) | 30 min | 次セッション |
| A-3 | `bench_*.py` に metadata 注入 (まず引数 pass-through だけ) | 1h | credential 復旧と並走 |
| A-4 | lleval impl notes に runtime metadata 章を追加 | 15 min | 本指示と同セッション |
| A-5 | 月次レビュー用 reminder を `~/.claude/projects/.../memory/` の `feedback_llamacpp_tracking` に記録 | 5 min | 本指示と同セッション |
