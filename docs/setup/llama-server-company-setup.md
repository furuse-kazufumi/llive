# llive を会社環境の llama.cpp `llama-server` (OpenAI 互換 API) で動かす導入手順

> **対象読者**: 会社 PC / 社内 LAN で llama.cpp の `llama-server` を既に
> 動かしており、追加ソフト導入を最小化したい技術担当者. Claude.ai に
> 渡して質問対話用 context にする想定.
>
> **前提**: 外部 cloud LLM API (OpenAI / Anthropic / Gemini) を使わず、
> on-prem で完結する構成. データ越境ゼロ.
>
> **Ollama は導入しない方針**. モデル管理が二重化する / `~/.ollama/models/`
> と llama.cpp 側 `.gguf` ファイル群の二重保管を避けるため.
>
> **対応バージョン**: llive `LLIVE_OPENAI_MODEL` env 対応版 (commit 6a7f89f,
> 2026-05-18) 以降.

---

## 0. TL;DR (env 4 つで終わり)

```powershell
# llama-server を起動 (会社 PC または LAN 内 GPU 機)
D:\llm\bin\llama-server.exe `
    --model D:\llm\models\llama-3.3-70b-instruct-Q4_K_M.gguf `
    --port 8080 `
    --ctx-size 8192

# llive を pip で導入
py -3.11 -m pip install "llmesh-llive[llm]" openai

# 環境変数 4 つ
$env:LLIVE_LLM_BACKEND   = "openai"
$env:OPENAI_BASE_URL     = "http://localhost:8080/v1"
$env:LLIVE_OPENAI_MODEL  = "llama-3.3-70b-instruct"   # llama-server の実 model 名
$env:OPENAI_API_KEY      = "dummy"                     # SDK 要件、認証は llama-server 側で別途

# 動作確認
py -3.11 -m llive.cli brief "テスト目標"
```

---

## 1. なぜ OpenAI 互換 backend を経由するのか

llama.cpp の `llama-server` は **OpenAI 互換の HTTP API** (`/v1/chat/completions`,
`/v1/embeddings` 等) を提供する. llive の `OpenAIBackend` は base_url を
上書きできる設計 (`OPENAI_BASE_URL` env) で、SDK は同じ `openai` Python パッケージ
を使う.

つまり llama-server + llive の組合せは:

```
llive ──[openai SDK]──▶ http://localhost:8080/v1/chat/completions ──▶ llama.cpp
                                  (OPENAI_BASE_URL で向け先指定)
```

ソース上の根拠 (`D:/projects/llive/src/llive/llm/backend.py:234-292`):

```python
class OpenAIBackend(LLMBackend):
    """Calls OpenAI (or any OpenAI-compatible HTTP API) via the ``openai`` SDK.
    Set OPENAI_BASE_URL to point at LM Studio / vLLM / llama-server / etc.
    Set LLIVE_OPENAI_MODEL to choose a default model name without code changes.
    """
    DEFAULT_MODEL = "gpt-4o-mini"

    def __init__(self, model=None, base_url=None):
        ...
        if base_url or os.environ.get("OPENAI_BASE_URL"):
            kwargs["base_url"] = base_url or os.environ["OPENAI_BASE_URL"]
        self._client = openai.OpenAI(**kwargs)
        self.model = (model
                      or os.environ.get("LLIVE_OPENAI_MODEL")
                      or self.DEFAULT_MODEL)
```

---

## 2. 前提条件 (会社環境チェックリスト)

| 項目 | 必須? | 備考 |
|---|---|---|
| Python 3.11 (3.12+ は未対応) | 必須 | `py -3.11 --version` |
| llama.cpp `llama-server.exe` | 必須 | 既に `D:\llm\bin\` 等に配備済の前提 |
| `.gguf` モデルファイル | 必須 | `D:\llm\models\*.gguf` |
| 社内 PyPI mirror (任意) | 任意 | 社外 pip 直接アクセス不可なら必要 |
| RAM 16 GB+ (7B-13B) / 48 GB+ (70B GPU offload 無し) | モデルサイズ依存 | Q4 量子化基準 |
| GPU (NVIDIA / AMD) | 任意 | あれば `--n-gpu-layers` で大幅高速化 |

**社内ネットワーク考慮**:

- `pip install openai>=1.0` で社外接続必要. 社内 mirror があれば
  `--index-url https://your-mirror/simple/`
- llama-server は localhost / LAN 内で完結すれば社外接続不要
- `.gguf` モデルは別 PC で download → 社内コピーで OK

---

## 3. llama-server の起動

### 3.1 シングル PC 構成 (基本)

```powershell
D:\llm\bin\llama-server.exe `
    --model D:\llm\models\llama-3.3-70b-instruct-Q4_K_M.gguf `
    --port 8080 `
    --ctx-size 8192 `
    --n-gpu-layers 80          # GPU offload 層数 (環境依存)
```

主要オプション:

| flag | 用途 |
|---|---|
| `--model <path.gguf>` | model ファイル指定 (必須) |
| `--port 8080` | listen port (default 8080) |
| `--ctx-size 8192` | context 長 (default 512 だと llive で短すぎる、8192+ 推奨) |
| `--n-gpu-layers <N>` | GPU offload 層数. 全層 GPU offload したい場合は十分大きい数 (`99` 等) を渡す慣習. 古いビルドでは `-1` も全層を意味したが、b8864 系では `99` が安全 |
| `--host 0.0.0.0` | LAN 内別ホストから接続させる場合 (社外 bind は厳禁) |
| `--api-key <key>` | API key 認証を有効化 (推奨). 設定すると llive 側で `OPENAI_API_KEY` をその値に |
| `--parallel <N>` | 並列 request slots. **複数 Brief 同時投入**する運用なら 4 以上 (llive の `orchestration.Pipeline` が `max_workers=4` で並列化). 単一 Brief 順次なら 1 で OK |
| `--alias <name>` | model alias. **本手順では不要** (llive 側 env で model 名指定するため) |
| `--verbose` | debug log |

### 3.2 model 名の確認

llama-server は **起動時の model ファイル名から model 名を自動命名** する.
HTTP で確認:

```powershell
curl http://localhost:8080/v1/models
# → {"object":"list","data":[{"id":"llama-3.3-70b-instruct-Q4_K_M",...}]}
```

この `id` の値が **`LLIVE_OPENAI_MODEL` に設定する値**.

### 3.3 LAN 内別ホストで動かす場合

GPU 機を別 PC として使うケース:

```powershell
# GPU 機側
D:\llm\bin\llama-server.exe --model ... --port 8080 --host 0.0.0.0 `
                            --api-key "social-shared-key-001"

# llive 実行 PC 側
$env:OPENAI_BASE_URL = "http://192.168.x.y:8080/v1"
$env:OPENAI_API_KEY  = "social-shared-key-001"
```

**注意**: `--host 0.0.0.0` は社内 LAN 限定. 社外 firewall 経由で公開する場合は
nginx + bearer / mTLS の前段を入れること.

---

## 4. llive インストール

```powershell
py -3.11 -m pip install --upgrade pip

# llive 本体 + openai SDK
py -3.11 -m pip install "llmesh-llive[llm]" openai

# 動作確認
py -3.11 -c "from llive.llm import OpenAIBackend; print(OpenAIBackend.DEFAULT_MODEL)"
# → gpt-4o-mini (これは env で上書きする値)
```

社内 PyPI mirror 経由なら:

```powershell
py -3.11 -m pip install --index-url https://your-mirror/simple/ `
    "llmesh-llive[llm]" openai
```

---

## 5. 環境変数 4 つの設定

```powershell
# 一時的 (現セッションのみ)
$env:LLIVE_LLM_BACKEND  = "openai"
$env:OPENAI_BASE_URL    = "http://localhost:8080/v1"
$env:LLIVE_OPENAI_MODEL = "llama-3.3-70b-instruct-Q4_K_M"   # /v1/models で得た id
$env:OPENAI_API_KEY     = "dummy"                            # llama-server に --api-key 無いなら任意文字列
```

恒久設定 (再ログイン後も有効):

```powershell
[Environment]::SetEnvironmentVariable("LLIVE_LLM_BACKEND",  "openai", "User")
[Environment]::SetEnvironmentVariable("OPENAI_BASE_URL",    "http://localhost:8080/v1", "User")
[Environment]::SetEnvironmentVariable("LLIVE_OPENAI_MODEL", "llama-3.3-70b-instruct-Q4_K_M", "User")
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY",     "dummy", "User")
```

### env の優先順位 (model 名)

llive 内部 (`OpenAIBackend.__init__`) で:

```
1. OpenAIBackend(model="<name>")   ← コード引数 (最優先)
2. $LLIVE_OPENAI_MODEL              ← env (推奨手段)
3. DEFAULT_MODEL = "gpt-4o-mini"    ← fallback (会社環境では使えない)
```

### resolve_backend の罠

`LLIVE_LLM_BACKEND` を **明示的に "openai" に設定する**こと.
未設定だと llive は以下の自動判定をする (`backend.py:405-414`):

```
$ANTHROPIC_API_KEY 設定済 → anthropic
$OPENAI_API_KEY    設定済 → openai     ← この経路でもいい
$OLLAMA_HOST       設定済 → ollama
それ以外            → mock
```

過去に `ANTHROPIC_API_KEY` を残してると意図せず Anthropic API に流れる
(= 越境発生 + 料金発生). 明示設定で防ぐ.

---

## 6. 動作確認 (Brief を 1 つ流す)

```powershell
# llama-server が起きているか
curl http://localhost:8080/v1/models | jq

# llive 経由で Brief 投入
py -3.11 -m llive.cli brief "テスト目標: Hello World を Python で書く"
```

期待される結果:

- 6 stage (Salience / Curiosity / Inner Monologue / Ego/Altruism / Action Plan
  / Finalise) が順に動く
- `BriefResult.status` が `ok` / `needs_approval` / `error`
- artifacts に出力ファイルパス

直接 backend を叩いて疎通だけ確認するなら:

```powershell
py -3.11 -c @"
from llive.llm import OpenAIBackend, GenerateRequest
b = OpenAIBackend()
print('model:', b.model)
print(b.generate(GenerateRequest(prompt='ping', max_tokens=32)).text)
"@
```

---

## 7. トラブルシュート

| 症状 | 原因 | 対処 |
|---|---|---|
| `ModuleNotFoundError: openai` | SDK 未インストール | `pip install openai>=1.0` |
| `Connection refused` to 8080 | llama-server 未起動 | `llama-server.exe --model ...` を別ウィンドウ |
| `404 model not found` | `LLIVE_OPENAI_MODEL` が llama-server の id と不一致 | `curl http://localhost:8080/v1/models` の id をコピー |
| 応答が空 / 即終了 | `--ctx-size` が小さい (default 512) | `--ctx-size 8192` 以上で再起動 |
| 応答途中で切れる | `max_tokens` 不足 | `GenerateRequest(max_tokens=2048)` 等で増やす |
| Anthropic API に流れている | `LLIVE_LLM_BACKEND` 未設定 + `ANTHROPIC_API_KEY` 残留 | `Remove-Item Env:ANTHROPIC_API_KEY` + 明示設定 |
| SDK が `OPENAI_API_KEY` 必須エラー | env 未設定 | `$env:OPENAI_API_KEY = "dummy"` |
| 401 from llama-server | llama-server 側 `--api-key` 設定済で llive 側 dummy | env の OPENAI_API_KEY を llama-server の `--api-key` 値に合わせる |
| 日本語 / 中文応答の質が低い | model 自体の特性 | Qwen 系 / DeepSeek 系の gguf に切替 |
| streaming で見たい | OpenAIBackend は同期のみ (現状) | F25 Phase h.2 の SSE 配信を待つか、別途 streaming layer |

---

## 8. データ越境 / セキュリティ

llive + llama-server (localhost / 社内 LAN) は **データが社外に出ない構成**.

| 動作 | 越境するか |
|---|---|
| llive → llama-server (localhost / 社内 LAN) | **越境しない** |
| llama-server → .gguf model 読み込み | ローカルファイル、越境せず |
| pip install (初回のみ) | **越境する** (PyPI / openai SDK 取得時のみ) |
| llive RAD コーパス / 監査ログ | ローカル file system のみ |

**やってはいけないこと**:

- llive の `LLIVE_LLM_BACKEND` を `openai` (本書) のまま `OPENAI_BASE_URL` を
  外して **本物の OpenAI API** に流す (社内データ越境)
- llama-server を `0.0.0.0:8080` で **社外公開** する (認証なしの場合は致命)
- `~/.llmesh/audit/` を cloud storage に同期する

---

## 9. 推奨 model (gguf, llama.cpp 経由運用)

| 用途 | 推奨 model | サイズ | 備考 |
|---|---|---|---|
| 標準 (英語) | `llama-3.3-70b-instruct-Q4_K_M.gguf` | 40 GB | GPU 推奨, llive 既存ベンチで主力 |
| 軽量 (CPU で動く) | `llama-3.1-8b-instruct-Q4_K_M.gguf` | 4.7 GB | 品質下限 |
| 中文強い | `qwen2.5-32b-instruct-Q4_K_M.gguf` | 18 GB | 多言語 / 中文ベンチで強い |
| コーディング | `qwen2.5-coder-32b-instruct-Q4_K_M.gguf` | 18 GB | コード生成 / レビュー |
| 軽量+品質ある程度 | `llama-3.1-70b-instruct-Q3_K_S.gguf` | 31 GB | Q3 量子化、メモリ節約 |

入手元 (例): Hugging Face TheBloke / bartowski リポジトリ.
社内ネットワーク事情によっては別 PC でダウンロード → 社内コピーが現実解.

---

## 10. オプション: ベンチ / 観測

llive のベンチ harness で llama-server backend を計測:

```powershell
py -3.11 -m llive.bench.progressive --backend openai --size m,l,xl
```

memory `feedback_benchmark_progressive_tokens` (xs/s/m/l/xl 5 段階) と
`feedback_llive_measurement_purity` (on-prem only) に従い、結果を
比較する際は他社 cloud API と混在させない.

---

## 11. 関連 docs (深堀り用)

- 規制対応 (中国・EU・日本): `D:/projects/fullsense/docs/regulatory/`
  - `cn-internal-use.md` (社内利用 filing 不要パターン)
  - `cn-public-service.md` (公衆向け filing 手順)
  - `eu-ai-act.md` (Article 別 mapping)
  - `data-sovereignty.md` (越境基準)
  - `audit-log-format.md` (HMAC chain 監査ログ)
- F25 連携 (llove / llmesh): `D:/projects/fullsense/docs/design/f25-phase-h-e2e.md`
- 別 backend (Ollama 経由) 版: `ollama-company-setup.md` (本ディレクトリ)

---

## 12. Claude.ai に渡すときの推奨プロンプト例

```
以下は llive (LLM 思考フレームワーク) を会社の llama.cpp llama-server
(OpenAI 互換 API) 経由で動かすセットアップ手順です. 内容を把握した上で、
私の環境固有の質問に答えてください.

(本ファイルの内容を貼り付け)

私の環境:
- OS: Windows 11
- Python: 3.11.x
- GPU: なし / RTX 4090 / etc.
- llama.cpp バージョン: b8864
- 実 model 名: llama-3.3-70b-instruct-Q4_K_M
- llama-server 起動済 port: 8080
- 社内プロキシ: あり / なし

質問: 〜
```

---

## 改訂履歴

- 2026-05-18 — v0.1 作成 (llama.cpp `llama-server` 経由、`LLIVE_OPENAI_MODEL`
  env 対応版 (commit 6a7f89f) 前提)
