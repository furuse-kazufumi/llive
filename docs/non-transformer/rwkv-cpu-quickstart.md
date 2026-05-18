# RWKV-7 CPU クイックスタート — GPU 無し PC で llive を動かす最短経路 (draft v0.1)

> 2026-05-18 作成. ユーザーの primary 環境が「GPU 無しの個人 PC」であることを
> 受けて、RWKV-7 (案 E from `ROADMAP.md`) を最速で動かすための手順.
>
> 想定読者: 自分の PC に GPU が無いが llive で何かを動かしたい開発者・研究者.

---

## 0. なぜ RWKV-7 が CPU only の最善手か

| 観点 | 説明 |
|---|---|
| RNN 形 推論 | 1 ステップ計算量が O(state_dim) — 系列長に依存しない |
| Apache-2.0 | 商用利用・再配布制限なし、FullSense dual-license と整合 |
| 軽量サイズ豊富 | 0.4B / 1.5B / 3B / 7B / 14B の選択肢、CPU 性能に応じ調整可能 |
| 多言語対応 | RWKV-7 World series は日英中対応、Mistral 系より日本語が良い |
| 純 CPU 最適化実装あり | rwkv.cpp が AVX2 / AVX-512 / ARM NEON で書かれており GPU 不要 |

Mamba 系は CPU only だと現状秒 1-2 トークン程度のため、**短期 (3 ヶ月)
では非現実的**. 長期では Mamba も入れるが、まず RWKV で立ち上げる.

---

## 1. PC スペック → モデルサイズ目安 (Q4 量子化基準)

| RAM | CPU | 推奨モデル | 期待速度 (xs ~500 tok) |
|---|---|---|---|
| 4 GB | 古め CPU (2018 以前) | RWKV-7 World **0.4B** | ~5 秒 |
| 8 GB | i5 / Ryzen 5 (2020+) | RWKV-7 World **1.5B** | ~3-5 秒 |
| 16 GB | i7 / Ryzen 7 (2022+) | RWKV-7 World **3B** | ~3 秒 |
| 16-32 GB | 上記 + AVX-512 | RWKV-7 World **7B** | ~5-10 秒 |
| 32 GB+ | i9 / Ryzen 9 | RWKV-7 World **14B** | 検証要 |

**判断基準**: `s` payload (~2k tok) で 15 秒以内に応答が返れば実用域.

---

## 2. インストール (Windows + PowerShell)

### 2.1 rwkv.cpp バイナリ取得

`rwkv.cpp` (https://github.com/RWKV/rwkv.cpp) は単一実行ファイルで、
**Python ランタイム無しで動く**. 推奨経路:

```powershell
# A. Release から直接 .zip を取得 (公式リリース)
# https://github.com/RWKV/rwkv.cpp/releases から
# rwkv.cpp-windows-x86_64-AVX2.zip を D:\llm\bin\ に展開

# B. または自分でビルド (CMake + MSVC、所要 ~5 分)
git clone https://github.com/RWKV/rwkv.cpp
cd rwkv.cpp
cmake -B build -DRWKV_BUILD_SHARED_LIBRARY=ON
cmake --build build --config Release
```

### 2.2 モデル取得 (`.bin` 形式)

Hugging Face から RWKV-7 World series の Q4 量子化済モデルを直接 download:

```powershell
# 例: 1.5B (推奨第一候補)
curl -L -o D:\llm\models\rwkv-7-world-1.5b-q4.bin `
  "https://huggingface.co/<rwkv-org>/RWKV-7-World-1.5B/resolve/main/rwkv-7-world-1.5b-q4.bin"
```

**注意**: 社内 PC で社外 download 禁止の場合は別 PC で取得し USB / 社内
mirror で持ち込む. memory `feedback_d_drive_preference` に従い D ドライブ
配置 (`D:\llm\models\`).

### 2.3 動作確認 (REPL で 1 応答)

```powershell
D:\llm\bin\rwkv.cpp\bin\Release\main.exe `
  --model D:\llm\models\rwkv-7-world-1.5b-q4.bin `
  --prompt "Hello, RWKV. " `
  --tokens 64
```

10-30 秒以内に応答テキストが出れば OK. 出ない場合 §6 トラブルシュート.

---

## 3. OpenAI 互換 HTTP server として起動

llive は OpenAI 互換 API 経由で接続するので、rwkv.cpp に同梱の HTTP
server を立てる:

```powershell
D:\llm\bin\rwkv.cpp\bin\Release\server.exe `
  --model D:\llm\models\rwkv-7-world-1.5b-q4.bin `
  --port 8080 `
  --ctx-size 4096
```

別ターミナルで疎通確認:

```powershell
curl http://localhost:8080/v1/models
# → {"data":[{"id":"rwkv-7-world-1.5b","object":"model",...}]}
```

`id` をメモ. これが `LLIVE_RWKV_MODEL` に設定する値.

---

## 4. llive 接続 (env 4 つ)

```powershell
py -3.11 -m pip install llmesh-llive openai

$env:LLIVE_LLM_BACKEND   = "rwkv"
$env:LLIVE_RWKV_TRANSPORT = "rwkv_cpp_server"
$env:LLIVE_RWKV_MODEL    = "rwkv-7-world-1.5b"   # /v1/models で得た id
$env:OPENAI_BASE_URL     = "http://localhost:8080/v1"
$env:OPENAI_API_KEY      = "dummy"

# 動作確認
py -3.11 -m llive.cli brief "テスト: 簡単な日本語の挨拶を返してください"
```

期待: 30 秒以内に Brief が完了し `BriefResult.status="ok"` が返る.

---

## 5. ベンチ harness で xs/s 計測

```powershell
py -3.11 -c @"
from llive.benchmark.low_spec import run_matrix, to_json
import json
results = run_matrix(['rwkv'])  # default: xs/s only (CPU-safe)
print(json.dumps(to_json(results), ensure_ascii=False, indent=2))
"@
```

§0.2 表の xs / s 行を達成しているか確認. **3 回連続で達成すれば実用域**
と判断 (1 回だけでは judge しない、memory
`feedback_benchmark_honest_disclosure`).

達成しない場合の対応:

| 失敗ケース | 対応 |
|---|---|
| xs > 5 秒 | model サイズを 1 段下げ (1.5B → 0.4B) |
| s > 15 秒 | model サイズを 1 段下げ、ctx-size を 2048 に縮める |
| RAM > 6 GB | Q4 → Q3 量子化、または model サイズを下げる |

---

## 6. トラブルシュート

| 症状 | 原因 / 対処 |
|---|---|
| `main.exe` が SSE/AVX 非対応エラー | CPU が古い. AVX2 ビルドの代わりに `noavx` ビルドを取得 |
| 応答が文字化け | model file が 7-bit ASCII 想定. UTF-8 対応の World series を使う |
| latency が秒 1 トークン以下 | 別プロセスが CPU を奪っている. `Get-Process | Sort-Object CPU -Descending | head` で確認 |
| `Connection refused` to 8080 | server.exe 未起動. 別ウィンドウで起動 |
| llive 経由で 404 | `LLIVE_RWKV_MODEL` が rwkv.cpp の id と不一致. `/v1/models` の id を再確認 |
| 日本語応答の質が低い | RWKV-7 World 1.5B → 3B / 7B にサイズアップ |

---

## 7. 案 A (Mamba 7B) を CPU only で試す場合の現実

参考までに、Mamba 7B を CPU only で動かした場合の **公開報告ベース想定値**
(Reddit /r/LocalLLaMA / Hugging Face モデルカード / llama.cpp issue 等の
報告から読み取った参考値、本リポジトリ側の実機ベンチは未取得):

| サイズ | xs latency | s latency | 実用判定 |
|---|---|---|---|
| Codestral-Mamba 7B Q4 | ~30-60 秒 | ~3-5 分 | **非実用** |
| Codestral-Mamba 7B Q3 | ~20-40 秒 | ~2-4 分 | △ |

**注意 (honest disclosure)**: 上記は本リポジトリ側の実測ではない. 個別
ハードウェアでは結果が大きくぶれるので、自分の PC で `llive.benchmark.low_spec.run_matrix`
を回して xs/s を実測してから判断を確定してください.

→ 公開情報を見る限り **GPU 無し環境で Mamba 7B はほぼ動かない**.
RWKV 軽量モデルを優先する判断と整合.

---

## 8. 関連 docs

- `ROADMAP.md` §0.2 (本ディレクトリ) — CPU only 性能目標
- `COMPARISON.md` (本ディレクトリ) — 案 E の評価詳細
- `docs/setup/ollama-company-setup.md` — Ollama 経由パターン (GPU 有り想定)
- `docs/setup/llama-server-company-setup.md` — llama-server 経由パターン

## 改訂履歴

- 2026-05-18 — draft v0.1 作成 (GPU 無し PC を primary deploy 環境とする
  方針確定 + RWKV-7 World series サイズ別ガイド + 期待値テーブル)
