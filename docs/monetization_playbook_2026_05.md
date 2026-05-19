# FullSense 収益化 実践 Playbook (2026-05-19)

> `requirements_v0.9_growth_automation.md` の収益化想定 (粗試算) を
> **「具体的にどう動かすか」**レベルまで掘り下げた実務 playbook.
> 個人開発者 1 人 + AI 自動化 (llgrow) を前提.
>
> **重要**: 収益化は **簡単ではない**. 本書は楽観論ではなく、各チャネル
> の **障壁・失敗パターン・時間 ROI** を honest disclosure する.

## 全体俯瞰: 10 チャネル × 難易度マトリクス

| # | チャネル | 月収目安 (現実) | 立ち上げ時間 | 維持時間 | 難易度 | llgrow 親和性 |
|---|---|---|---|---|---|---|
| 1 | **GitHub Sponsors** | ¥1k-50k | 1 日 | 0.5h/週 | 低 | ◎ |
| 2 | **Buy Me a Coffee** | ¥0-10k | 30 分 | 0h | 低 | ○ |
| 3 | **note 有料記事** | ¥0-20k | 1 日 | 5h/月 | 中 | ◎ |
| 4 | **Zenn Books** | ¥0-30k | 2 週間 | 月 1 冊 | 中 | ◎ |
| 5 | **Qiita / dev.to** | ¥0 (認知) | 30 分/記事 | 3h/週 | 低 | ◎ |
| 6 | **YouTube 広告** | ¥0-10k (1k 登録後) | 6 ヶ月 | 10h/週 | 高 | ○ |
| 7 | **Commercial license** | ¥50k-500k/契約 | 1 ヶ月 | 月 5h | 高 | △ |
| 8 | **個別コンサル** | ¥10k-100k/h | 3 ヶ月 | 月 10h | 中 | △ |
| 9 | **企業セミナー** | ¥100k-500k/回 | 6 ヶ月 | 1 回/月 | 高 | △ |
| 10 | **受託開発** | ¥3M-10M/案件 | 6-12 ヶ月 | 月 80h | 最高 | × |

「llgrow 親和性」◎ = AI 自動化で大半カバー、○ = 一部自動化、△ = 人間
中心、× = AI 自動化困難.

## 実践順序 (推奨)

### Sprint 0: 今週 (¥0、所要 2-3 時間)

#### 0.1 GitHub Sponsors セットアップ (1 時間)

1. <https://github.com/sponsors> にアクセス
2. "Join the waitlist" → 個人開発者プロフィール記入
   - 名前 / 国 / 開発分野 (AI / ML)
   - 受領通貨: JPY (Stripe 経由で日本円)
3. **税務情報** (重要):
   - 個人事業主 開業届を **税務署に出す** (国税庁 e-Tax で 15 分、無料)
   - "事業の概要" 欄に「ソフトウェア開発、技術記事執筆、コンサルティング等」
   - 開業届控えを保存 (Sponsor 受領時の経費計上に必要)
4. Tier 設定 (推奨):
   - ¥500/月: Bronze (Discord 招待)
   - ¥2,000/月: Silver (月次 digest + GitHub README 名前掲載)
   - ¥10,000/月: Gold (個別 30 分セッション/月)
   - ¥50,000/月: Platinum (企業 logo 掲載、優先サポート)
5. **README に link を追加** (即効性高):
   ```markdown
   <a href="https://github.com/sponsors/furuse-kazufumi">
     <img src="https://img.shields.io/badge/Sponsor-FullSense-EA4AAA?logo=githubsponsors" />
   </a>
   ```

**現実の落とし穴**:
- 待機リストが 1-4 週間
- 最初の 3 ヶ月は ¥0-5,000 程度が普通 (大量の sponsor が湧くわけではない)
- 「期待しすぎない」が一番のメンタル防衛

#### 0.2 Buy Me a Coffee (30 分)

- <https://buymeacoffee.com/> でアカウント
- README に widget 追加
- 単発 ¥500 寄付を気軽に受けられる
- 「コーヒー一杯分」の心理的閾値が低い

#### 0.3 開業届 (税務) — 必須事前作業

GitHub Sponsors / note / YouTube 等で **年間 ¥20 万超** の所得が出ると
個人事業主 開業届と確定申告が必要. 先に出しておく.

```
1. e-Tax (国税庁) または freee 開業 / マネーフォワード開業 で 15 分
2. "個人事業の開業・廃業等届出書" を提出 (PDF or 紙提出)
3. 屋号 (任意): "FullSense" または個人名
4. 開業日: 今日 (遡及不可)
5. 青色申告承認申請書 (オプション、控除 ¥65 万、絶対やるべき)
```

freee 開業: <https://www.freee.co.jp/kaigyou/>
e-Tax: <https://www.e-tax.nta.go.jp/>

**インボイス制度** (2023-10-01〜) は売上 ¥1,000 万未満なら任意. 当面は
登録不要 (登録すると消費税納付義務発生).

### Sprint 1: 1 ヶ月 (¥10k-30k 目標、所要 月 20-30 時間)

#### 1.1 note 有料記事 (1-2 週間)

- 既存 Qiita 記事 (M8.x / Cognitive Mesh / FullSense 哲学等) を note 形式に整理
- **無料記事** 5-10 本で foundation 作る (まず読者を集める)
- **有料記事** 1 本目: 「FullSense 設計の全体像」¥980 で投稿
- 価格帯: ¥100-500 が読まれやすい、¥1,000+ は読者層が変わる
- メンバーシップ ¥500/月 を 6 ヶ月後を目処に解放

**llgrow 連携**: GROW-01 (Content Generator) が下書きを生成し、人間
最終承認で投稿

**現実の落とし穴**:
- 「有料記事 1 本で ¥10 万」は非常に稀
- 月 ¥5,000 が現実線 (¥980 × 5 部 = ¥4,900)
- 累積で読まれるので、半年-1 年継続が前提

#### 1.2 Zenn Books (2-4 週間)

- 既存 docs (cognitive_mesh / M8.x / on-prem AI) を 1 冊の Zenn Book に
- 価格: ¥500-3,000
- 構成: 序章 / 8-12 章 / 終章 + 付録
- スコープ: 「FullSense 入門 — on-prem AI を 1 人で作る」
- 公開後は SNS で告知 + Qiita 記事との相互リンク

**現実の落とし穴**:
- 1 冊書くのに 40-80 時間 (llgrow GROW-01 で短縮可能 + 人間 review 必須)
- 売れる本: 「具体的に動くコード」+ 「失敗談」が含まれるもの
- 売れない本: 「理論先行」「抽象的」

#### 1.3 SNS 連動 (継続)

- X (Twitter): 1 日 1-3 post (技術 hint + 進捗) → llgrow GROW-01
- LinkedIn: 週 1 post (英語、企業向け) → 既存 [[feedback-linkedin-translation-jp-only]]
  方針: 日本語 + 組込翻訳で OK
- Discord (FullSense community): まず GitHub Sponsors Tier の特典として開設

### Sprint 2: 3 ヶ月 (¥30k-100k 目標、所要 月 30-50 時間)

#### 2.1 YouTube 立ち上げ (6 ヶ月超かかる)

**収益化条件**: 登録 **1,000** + 過去 12 ヶ月の総視聴時間 **4,000h**
(または Shorts 1000 万再生).

**現実**:
- 0 → 1,000 登録に **平均 6-12 ヶ月**
- 動画 1 本あたり 5-10 時間 (撮影 + 編集) — llgrow GROW-02 で大幅短縮可
- ¥1 視聴 ≈ ¥0.1-0.5 → 1 万再生 = ¥1,000-5,000
- **広告収益単独で生活費は無理**. 認知拡大 → 他 channel への流入が本筋

**推奨コンテンツ**:
- 「llive M8.x 実装 ライブ」(asciinema → 動画化)
- 「on-prem LLM ベンチ honest disclosure シリーズ」
- 「FullSense vs 大手 (Claude / GPT) 公平比較」

#### 2.2 個別コンサル (¥10k-100k/h)

- LinkedIn / connpass / Twitter で「on-prem AI 導入相談 30 分 ¥10,000」と
  明示的に提供
- 最初の 3 件は無料 → 事例化 → 価格上げる
- 案件サイクル: 月 2-5 件 = ¥20k-500k

**現実の落とし穴**:
- リードジェネレーションが最大の障壁
- 既存ネットワークが効く (前職 / SNS フォロワー / コミュニティ)
- 1 件あたり前後合わせて 3-5 時間 (準備 + 実施 + フォロー)

### Sprint 3: 6 ヶ月 (¥100k-500k 目標、所要 月 40-60 時間)

#### 3.1 Commercial license (¥50k-500k/契約)

- llmesh-suite の Apache-2.0 + Commercial dual license の **Commercial 条項**
  を実運用化
- ターゲット: 規制業界 IT 部門 (金融 / 製造 / 医療 / 公共)
- 価格 (案):
  - スタータ: ¥50,000/年/サイト (1-10 ユーザ)
  - チーム: ¥200,000/年/サイト (10-100 ユーザ)
  - エンタープライズ: ¥500,000-2,000,000/年 (要相談)
- 商標出願済 (Sprint 1 中に並行) + NOTICE / TRADEMARK.md を整備

**現実の落とし穴**:
- 法人向け契約は契約書レビュー 2-3 週間
- 既存実績 (公開事例) がないと話が進まない
- 個人事業主のままだと「法人格がない」で弾かれる → 法人成り検討

#### 3.2 企業セミナー / 招待講演 (¥100k-500k/回)

- 月 1-2 回が現実線
- リードジェネレーション: SES 系 / IT 業界団体 / connpass で実績作り
- スポンサー付きセッション (¥500k+) は 1-2 年後

#### 3.3 法人成り検討

- 売上 ¥500-1,000 万超えたら検討
- 合同会社 (¥6 万、設立簡単) or 株式会社 (¥25 万、信頼性高)
- メリット: 法人税率が低い + 経費範囲広い + 法人契約可能
- デメリット: 社会保険負担 + 決算書作成

### Sprint 4: 12 ヶ月+ (¥500k+/月)

このフェーズに到達するには **複数チャネルの組合せ** が必要:
- Sponsor (継続) ¥30-100k
- note / Zenn (継続) ¥20-50k
- Commercial license 2-3 契約 ¥100-500k
- セミナー / コンサル ¥100-300k
- 計 **¥250-950k/月**

**目標 ROI**: AI 開発環境投資 (¥300k-600k) を **6 ヶ月で回収**.

## 失敗パターン (現実的)

### F1. 「書けば売れる」の誤算

技術記事は **書いてから 6-12 ヶ月後に読まれる**. 即時収益化を期待すると
失敗. 累積前提.

### F2. YouTube 1000 登録の壁

99% の YouTuber は 1000 登録に到達しない. 6 ヶ月続けても登録 200 未満は
よくある. **継続が最大の障壁** で、llgrow で自動化していても**動画は人間
レビューが必須** (顔出し / 声出し).

### F3. Commercial license の「最初の 1 件」

最初の 1 件を取るのに **6-12 ヶ月**. リファレンス事例が無いと話が進まない.
無償 PoC (3-6 ヶ月限定) で事例化 → 本契約、が現実的.

### F4. AI 自動化バレ問題

llgrow で大量に自動投稿すると「AI 量産」と見抜かれて評価下落. **量より
質** + **honest disclosure** を維持. AI 下書き + 人間 final touch.

### F5. 個人ブランドの拡張限界

1 人開発者の発信は **「中の人」依存**. スケールアウトには 法人化 + 共同
創業者 / メンバー獲得が必要だが、これは別問題.

### F6. 課税・会計の落とし穴

- 売上発生から 2 ヶ月以内に開業届 (出してない場合)
- 青色申告承認申請は事業開始から **2 ヶ月以内** (¥65 万控除を逃すと痛い)
- 海外決済 (Stripe US, Patreon, GitHub Sponsors) は **外貨建て** → 為替損益計算
- インボイス未登録だと **法人顧客から敬遠** されることがある (売上 ¥1,000 万
  未満なら影響限定的)

### F7. 過度な期待による燃え尽き

「月 ¥100 万稼ぐぞ」と 3 ヶ月で達成できないと諦める. **6-12 ヶ月の継続**
が前提. [[feedback-session-marathon]] と同じ精神でじっくり.

## 実践チェックリスト (今すぐ / 今週 / 今月)

### 今すぐ (1 時間)

- [ ] 開業届を出す (e-Tax or freee 開業、15 分)
- [ ] 青色申告承認申請書も同時提出
- [ ] GitHub Sponsors waitlist 登録
- [ ] Buy Me a Coffee アカウント作成
- [ ] README に Sponsor / BMC バッジ追加 (4 リポ分)

### 今週 (3-5 時間)

- [ ] 銀行口座 (事業用) を分ける (個人口座と分離)
- [ ] freee 会計 or マネーフォワードクラウド契約 (¥1,000/月、青色申告必須)
- [ ] note アカウント作成 (最初は無料記事 3 本)
- [ ] Zenn アカウント作成 (まず free article)
- [ ] X / LinkedIn プロフィールに "Sponsor me" / "Commercial inquiries" 追加

### 今月 (10-20 時間)

- [ ] note 有料記事 1 本目を公開 (FullSense 全体像、¥980)
- [ ] Zenn Book 目次作成 (1 冊目の章立て)
- [ ] YouTube チャンネル作成 + 動画 1-2 本 (M8.x demo asciinema → mp4 変換)
- [ ] Commercial license の問い合わせフォーム (llmesh-suite README に追加)
- [ ] **商標出願** (Sprint 0 で開業届とセット、別途 ¥48,000)

## 税務・会計の最低限ナレッジ

- **個人事業主 開業届**: 開業から 1 ヶ月以内に税務署 (e-Tax で 15 分)
- **青色申告承認申請**: 開業から 2 ヶ月以内 (¥65 万控除)
- **確定申告**: 翌年 2/16-3/15 (freee で半自動化、¥1,000/月)
- **消費税**: 売上 ¥1,000 万 / 年未満は免税
- **インボイス制度**: 任意 (登録すると消費税納付義務)
- **海外決済**: 為替損益は雑所得 (確定申告で計算)
- **経費**:
  - ハードウェア (GPU / PC / Mac) → 減価償却 (4 年) or 一括 (¥10 万未満)
  - クラウド / SaaS / 通信費 → 全額経費
  - 自宅按分 (家賃 / 電気代) → 業務使用比率 30-50% 程度
  - 書籍 / セミナー参加費 → 全額経費
  - 商標出願料 (¥48,000) → 開業費 or 雑費

## llgrow との接続点

| llgrow 要件 | 関連収益チャネル |
|---|---|
| GROW-01 (Content Generator) | note / Zenn / Qiita / X / LinkedIn |
| GROW-02 (Video Generator) | YouTube |
| GROW-04 (Engagement Responder) | 全 channel のコメ返信 |
| GROW-05 (KPI Dashboard) | 月次収支 + 各 channel ROI 比較 |
| GROW-07 (Sponsor Management) | GitHub Sponsors / Patreon / BMC |
| GROW-08 (Press / Outreach) | 企業セミナー / Commercial license リード |

**llgrow を作る順序**:
1. GROW-05 (KPI Dashboard) を最初に作る — 「測れないものは改善できない」
2. GROW-01 (Content Generator) — 記事系を半自動化
3. GROW-07 (Sponsor Management) — Sponsor 増えてきてからで OK
4. GROW-02 (Video Generator) — GPU 環境後

## 結論: 1 行で

> 収益化は **「3-6 ヶ月の継続 + 複数チャネルの組合せ + 人間最終承認**」
> が前提. AI 自動化 (llgrow) は **効率化** であり、**魔法ではない**.
> [[feedback-benchmark-honest-disclosure]] と同じ精神でじっくり.

## 関連

- `requirements_v0.9_growth_automation.md` — llgrow 全要件 + リスク章
- `ai_dev_env_2026_05.md` — AI 開発環境投資
- `docs/legal/trademark/CHECKLIST_2026_05.md` — 商標出願 (¥48,000)
- portal `docs/spinoff_ideas_2026_05.md` — vertical カタログ
- memory: [[feedback-publishing-workflow]] / [[feedback-articles-pause]] /
  [[feedback-publication-channels]] / [[feedback-session-marathon]] /
  [[feedback-response-timing]]
