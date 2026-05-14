# MCP 連携ガイド — Claude Desktop / LM Studio / Open WebUI / Cursor / Continue.dev

llive は **MCP (Model Context Protocol) server** として動作し、Raptor 由来の
RAD 知識庫 (49 分野・44,864 docs) を外部 LLM ホストから呼び出せる tool として
公開します。これにより Ollama / LM Studio / Claude Desktop / Open WebUI /
Cursor / Continue.dev のいずれからでも、llive の知識・記憶 API を直接使った
**ローカルファースト記憶 LLM** が組めます。

## 提供 tool (Phase C-2.0)

| Tool name | 用途 |
|---|---|
| `list_rad_domains` | 全 RAD ドメインの一覧 + メタデータ (ファイル数・サイズ・取り込み日時) |
| `get_domain_info` | 1 ドメインの詳細 + corpus2skill 階層スキル (あれば) |
| `query_rad` | キーワード検索 (filename score × 3 + content score、excerpt 付き) |
| `read_document` | 特定ドキュメントの本文を取得 (max_bytes で truncate) |
| `append_learning` | `_learned/<domain>/` に学習物を書き戻し (provenance.json 自動生成) |

将来 (Phase C-2.1) 追加予定: `vlm_describe_image` / `code_complete` /
`code_review` / `recall_memory`。

## 事前準備

1. **llive リポジトリのクローン** + Python 3.11 環境構築
2. **MCP 依存のインストール**:
   ```powershell
   py -3.11 -m pip install -e .[mcp]
   ```
3. **RAD コーパスの取り込み** (1 回だけ):
   ```powershell
   py -3.11 scripts/import_rad.py
   ```
   `D:/projects/llive/data/rad/` 配下に 49 分野・~112 MB が展開されます。
4. **動作確認**:
   ```powershell
   py -3.11 -m pytest tests/unit/test_mcp_server_smoke.py -v
   ```

## クライアント別設定

### Claude Desktop

`%APPDATA%\Claude\claude_desktop_config.json` に以下を追加:

```json
{
  "mcpServers": {
    "llive": {
      "command": "py",
      "args": ["-3.11", "-m", "llive.mcp.server"],
      "env": {
        "LLIVE_RAD_DIR": "D:/projects/llive/data/rad"
      }
    }
  }
}
```

再起動後、`@llive` でツールを呼べます。

### LM Studio (≥ 0.3.x)

LM Studio の Developer タブ → MCP Servers に同様の設定を追加:

```json
{
  "name": "llive",
  "command": "py",
  "args": ["-3.11", "-m", "llive.mcp.server"],
  "env": { "LLIVE_RAD_DIR": "D:/projects/llive/data/rad" }
}
```

### Open WebUI

Settings → Models → Tools → Add MCP server。`stdio` 経由で同じコマンドを設定。

### Cursor / Continue.dev

`.cursor/mcp.json` または `~/.continue/config.json` の `mcpServers` セクションに
同じ JSON を追加。Cursor の場合は Cursor Settings → Features → MCP からも追加可。

### Ollama (直叩き、Phase C-3 後)

現状の Ollama 本体は MCP client ではないため、直接 MCP サーバとして接続することは
できません。Phase C-3 で実装する **OpenAI 互換 HTTP server** (`/v1/chat/completions`)
が完成すると、Ollama の OpenAI 互換クライアント経由で利用可能になります。

それまでは、Ollama を **モデルプロバイダ**として使い、llive 側で
``LLIVE_LLM_BACKEND=ollama`` を設定して `llive.llm.OllamaBackend` 経由で呼ぶ形が
利用可能です。

## 環境変数

| 変数 | 既定値 | 用途 |
|---|---|---|
| `LLIVE_RAD_DIR` | `<repo>/data/rad` | RAD ルート (読み + 書き層) |
| `RAPTOR_CORPUS_DIR` | — | `LLIVE_RAD_DIR` 未設定時のフォールバック (Raptor 共有) |
| `LLIVE_LLM_BACKEND` | (auto) | `mock` / `anthropic` / `openai` / `ollama` |
| `ANTHROPIC_API_KEY` | — | 設定があれば Anthropic backend が自動選択 |
| `OPENAI_API_KEY` | — | 設定があれば OpenAI backend が自動選択 |
| `OPENAI_BASE_URL` | — | LM Studio / vLLM 等の OpenAI 互換 URL |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama HTTP API |

## 動作デモ

```jsonc
// list_rad_domains
{ "method": "tools/call", "params": { "name": "list_rad_domains" } }
// → [{"name": "security_corpus_v2", "file_count": 751, "is_learned": false}, ...]

// query_rad
{
  "method": "tools/call",
  "params": {
    "name": "query_rad",
    "arguments": { "keywords": "buffer overflow", "domain": "security_corpus_v2", "limit": 3 }
  }
}
// → [{"domain": "security_corpus_v2", "doc_path": ".../buffer_overflow.md", "score": 18.0, "excerpt": "...", "matched_terms": ["buffer", "overflow"]}, ...]

// append_learning (consolidation が自動呼び出し、手動でも可)
{
  "method": "tools/call",
  "params": {
    "name": "append_learning",
    "arguments": {
      "domain": "domain_concept",
      "content": "# Newly learned topic\\n\\nSummary text...",
      "source_type": "consolidator",
      "confidence": 0.8,
      "derived_from": ["event-001", "event-002"]
    }
  }
}
// → {"doc_id": "20260515T093012Z-a1b2c3d4", "doc_path": ".../domain_concept/<id>.md", ...}
```

## トラブルシューティング

* **`ERROR: the 'mcp' package is not installed.`**
  → `py -3.11 -m pip install 'mcp>=1.0'`
* **`list_rad_domains` が空配列を返す**
  → `LLIVE_RAD_DIR` 配下に `<domain>_v2/` ディレクトリが存在するか確認。
    まだなら `py -3.11 scripts/import_rad.py` で取り込み。
* **Path traversal エラー** (`PermissionError: path traversal blocked`)
  → `read_document` の `rel_path` に `..` を含めない。
* **`append_learning` が動かない**
  → ドメイン名に `/` や `\` を含めない。`.` で始まる名前も禁止。

## 関連ドキュメント

* `data/rad/README.md` — RAD レイアウト
* `docs/ROADMAP.md` — Epic RAD-A/B/C 進捗
* `docs/PROGRESS.md` — セッション別作業ログ
* `src/llive/llm/backend.py` — LLM backend abstraction (Phase C-1)
