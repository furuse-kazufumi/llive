# llive を会社環境の Ollama (LLaMA) で動かす導入手順

> **対象読者**: 会社 PC / 社内 LAN で llive を Ollama 経由の LLaMA モデルで
> 動かしたい技術担当者. Claude.ai に渡して質問対話用 context にする想定.
>
> **前提**: 外部 cloud LLM API (OpenAI / Anthropic / Gemini) を使わず、
> on-prem (顧客管理ネットワーク内) で完結する構成. データ越境ゼロ.

---

## 0. TL;DR (5 行サマリー)

```powershell
# 1. Ollama 導入 (会社 PC または LAN 内別ホスト)
winget install Ollama.Ollama       # または公式 .msi
ollama serve                       # サーバ起動 (別ウィンドウ)
ollama pull llama3.1:8b            # GPU 無し環境の現実解。70b は GPU 必須

# 2. Python 3.11 + llive
py -3.11 -m pip install llmesh-llive

# 3. 環境変数 → llive 実行
$env:LLIVE_LLM_BACKEND = "ollama"
$env:OLLAMA_HOST       = "http://localhost:11434"
py -3.11 -m llive.cli brief "テスト目標"
```

---

## 1. 前提条件 (会社環境チェックリスト)

| 項目 | 必須? | 備考 |
|---|---|---|
| Python 3.11 (3.12+ は未対応) | 必須 | `py -3.11 --version` で確認 |
| pip がプロキシ経由で社外接続可 | 必須 (初回のみ) | 社内 PyPI mirror があればそれで OK |
| Ollama 11434 ポートに到達可能 | 必須 | localhost なら不要、LAN 内なら社内 firewall 許可 |
| RAM 16 GB 以上 | 推奨 | `llama3.1:8b` 動作下限。`70b` は 64 GB+ |
| GPU (NVIDIA / Apple Silicon) | 任意 | CPU でも動くが体感 1 トークン/秒 級 |
| ディスク空き 30 GB 以上 | 推奨 | llama3.1:8b ≒ 4.7 GB, llama3.3:70b ≒ 40 GB |

**社内ネットワーク事情に注意**:

- `ollama pull` は社外 (registry.ollama.ai) に到達する必要があります.
  プロキシ環境では `HTTPS_PROXY` 環境変数を設定.
- モデルファイルを **別 PC で pull → 社内コピー** することも可能.
  パス: `~/.ollama/models/` (Windows: `%USERPROFILE%\.ollama\models\`)
- pip も同様に社内 mirror か `--index-url` 切替で対応.

---

## 2. Ollama インストール

### 2.1 Windows

```powershell
# 推奨: winget
winget install Ollama.Ollama

# または公式 .msi: https://ollama.com/download/OllamaSetup.exe
```

インストール後:

```powershell
# サーバ起動 (常駐).
# 自動起動になっていない場合は手動でこのコマンドを別ウィンドウで.
ollama serve

# 別ターミナルで疎通確認
curl http://localhost:11434/api/tags
# → {"models":[...]} が返れば OK
```

### 2.2 Linux (会社 Linux サーバ / WSL)

```bash
curl -fsSL https://ollama.com/install.sh | sh
systemctl --user enable ollama
systemctl --user start ollama
```

### 2.3 LAN 内の別ホストで動かす場合

Ollama サーバを別 PC (GPU 機など) に置くケース:

```powershell
# サーバ側 (GPU 機)
$env:OLLAMA_HOST = "0.0.0.0:11434"   # LAN に bind
ollama serve

# クライアント側 (llive 実行 PC)
$env:OLLAMA_HOST = "http://192.168.x.y:11434"
```

**注意**: Ollama 自体に認証機能は無いので、社内 LAN 外には絶対に
bind しないこと. 公開する場合は nginx などで bearer / mTLS の前段を入れる.

---

## 3. モデル pull

```powershell
# GPU 無し: 軽量モデル
ollama pull llama3.1:8b

# GPU 有り (16 GB+ VRAM): 中規模
ollama pull llama3.1:70b

# 最新の高性能
ollama pull llama3.3:70b

# 中国語強い (会社が中国向けサービスする場合)
ollama pull qwen2.5:32b

# コーディング特化
ollama pull qwen2.5-coder:32b

# ビジョン (画像読み取り)
ollama pull llava:7b
```

`ollama list` で pull 済モデル確認.

**サイズ別の目安** (筆者 / llive ベンチ実測 ベース):

| モデル | RAM/VRAM | 速度 | llive 品質 |
|---|---|---|---|
| `llama3.2:3b` | 4 GB | 高速 | **不足**. Brief A/B で明らかに劣化. 検証用のみ |
| `llama3.1:8b` | 8 GB | 普通 | 実用下限. CPU でも動く |
| `llama3.1:70b` | 48 GB+ (GPU) | 遅め | 実用上限の標準. GPU 推奨 |
| `llama3.3:70b` | 48 GB+ (GPU) | 同上 | 2026 最新. llama3.1:70b より好成績 |
| `qwen2.5:32b` | 24 GB | 中速 | 多言語特に中文に強い |

---

## 4. llive インストール

```powershell
# Python 3.11 がインストール済の前提
py -3.11 -m pip install --upgrade pip
py -3.11 -m pip install llmesh-llive

# 動作確認
py -3.11 -c "import llive; print(llive.__version__)"
```

社内 PyPI mirror を使う場合:

```powershell
py -3.11 -m pip install --index-url https://your-mirror/simple/ llmesh-llive
```

---

## 5. 環境変数の設定

llive は以下 2 つの env で Ollama を認識します:

```powershell
# 必須
$env:LLIVE_LLM_BACKEND = "ollama"

# Ollama サーバ位置 (localhost なら省略可)
$env:OLLAMA_HOST       = "http://localhost:11434"

# モデル指定 (省略時は llama3.1 default)
# llive 内部で OllamaBackend(model=...) を渡す経路があれば
# config / 環境変数 / コード引数 のいずれかで指定.
```

恒久設定する場合:

```powershell
[Environment]::SetEnvironmentVariable("LLIVE_LLM_BACKEND", "ollama", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_HOST", "http://localhost:11434", "User")
```

---

## 6. 動作確認 (Brief を 1 つ流す)

```powershell
py -3.11 -m llive.cli brief "テスト用の目標: Hello World を Python で書く"
```

期待される結果:

- 6 stage (Salience / Curiosity / Inner Monologue / Ego/Altruism / Action Plan
  / Finalise) が順に動く
- 思考因子 (uncertainty / structurize / ...) の発火状態が出力
- `BriefResult.status` が `ok` / `needs_approval` / `error` のいずれか
- artifacts に出力ファイルパスが含まれる

エラー時のチェック:

```powershell
# Ollama サーバ疎通
curl http://localhost:11434/api/tags

# モデル指定エラーなら llist
ollama list

# llive デフォルト model が pull されていない場合
ollama pull llama3.1
```

---

## 7. トラブルシュート

| 症状 | 原因 | 対処 |
|---|---|---|
| `Connection refused` to 11434 | Ollama サーバ未起動 | `ollama serve` を別ウィンドウで実行 |
| `model not found: llama3.1` | モデル未 pull | `ollama pull llama3.1` |
| 応答が極端に短い / 途中で切れる | num_ctx が 2048 default で truncated | llive 側 config で `num_ctx=8192` 以上に上書き |
| CPU 100% で 1 トークン/秒 | GPU 未使用 | NVIDIA driver / CUDA 確認. または小モデル (llama3.1:8b) に切替 |
| pip install で SSL/プロキシエラー | 会社 firewall | `HTTPS_PROXY` env + 社内 mirror 使用 |
| Brief が `needs_approval` で止まる | HITL Approval Bus 待ち | これは正常. policy 側で `approval_required=False` にするか、HITL UI から承認 |
| 日本語応答の質が低い | llama 系は英語寄り | `qwen2.5:32b` に切替 (多言語強い) |
| 中文応答の質が低い | 同上 | `qwen2.5:32b` または DeepSeek 系 |

---

## 8. 注意点 — データ越境 / セキュリティ

llive + Ollama の組合せは **データが社外に出ない構成** が原則.

| 動作 | 越境するか |
|---|---|
| llive → Ollama (localhost / 社内 LAN) | **越境しない** |
| Ollama → モデル pull (`registry.ollama.ai`) | **越境する** (モデル取得時のみ。runtime は越境しない) |
| llive RAD コーパス (`D:/.../rad/`) | ローカル file system のみ |
| llive 監査ログ | `~/.llmesh/audit/` (社内 storage 推奨) |

**やってはいけないこと**:

- llive の `LLIVE_LLM_BACKEND` を `openai` / `anthropic` に切替えて
  cloud API に流す (社内データが社外に出る)
- Ollama を `0.0.0.0:11434` で社外公開する (認証なし)
- `~/.llmesh/audit/` を cloud storage に同期する

---

## 9. オプション: 別 backend への切替

llive は backend をプラガブルにできる設計:

| LLIVE_LLM_BACKEND | 用途 |
|---|---|
| `mock` | テスト用. 決定論的応答. 学習目的のみ |
| `ollama` | **本書の対象**. on-prem LLaMA / Qwen 等 |
| `openai` | OpenAI API. **on-prem 制約があれば使わない** |
| `anthropic` | Anthropic API. 同上 |
| `cnmesh:<provider>:<model>` | llmesh 経由で中国 LLM (Qwen/DeepSeek/GLM) |

会社環境では `ollama` または `cnmesh:` のみ使用. cloud API 系は越境発生.

---

## 10. 関連 docs (深堀り用)

- 規制対応 (中国・EU・日本): `D:/projects/fullsense/docs/regulatory/`
  - `cn-internal-use.md` (社内利用 filing 不要パターン)
  - `cn-public-service.md` (公衆向け filing 手順)
  - `eu-ai-act.md` (Article 別 mapping)
  - `data-sovereignty.md` (越境基準)
  - `audit-log-format.md` (HMAC chain 監査ログ)
- F25 連携 (llove / llmesh): `D:/projects/fullsense/docs/design/f25-phase-h-e2e.md`

---

## 11. Claude.ai に渡すときの推奨プロンプト例

```
以下は llive (LLM 思考フレームワーク) を会社 Ollama 環境で動かす
セットアップ手順です. 内容を把握した上で、私の環境固有の質問に
答えてください.

(本ファイルの内容を貼り付け)

私の環境:
- OS: Windows 11
- Python: 3.11.x
- GPU: なし / RTX 4070 / その他
- 社内プロキシ: あり / なし
- 想定モデル: llama3.1:8b / llama3.1:70b / qwen2.5:32b

質問: 〜
```

---

## 改訂履歴

- 2026-05-18 — v0.1 作成 (会社 Ollama 環境向け llive セットアップ手順)
