# llive 要件定義 v0.H — Mascot / Brand Identity

**Drafted:** 2026-05-22
**Status:** **要件登録 (構想)** — 実装はブランディング段階で.
**Type:** Branding / PR / OSS identity asset
**Trigger:** ユーザー指摘 (2026-05-22):

> https://self.systems/ai-news-app-furuseai-gpt/ 昔からこのキャラクターが気になってますね。私の名前と被っていて AI を前面に出しているからです。今の llive ってアスキーアートですが、禿キャラなので・・・正直かわいくないですよね。

---

## 1. 背景 — 既存キャラ「古瀬あい」との衝突

### 1.1 リファレンス: SELF株式会社「古瀬あい (こせあい)」

- SELF アプリの AI キャラクター (癒し / 感情共有型)
- **2017 年実装** (先行 9 年)
- 運営: **SELF株式会社** (`self.systems`)
- 仕様: 無課金 3 日で記憶消失 / 月額 580 円で記憶保持
- 2023-10 ChatGPT 連携、145 万 DL 規模
- 出典: `https://self.systems/ai-news-app-furuseai-gpt/`

ユーザー名 (furuse) と被るため、llive が「古瀬」系の名前を採用すると **完全に衝突**. 既存ユーザーは混乱、商標的にも不利.

### 1.2 現状 llive のキャラ

- CLI 起動時の **アスキーアート (ASCII)** — ユーザー曰く「禿キャラで正直かわいくない」
- 普及 PR ([[project_f25_demo_polish]] / [[project_github_animated_svg]]) で「動きで魅せる」「採用ファネル先頭」が求められているが、現状キャラはこれに貢献していない

---

## 2. 設計目標

### 2.1 ブランド衝突回避

- 「古瀬」「あい」「FuruseAI」とは **名前で被らない** ブランディング
- ユーザー個人名 (furuse) と llive を **直接接続しない** (個人依存ブランドはスケールしない)
- 商標的にもグローバル展開可能なネーミング ([[project_fullsense_brand.md]] 親 brand 整合)

### 2.2 「禿キャラ」からの脱却

- 単純に「可愛さ」を追加するのではなく **llive の architecture を擬人化**:
  - 4 層メモリ → 4 色のリング or 4 つの羽 / 装飾
  - 10 思考因子 → 10 個のリボン / 装飾光点
  - Approval Bus → 「審査つき」のサイン / 帽子
  - 派生集団進化 → 複数の小さな自分が周りにいる "swarm" 演出
- 機能を視覚化する形で「内側設計が一目でわかる」キャラ

### 2.3 ASCII / SVG / 立体の多階層展開

- **CLI 起動 (現状)**: ASCII art — 軽量版マスコットを ASCII で再構成
- **README / docs hero**: 静的 SVG / animated SVG ([[project_github_animated_svg]])
- **F25 demo / 動画**: アニメーション (rive / lottie / SVG SMIL)
- **将来**: VRM / Live2D / Spine (llove ↔ llive 連携で実機表示)

---

## 3. ネーミング候補 (棚卸し)

| 候補 | 由来 | pros | cons |
|---|---|---|---|
| **lily** (リリィ) | l-l-i-v-e + 花 | 短い / 国際的 / 可愛い | 一般語、SEO 弱 |
| **Liv** | llive 短縮 | 短い / 名前っぽい | Apple Liv 等競合 |
| **livia** | llive + name | 名前らしい / 国際的 | Olivia 系統と被る |
| **livu** | llive + AI | 独自 / 検索ユニーク | 響きが弱い |
| **llio** (りお) | l-l-io | 短い / 日本/海外両立 | Mario と一文字違い |
| **lle** (れ / Le) | l-l-e (last char of llive) | 極短 / 抽象的 | 短すぎて検索難 |
| **lova** | llive + love + a | 親しみやすい | 既存ブランド多数 |

**選定方針**:

1. 同名 OSS / 商標を事前検索 (GitHub / NPM / PyPI / USPTO / IPSDL)
2. ドメイン取得可能性 (`.dev` / `.ai` / `.app`)
3. **ASCII で書ける** (CLI で表示しやすい)
4. 4-6 文字以内推奨
5. 日本語と英語両方で違和感がない

→ 一次調査後 (NMG-01) に top 3 を絞り、ロゴ案も並走作成.

---

## 4. 設計柱

### 柱 A: ビジュアル要素 (Visual DNA)

- **4 色 palette** (4 層メモリ対応):
  - sensory: `#5dd1ff` (cyan)
  - episodic: `#7ee787` (green)
  - semantic: `#ffd166` (yellow)
  - parameter: `#ef476f` (magenta)
- 補助色: `#c084fc` (purple, Approval Bus) / `#0e1426` (背景)
- **形状要素**:
  - **環**: 4 リング (memory layers) を背景に
  - **触角 / アンテナ**: 思考因子の vector — 10 本の細い線が周囲を巡る
  - **顔**: 表情はシンプル (2 つの目 + 小さい口)
  - **ボディ**: 小柄、抽象的、人型 or マスコット型 (ぬいぐるみのような曖昧形)

### 柱 B: ASCII レンダリング (現 CLI 互換)

新キャラを ASCII で再描画する仕様:

- 縦 16 行 × 横 32 文字以内
- Unicode 罫線 (┌─┐│└─┘ + ◯ ●) を活用
- 色 ANSI escape 対応 (`\x1b[36m` 等) と plain fallback
- 既存 `.startup-output` / banner と置き換え可能なドロップイン

### 柱 C: 静的 SVG (README / docs hero)

- viewBox 800x240 (hero bar) と 256x256 (avatar square) の 2 解像度
- 透過背景 (記事 / portal に貼りやすい)
- raw URL で参照 ([[project_github_animated_svg]] 既存の埋め込みパターン準拠)

### 柱 D: Animated SVG (animation + branding)

- SMIL only (no script、Qiita / Mintlify / Pages 互換)
- 4 つのメモリリングが周回 / 10 思考因子が点滅 / Approval Bus サイン が定期点灯
- 既存 #24-02〜#24-08 hero SVG ([[project_github_animated_svg]] queue 投入済) と整合する color palette

### 柱 E: License + IP

- **ロゴ + キャラデザイン本体** は CC BY-SA 4.0 (商業利用可、改変は同条件で公開)
- **キャラのコード/SVG ソース** は llive 本体と同じ Apache-2.0 + Commercial dual ([[project_llive_v06_legal]] 準拠)
- 商標: 採用候補 top 3 が決まったら llive 配下で **JP / US / EU 出願 draft** ([[project_fullsense_brand]] と同 lane)

---

## 5. 実装ロードマップ (要件のみ、実装は次フェーズ)

| ID | 内容 | 依存 |
|---|---|---|
| NMG-01 | ネーミング 7 候補の重複検索 + top 3 選定 | — |
| NMG-02 | 商標 / ドメイン取得可能性チェック | NMG-01 |
| NMG-03 | top 3 候補それぞれにロゴ + マスコット ラフ案 (3 案 × 3 ロゴ = 9 試作) | NMG-01 |
| NMG-04 | ユーザー選定 + 1 候補に絞る | NMG-03 |
| NMG-05 | ASCII art 版マスコット (`.startup-output` 用) | NMG-04 |
| NMG-06 | Static SVG 版 (hero + avatar) | NMG-04 |
| NMG-07 | Animated SVG (SMIL, README / docs 用) | NMG-06 |
| NMG-08 | F25 demo へキャラ統合 ([[project_f25_demo_polish]]) | NMG-06/07 |
| NMG-09 | 商標出願 draft (JP) | NMG-04 |
| NMG-10 | llove / llmesh / fullsense portal 全体ブランド統一 ([[project_fullsense_brand]]) | NMG-04..09 |

---

## 6. リスクと honest disclosure

| リスク | 影響 | 対策 |
|---|---|---|
| 既存ブランドとの再衝突 (古瀬あい以外にも) | rename ループ | NMG-01/02 で事前 dedup, top 3 並走 |
| キャラ作成は本業外の工数 | スケジュール遅延 | 外注 (Fiverr / 99designs / Skeb) の選択肢を残す |
| ロゴが好みに合わない | 採用ファネル先頭での印象悪化 | ラフ 3 案 × top 3 候補 = 9 案で多様性確保 |
| アスキーアート版が表現力不足 | CLI ユーザー体験低下 | Animated SVG fallback + 簡易 ASCII 両立 |
| 一個人のセンスに依存 | ブランド老朽化 | デザインシステム (color palette + 形状 DNA) を docs 化 |

---

## 6.5 長期ビジョン — Transformer 脱却後のコラボ路線

ユーザー追加指摘 (2026-05-22):

> Transformer アルゴリズムを脱却し普及することが実現した暁には、コラボ路線とか歩めたらいいのになと思います。

短期 (v0.H 〜) と長期で **戦略を分離**:

### 短期 (now 〜 transformer 脱却前)

- 「古瀬あい」とは **完全に切り離す**. 名前 / ビジュアル / マーケティング上の被りを排除
- llive は独自ブランドで普及ファネル (#24 series / animated SVG / 採用ファネル先頭) を整備
- 出典: `https://self.systems/ai-news-app-furuseai-gpt/` は **競合ではなく将来パートナー候補** として位置づけ、敵対的態度は取らない

### 長期 (Transformer 脱却が普及した暁に)

- llive non-transformer backend ([[#24-06]] Mamba / Jamba / RWKV / Diffusion) が普及 → llive の存在感が立つ
- そのタイミングで **SELF株式会社 (古瀬あい) とコラボ路線** を歩む可能性:
  - 古瀬あい × llive の **連携 SDK** (古瀬あい個性層を llive 4 層メモリで強化)
  - llive 4 層メモリ ⇄ 古瀬あい 課金型記憶 のブリッジ (record / replay)
  - 共通 brand event ("Transformer 後の AI" コラボ keynote)
  - 名前衝突問題は「ファミリーキャラ」「兄弟キャラ」位置づけで解決
- 進め方:
  1. llive non-transformer backend が普及指標 (production 採用 / DL 数 / 学術引用) で **明確な実績** を持つまでは静観
  2. その時点で **公式に approach**: 競合ではなく complementarity を提示
  3. 商標 / ライセンス上の **dual-track** を維持 (協業 OK / 独立運営も OK)
- 失敗時: コラボ不成立でも llive 単独で立てる (依存しない)

### How to apply

- v0.H 命名選定 (柱 3) では **「古瀬あい」と並んでも違和感がない別名** を選ぶ (兄弟関係を作りやすい命名)
- 戦略的に「敵」化しない: 記事 / SNS 発信で SELF株式会社 や古瀬あいを **批判的に言及しない**
- 長期 KPI: Transformer 脱却関連の milestone (non-transformer backend production 採用 N 社 / 学術論文 M 本) を年次計測

## 7. 連動 memory / docs

- `[[project_llive_mascot_design]]` — 本要件の memory 側
- `[[project_fullsense_brand]]` — 親 brand FullSense との整合
- `[[project_github_animated_svg]]` — Animated SVG 普及戦略 (キャラ SVG はその一環)
- `[[project_f25_demo_polish]]` — demo にキャラを組み込む
- `[[project_llive_v06_legal]]` — ライセンス整合
- `[[feedback_publishing_workflow]]` — GitHub / PyPI 公開時に hero SVG を README に貼る

---

> Drafted by Claude (Opus 4.7) on 2026-05-22.
> ユーザー個人名 (furuse) は llive ブランドと **意図的に切り離す**. 「古瀬あい」競合と区別、長期的にユーザー離脱でも残るブランドへ.
