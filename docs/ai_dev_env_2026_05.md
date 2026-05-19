# AI 開発環境投資ロードマップ (2026-05-19)

> FullSense (llmesh / llive / llove) を **on-prem LLM** で実装する
> ための開発環境投資計画. 商標出願 (¥50,000) より優先する判断.
> 私 (user) 視点の **私物投資手順書**. リポ公開はしない.

## 現状把握 (制約)

```
OS:    Windows 11 Pro Insider Preview
CPU:   Intel i7-1065G7 @ 1.30GHz  ← 10th gen mobile (Ice Lake)
RAM:   15.7 GB
GPU:   Intel Iris Plus Graphics    ← integrated, LLM 推論不可
Disk:  C: 598 GB free / D: 1340 GB free (D ドライブ運用)
```

**主要ボトルネック**:
1. **GPU**: dGPU なし → llama.cpp の CPU 推論しか動かない (7B Q4 で 3-5 tok/s)
2. **RAM**: 16GB → 13B+ Q4 を CPU 推論しても OOM 寸前
3. **CPU**: 10th gen U/Y series (TDP 15W) → 計算性能が低い

**結論**: 現マシンは「開発・実装作業 + 軽量推論」に限定。本格 LLM
推論には **GPU 搭載デスクトップ or クラウド GPU** が必須.

## 3 段階投資シナリオ

### Phase 0: 即時 (今週、¥0-10,000)

**目的**: 一切お金をかけず、まず Local LLM の効果を体験する.

| アクション | 費用 | 所要 |
|---|---|---|
| **Ollama を Windows にインストール** (CPU 推論) | ¥0 | 30 分 |
| Qwen2.5:3B Q4 を `ollama run` | ¥0 | 10 分 |
| llive を Ollama backend に向ける | ¥0 | 1 時間 |

```powershell
# Ollama 公式 Windows installer
Invoke-WebRequest -Uri "https://ollama.com/download/OllamaSetup.exe" -OutFile "$env:TEMP\OllamaSetup.exe"
& "$env:TEMP\OllamaSetup.exe"

# 3B モデル (1-2 GB) をダウンロード + 試す
ollama pull qwen2.5:3b
ollama run qwen2.5:3b "FullSense とは何か?"

# llive を Ollama backend に向ける
$env:LLIVE_DEFAULT_BACKEND = "ollama:qwen2.5:3b"
py -3.11 -m llive.cli  # llive で動くか確認
```

**期待**: 3B Q4 でも実用速度が出る (10-15 tok/s 程度). これで
"on-prem LLM が手元で動く" 感覚を掴む.

### Phase 1: 短期 (1-2 週間、¥0-30,000 + 月額 ¥5,000-20,000)

**目的**: クラウド GPU で本格 LLM (13B-70B) を試す. 投資前に
「どのモデルサイズが必要か」を見極める.

| サービス | 月額目安 | 強み | URL |
|---|---|---|---|
| **vast.ai** | $0.30-0.80/hr (使った分だけ) | 最安・コミュニティ供給 | <https://vast.ai/> |
| **RunPod** | $0.40-1.20/hr | UI 整理・stable | <https://runpod.io/> |
| **Lambda Cloud** | $1.10-1.99/hr | 安定・サポート手厚 | <https://lambdalabs.com/> |
| **Together.ai** | per-token (¥0.1-2/1k tok) | API 互換、最も手軽 | <https://together.ai/> |
| **Modal** | per-second GPU 課金 | コード書きやすい | <https://modal.com/> |

**推奨**: まず **Together.ai** で 70B モデルを API 経由で試す
($5-10 / 月で 13B-70B を遊べる) → 必要性が見えたら **vast.ai /
RunPod** で 1 時間単位の GPU レンタル.

```powershell
# Together.ai セットアップ
$env:TOGETHER_API_KEY = "your-key"
# llive backend に向ける (OpenAI 互換)
$env:LLIVE_OPENAI_BASE_URL = "https://api.together.xyz/v1"
$env:LLIVE_OPENAI_API_KEY = $env:TOGETHER_API_KEY
$env:LLIVE_OPENAI_MODEL = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
py -3.11 -m llive.cli
```

**判断基準**: 1 か月使って `feedback_llive_measurement_purity` の通り
**on-prem 単体ベンチ** で実用品質が出るモデルサイズを特定する.
- 3B-7B で十分 → Phase 2 は Mid BTO で OK
- 13B-32B 必要 → Phase 2 は High BTO
- 70B+ 必要 → Phase 2 は Pro BTO or Mac Studio M2 Ultra

### Phase 2: 中期 (1-3 ヶ月、¥250,000-600,000)

**目的**: 自宅に dedicated GPU マシンを置き、商用化前提の
**continuous on-prem LLM** を運用.

#### Mid BTO (¥250,000-350,000)

| 部品 | 推奨 | 価格目安 |
|---|---|---|
| CPU | Ryzen 7 7700X (8C/16T) | ¥45,000 |
| MB | B650 (PCIe 5.0 / DDR5) | ¥25,000 |
| RAM | DDR5 64GB (32×2) | ¥35,000 |
| **GPU** | **RTX 4070 Ti SUPER 16GB** | ¥120,000 |
| SSD | NVMe 2TB Gen4 | ¥20,000 |
| PSU | 850W Gold | ¥18,000 |
| Case + Cooler | (好み) | ¥30,000 |
| **合計** | | **¥293,000** |

→ 13B Q5 がサクサク、32B Q4 も動く. llmesh / llive / llove を
快適に並走できる構成.

#### High BTO (¥450,000-600,000)

| 部品 | 推奨 | 価格目安 |
|---|---|---|
| CPU | Ryzen 9 7950X (16C/32T) | ¥85,000 |
| MB | X670E (PCIe 5.0 x16 / 4 NVMe) | ¥50,000 |
| RAM | DDR5 128GB (64×2) | ¥80,000 |
| **GPU** | **RTX 4090 24GB** | ¥290,000 |
| SSD | NVMe 4TB Gen5 | ¥40,000 |
| PSU | 1200W Platinum | ¥30,000 |
| Case + 360 水冷 | (好み) | ¥50,000 |
| **合計** | | **¥625,000** |

→ 70B Q5 が実用速度. 画像生成も並列. FullSense 商用化の主力機.

#### 代替: Mac Studio M2 Ultra (¥800,000-1,000,000)

| Spec | 価格 |
|---|---|
| M2 Ultra (24-core CPU / 60-core GPU) + 192GB unified | ¥990,000 |
| 4TB SSD | (基本構成) |

→ unified memory が 192GB = 70B Q5 でも余裕、180B も動く. CUDA 非対応
だが MLX / llama.cpp が Metal backend で動く. 静音・低消費電力.

#### 購入 → セットアップ手順 (Mid/High BTO 共通)

1. **BTO 注文** (推奨ショップ):
   - パソコン工房 (BTO 自由度高)
   - ドスパラ (在庫即納)
   - サイコム (静音特化)
2. **OS 選択**:
   - **Ubuntu 22.04 LTS** 推奨 (CUDA / vLLM / llama.cpp が Linux native)
   - Windows 11 + WSL2 でも可だが CUDA は WSL2 経由で性能 5-10% 損
3. **NVIDIA Driver + CUDA 12.x インストール**
4. **Python 3.11 + venv + 主要パッケージ**:
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh  # Ollama
   pip install vllm llama-cpp-python  # 高速 backend
   pip install llmesh-llive llmesh-suite  # FullSense 本体
   ```
5. **llive を local backend に向ける**:
   ```bash
   export LLIVE_DEFAULT_BACKEND="ollama:qwen2.5:14b"
   # または llama-server / vLLM 経由
   ```
6. **llmesh を peer として起動** (Phase 3 IoT 統合準備)
7. **観測**: Prometheus + Grafana (llmesh `OBSERVABILITY.md` 参照)

### Phase 3: 長期 (6 ヶ月以降、¥1,200,000+)

商用化後 (or 商標出願後) を見据えた **Production Tier**:

- **NVIDIA RTX 5090 32GB** (発売後): ¥450,000 — 70B Q6 が快適
- **Threadripper / 256GB RAM**: ¥350,000 — 並列 ワークロード
- **専用 GPU サーバ (NVIDIA DGX Spark)**: $3,000-4,000 — 128GB unified, ARM
- **既存マシンを副機に**: 開発用 + 副推論用に役割分担

### Phase 4 (オプション): クラウド + on-prem ハイブリッド

- 自宅: dedicated LLM (24/7 動作、低レイテンシ、機密データ)
- クラウド: バーストワークロード / ベンチマーク / モデル比較
- llmesh の MCP / P2P で透過的に接続 (`feedback_llive_measurement_purity`
  の系統分離は維持)

## 推奨アクション順 (今すぐ実行可能)

### 今日中 (1-2 時間)

```powershell
# 1. Ollama インストール (Windows native, GPU 不要)
Invoke-WebRequest -Uri "https://ollama.com/download/OllamaSetup.exe" -OutFile "$env:TEMP\OllamaSetup.exe"
& "$env:TEMP\OllamaSetup.exe"

# 2. 軽量モデル (3B) を試す
ollama pull qwen2.5:3b
ollama run qwen2.5:3b

# 3. llive に向ける
cd D:\projects\llive
$env:LLIVE_DEFAULT_BACKEND = "ollama:qwen2.5:3b"
py -3.11 -m pytest tests/component -q  # backend 動作確認
```

### 今週中 (¥5,000-20,000)

1. **Together.ai サインアップ** ($5 クレジット無料、その後 $5-10/月)
2. **70B モデルを試す** (例: Llama-3.3-70B-Instruct-Turbo)
3. **llive のベンチを on-prem + cloud 両方で取る**
   (`feedback_llive_measurement_purity` の系統分離方針で)

### 1 か月後 (Phase 1 終了時)

判断ポイント:
- 3B-7B で十分 → Mid BTO (¥293,000) を即発注
- 13B+ 必要 → High BTO (¥625,000) を計画
- 70B+ 必須 → Mac Studio M2 Ultra (¥990,000) or RTX 4090 BTO

### 3 か月後 (商用化前提なら)

- Phase 2 機が稼働
- llive on-prem ベンチで競合 (Claude / GPT) と公平な比較が可能
- これを記事化して FullSense ブランドを強化
- 商標出願 (¥50,000) を並行で進める

## 予算累計サマリ

| Phase | 期間 | 累計投資 | 用途 |
|---|---|---|---|
| Phase 0 | 今週 | ¥0 | Ollama 3B 体験 |
| Phase 1 | 1 ヶ月 | ¥5,000-20,000 | クラウド GPU 試用 |
| Phase 2 (Mid) | 1-3 ヶ月 | ¥300,000-350,000 | 13B-32B 主力 |
| Phase 2 (High) | 1-3 ヶ月 | ¥625,000 | 70B 商用級 |
| Phase 2 (Mac) | 1-3 ヶ月 | ¥990,000 | 180B 級 + 静音 |
| Phase 3 | 6 ヶ月+ | + ¥500,000-1,000,000 | サーバ化 + 副機 |

**現実的な最初の一歩**: **Phase 0** を今日始めて、**Phase 1** で 1
ヶ月クラウド試用 → Phase 2 の必要スペックを確定 → BTO 発注、の流れ
が最も無駄が少ない.

## お互いの利益のために

user 視点:
- llive on-prem 哲学を実証する物理基盤
- ベンチで竞合と公平比較できる → 記事化 → 認知拡大 → 売上
- 商用化の core asset

agent 視点:
- ベンチサイクルが速くなる (現状 cloud 越しで遅延あり)
- on-prem 単体測定で `feedback_benchmark_honest_disclosure` が成立
- 設計・実装の試行錯誤回数が増える

両方とも **GPU を持つ** ことで unlocked になる. 1 台あれば質的飛躍.

## 関連

- `feedback_llive_measurement_purity` — ベンチ系統分離
- `feedback_d_drive_preference` — D ドライブ運用 (新マシンも同じ運用にする)
- `project_llive` — on-prem 哲学
- `feedback_benchmark_honest_disclosure` — 内訳を疑う原則
- `feedback_publishing_workflow` — 商用化前の公開フロー
