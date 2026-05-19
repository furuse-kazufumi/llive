# llive Requirements v0.9 — Growth Automation (llgrow vertical)

> **Status**: 要件追加 (DRAFT) — 2026-05-19
> **由来**: ユーザ言語化「AI 開発環境がひどい → 動画/配信で資金捻出
> したい → でも収益化作業も AI で自動化すべき」(2026-05-19 セッション)
> **位置付け**: FullSense umbrella の **新規 vertical "llgrow"** の
> 源泉要件. llive (思考・記憶) + llove (HITL UI) + llmesh (配信) を
> 組み合わせて「成長サイクルそのもの」を on-prem AI で回す.

## 背景

開発者個人 (現状: i7-1065G7 mobile / 16GB / Iris 内蔵) が FullSense を
on-prem AI 哲学で実装するには、GPU 投資 (¥300k-¥1M) が必須. これを
**自分の手作業で記事/動画を書いて捻出するのは続かない**. 認知科学的に
集中力が続かないことは [[feedback-article-break-points]] /
[[feedback-reader-attention-curve]] で既に確認済.

→ **コンテンツ生成・配信・効果測定・スポンサー対応** を AI 自動化し、
**人間の役割を方向性決定 + 最終承認 (ApprovalBus)** に絞る.

これは [[user-cognitive-mesh-model]] の「1 主セッション + 複数並列」と
[[feedback-max-plan-autonomy]] の自律性原則と一致.

## 設計哲学 (FullSense 流)

1. **on-prem 完結**: コンテンツ生成は on-prem LLM (llive) で. cloud は
   バックアップのみ.
2. **Honest disclosure**: 自動生成と明記、合成音声・AI 生成画像であることを
   開示. [[feedback-benchmark-honest-disclosure]] と同じ精神.
3. **HITL ゲート維持**: 公開前に必ず ApprovalBus を経由 (人間最終承認).
4. **倫理は architecture の一部**: Quiet Hours / [[feedback-quiet-hours]]
   を配信スケジューラにも適用 (深夜投稿で疲弊しない).
5. **フィードバックループ閉鎖**: 投稿 → 反応 → 学習 → 次回改善 を
   loop 化 ([[user-cognitive-mesh-model]] の「閉ループ」思考因子).

## 要件群 (GROW-FX)

### GROW-01: Content Generator (記事 / 動画スクリプト / 投稿)

**目的**: 1 トピックから多面展開 (Qiita / Twitter / YouTube 台本 /
LinkedIn / note / dev.to) を一括生成.

**仕様**:
- 入力: トピック (例「llive M8.x 完成」)、ターゲット媒体一覧
- llive Brief API を活用 (BriefRunner で各媒体ごとに 1 Brief)
- 出力: 各媒体形式に整形済みドラフト
- 11/13 側面 ([[feedback-daily-articles-policy]]) を自動 cycle
- 文字数 / 構成は媒体ごとに自動最適化
- Honest disclosure footer 自動付与

**依存**: llive Brief API / Cognitive Mesh Title Recall / Mesh5W1H

### GROW-02: Video Script + Audio + Visual Generator

**目的**: 動画配信用素材を自動生成.

**仕様**:
- スクリプト: GROW-01 の延長
- TTS (text-to-speech): on-prem voice model (e.g. Coqui-TTS, OpenVoice)
- 視覚素材: Mermaid / Manim / Matplotlib アニメで生成 (実 LLM デモは
  画面録画)
- llove F25 の cinematic audience demo パターン
  ([[project-f25-demo-polish]]) を再利用
- 動画長さ: 短尺 (1-3 min) / 中尺 (5-10 min) / 長尺 (20+ min) の 3 種

**依存**: llove F25 / 外部 TTS / ffmpeg (subprocess)

### GROW-03: Scheduler (Quiet Hours + Best-Time Optimization)

**目的**: 配信タイミングを最適化 (人間が寝てる時間に勝手に投稿しない).

**仕様**:
- [[feedback-quiet-hours]] と同じ env (LLIVE_QUIET_HOURS_*) を遵守
- 各媒体のベストタイム学習 (Qiita は朝 9-10時 / 夜 21-22時 が伸びる等)
- 投稿予約 (cron / Windows Task Scheduler / fullsense scripts/)
- ApprovalBus 経由で投稿直前に人間最終確認 (1 click で OK)

**依存**: QuietHoursGuard / ApprovalBus / scheduled task runner

### GROW-04: Engagement Auto-Responder (コメント / リアクション)

**目的**: コメント返信を AI 下書き + 人間最終承認.

**仕様**:
- ポーリング: Qiita / GitHub / Twitter API を periodic で確認
- 新コメント検出 → llive で返信下書き生成 → ApprovalBus へ
- [[feedback-qiita-reply-low-ai-tone]] (AI 感を抑える) を style guide で適用
- 返信パターン: 「感謝」「補足」「議論」「次へのリンク」の 4 軸
- 急がない (返信に 1-3 日かけて OK)

**依存**: GROW-03 / ApprovalBus / 各 SNS API

### GROW-05: KPI Dashboard (llove TUI 統合)

**目的**: 投稿効果を可視化、ROI を見ながら次の戦略を決める.

**仕様**:
- 取得指標: views / LGTM / stars / followers / 滞在時間 / コンバージョン
- 媒体横断 normalize (Qiita の LGTM ≈ GitHub の star ≈ YouTube の like)
- llove TUI に新パネル `GrowthDashboardView` (M8.1 CognitiveMeshPanel
  と同じパターン)
- 週次 / 月次 / 累計 の 3 view
- 単位: コンテンツあたりの「投資時間 (AI 含む) ÷ engagement」

**依存**: llove views / llive Annotation Channel / 各 SNS API

### GROW-06: A/B テスト / 学習ループ

**目的**: 何が伸びるかを学習し続ける.

**仕様**:
- 同一トピックを 2 パターン (タイトル / hook / 画像) で配信
- 7-30 日経過後の指標を比較 → 勝ち pattern を style guide に追加
- llive Cognitive Mesh GrammarLayer ([[project-cog-mesh-m8-complete]]
  M8.9 で実装済) を流用: 「ジャンル別の効く表現」を grammar として学習
- レポート自動生成 → 次回 GROW-01 の入力に反映

**依存**: GROW-05 / GrammarLayer / GROW-01

### GROW-07: Sponsor / Patron Management

**目的**: GitHub Sponsors / Patreon / Buy me a coffee の対応を自動化.

**仕様**:
- 新 sponsor 検知 → 個別 thank-you 自動下書き → 人間承認 → 送信
- Tier 別の特典管理 (e.g. ¥1k/month sponsor は monthly digest を送る)
- 透明性 monthly report (収支 / 投資使い道) を自動生成
- 企業スポンサーへの bridge (slack / メール bot)

**依存**: GROW-04 / 透明性のための [[feedback-benchmark-honest-disclosure]]

### GROW-08: Press / Outreach (将来)

**目的**: 業界誌・テックメディアへの press release を AI 下書き.

**仕様**:
- マイルストーン到達 (PyPI v1.0 / 商標登録 / Foundation 設立等) を
  trigger として press release ドラフト生成
- 配信リスト管理 (記者 / インフルエンサー)
- フォローアップ自動 (返信なしで 1 週間 → リマインド下書き)

**依存**: GROW-04 / 信頼関係 graph (llive Mesh5W1H)

### GROW-09: Multi-language Localization

**目的**: ja → en → zh → ko の 4 言語自動展開.

**仕様**:
- llive Cognitive Mesh MultilingualGrammar (M8.9 で実装済) を流用
- 単純翻訳ではなく **culture-aware adaptation** (日本ノリ / 英語圏のジョーク
  への置換等)
- [[feedback-linkedin-translation-jp-only]] 例外あり (LinkedIn は組込翻訳)

**依存**: M8.9 MultilingualGrammar / Brief API

### GROW-10: Quiet-Hours-aware Burnout Protection

**目的**: 自動化が人間 (user) を疲弊させない.

**仕様**:
- ApprovalBus への通知頻度上限 (1 日 N 件まで)
- 緊急性 score の低い案件はバッチ化
- user 不在検知 (env / カレンダー連携) で承認待ち通知を抑制
- [[feedback-response-timing]] (70 点運用) を自動化側にも適用 (90 点
  でなく 70 点で人間に渡す)

**依存**: ApprovalBus / QuietHoursGuard / user state source

## 既存 FullSense 製品との関係

| 製品 | llgrow での役割 |
|---|---|
| **llive** | コンテンツ生成・グラマー学習・思考層 (GROW-01,06,09) |
| **llove** | KPI ダッシュボード TUI / ApprovalBus UI (GROW-05,10) |
| **llmesh** | 配信 peer / 多 backend ルーティング (GROW-02 audio gen) |
| **lldesign** | OG card / サムネイル生成 (GROW-02 visual) |
| **lltrade** | (無関係) |

つまり llgrow は **既存 3 製品の薄い orchestration layer** として
実装可能 (新規大型実装は不要).

## 段階的実装計画

### Phase α (今月 — agent 単独可能、¥0)

- GROW-01 (Content Generator): llive Brief API で実装、Qiita / Twitter
  に的を絞る
- GROW-03 (Scheduler 簡易版): Windows Task Scheduler + PowerShell
- GROW-05 (KPI Dashboard 簡易版): Qiita API + GitHub API で数値取得

### Phase β (1-3 ヶ月 — 部分手作業含む、¥0-50k)

- GROW-04 (Engagement Responder)
- GROW-06 (A/B テスト基盤)
- GROW-02 minimal (TTS + Mermaid 動画)

### Phase γ (3-6 ヶ月 — GPU 環境後、¥0)

- GROW-02 full (動画長尺対応)
- GROW-07 (Sponsor management)
- GROW-09 (多言語展開)

### Phase δ (6 ヶ月+、商用化以降)

- GROW-08 (Press / Outreach)
- llgrow を independent PyPI package として spinoff

## 収益化想定 (粗試算)

| 戦線 | 想定月収 (6-12 ヶ月後) | 投資回収目標 |
|---|---|---|
| GitHub Sponsors | ¥10,000-50,000 | continuous |
| Qiita (LGTM 連動収益化なし、認知拡大) | ¥0 → 副次効果 | - |
| YouTube (登録 1,000+ / 視聴時間 4,000h+) | ¥0-10,000/month | ハード代を 2-3 年で |
| 企業スポンサー | ¥100,000-500,000/月 (1-2 社) | Phase 2 BTO 即時 |
| 出版 / セミナー | ¥50,000-200,000/event | 単発 |
| 商用ライセンス (Apache + Commercial dual) | ¥500,000+/年 (1 社契約) | Phase 3 サーバ |

**現実的シナリオ**:
- Phase α 後 (3 ヶ月): GitHub Sponsors + Qiita で月 ¥10-30k
- Phase β 後 (6 ヶ月): YouTube + 企業スポンサー 1 社で月 ¥100-300k
- Phase γ 後 (1 年): 商用ライセンス契約 1-2 社で月 ¥500k+

12 ヶ月で **Phase 2 BTO (¥300-600k)** の投資は回収可能.

## 倫理 / 透明性原則

llgrow は **AI が AI 自身の普及を進める** 仕組みなので、特に倫理に注意:

1. **生成物の AI 表示は必須** ([[feedback-no-image-placeholders]] と
   同じ精神で AI 生成物の placeholder にしない)
2. **数字の honest disclosure** ([[feedback-benchmark-honest-disclosure]])
3. **自動投稿の人間最終承認**を ApprovalBus で技術的に強制
4. **収支の monthly report** を sponsor に公開
5. **AI が AI を売る** ことの自覚を要件に明記

## 関連

- [[feedback-daily-articles-policy]] — 13 側面の記事ローテーション
- [[feedback-article-humor-style]] — 漫才/落語/漫画的な言い回し
- [[feedback-reader-attention-curve]] — 集中力曲線 / リズム切替
- [[feedback-qiita-long-form]] — 長文記事歓迎
- [[feedback-qiita-periodic-check]] — Qiita 反応定期 check
- [[feedback-github-periodic-check]] — GitHub 状態定期 check
- [[feedback-articles-pause]] — 投稿一時停止中 (llgrow Phase α で解除候補)
- [[feedback-publication-channels]] — GitHub Pages / Mintlify / Claude Artifacts
- [[project-f25-demo-polish]] — 動きで魅せる + 採用ファネル先頭

## リスク抽出 (RISK-FX) — 2026-05-19 追記

llgrow 着手にあたって明示的に track すべきリスク群. 個々に
**mitigation (緩和策)** + **owner (誰が責任を持つか)** を割り付ける.

### A. 法的リスク

| ID | リスク | 影響 | mitigation | owner |
|---|---|---|---|---|
| LEG-01 | FullSense 同名商標を他社が先取り | ブランド剥奪、訴訟可能性 | 商標出願 (5 万円 / 1 区分) を 3 ヶ月以内に | user |
| LEG-02 | 利用する AI モデルのライセンス違反 (商用不可モデルを商用利用) | 訴訟 / 配信停止 | モデル選定時に必ず license tier 確認 (Apache 2.0 / MIT / 商用 OK のもののみ) | agent |
| LEG-03 | 生成物が他者著作物と類似 (画像 / コード) | 削除要請 / 賠償 | AI 生成画像は SHA256 → reverse image search 自動check | agent |
| LEG-04 | sponsor 情報 (個人情報) の管理ミス | 個人情報保護法違反 | sponsor 情報は llive ledger に暗号化保存 + 退会即削除 | agent |
| LEG-05 | 景表法 (誇大広告) | 行政指導 | "world's first" 等の誇大表現を style-guard で禁止 | agent |
| LEG-06 | 金商法 / 投資勧誘規制 (lltrade 関連で投資助言とみなされる) | 業務停止 | lltrade 関連 content には自動 disclaimer 付与 | agent |

### B. 技術リスク

| ID | リスク | 影響 | mitigation | owner |
|---|---|---|---|---|
| TECH-01 | AI 生成物の品質劣化 (drift) | 投稿の質低下 → 視聴者離反 | GROW-06 A/B + 人間 spot-check (週次) | agent |
| TECH-02 | 外部 API 価格変動 / 廃止 (OpenAI / Together 等) | 自動化停止 | on-prem fallback を必須に (degrade gracefully) | agent |
| TECH-03 | GPU 故障 / 火災 / 自宅サーバ事故 | データ喪失 / 開発停止 | UPS + 火災検知器 + 定期バックアップ to クラウド | user |
| TECH-04 | データ喪失 (誤削除 / RAID 故障) | コンテンツ資産喪失 | D ドライブ → クラウド (Backblaze / B2) 毎日 sync | user |
| TECH-05 | 依存パッケージの脆弱性 | RCE / 認証バイパス | dependabot + sca 自動 scan (raptor 連携) | agent |
| TECH-06 | supply chain attack (PyPI / npm typosquatting) | malicious code 実行 | requirements を pin + checksum verify | agent |

### C. ビジネスリスク

| ID | リスク | 影響 | mitigation | owner |
|---|---|---|---|---|
| BIZ-01 | 大手 (Google / Anthropic / OpenAI) による FullSense 概念模倣 | 認知シェア奪取 | Honest disclosure + 先行 prior art を Qiita 等で大量蓄積 | agent |
| BIZ-02 | 収益化失敗 (予想通り伸びない) | 投資回収不能 | Phase α-γ で月次 KPI 評価 → 撤退判断点を明示 | user |
| BIZ-03 | BTO 投資後の用途消滅 | sunk cost | 副用途 (動画編集 / 画像生成 / ゲーム) でも価値ある選定 | user |
| BIZ-04 | スポンサー減退 / 主要 sponsor 離脱 | 月収減 | sponsor を 5+ に分散、依存度 30% 上限 | agent |
| BIZ-05 | 競合プロダクト (Open WebUI / LibreChat / Anything LLM) の台頭 | 差別化喪失 | on-prem + Approval Bus + HITL の 3 軸を継続強化 | agent |

### D. 健康・心理リスク

| ID | リスク | 影響 | mitigation | owner |
|---|---|---|---|---|
| HEALTH-01 | 自動化が user を疲弊させる (承認疲れ) | バーンアウト | GROW-10 で承認頻度上限・緊急性スコアで batch 化 | agent |
| HEALTH-02 | AI 過信で事実誤認を見逃す | 信用失墜 | 重要 content は出典 URL 必須化 (style-guard 強制) | agent |
| HEALTH-03 | quiet hours 違反で深夜投稿が user に通知される | 睡眠不足 | QuietHoursGuard を ApprovalBus の通知側にも適用 | agent |
| HEALTH-04 | コメント返信プレッシャー | 心理負荷 | GROW-04 で「急がない」を default style guide に | agent |
| HEALTH-05 | 1 人開発の孤立感 | モチベ低下 | Discord / GitHub Discussion で community 形成 | user |

### E. レピュテーションリスク

| ID | リスク | 影響 | mitigation | owner |
|---|---|---|---|---|
| REP-01 | AI 生成物の差別的表現 / hate speech | 炎上 / アカウント停止 | toxicity classifier を style-guard pipeline に組込 | agent |
| REP-02 | AI 自動コメント返信の失礼 / 誤情報 | 個別関係悪化 | 承認前に「AI 下書き」と明示 + 人間最終承認必須 | agent |
| REP-03 | "中身がない AI 量産" 批判 | ブランド毀損 | honest disclosure + 質的差別化 (商用級コード / 実測値) | agent |
| REP-04 | Honest disclosure 不足で「騙してる」批判 | 信用失墜 | 全 AI 生成物に "AI-assisted" footer 強制 | agent |
| REP-05 | 大手企業の不利な比較で炎上 | 訴訟 / 影響力低下 | 比較は公開資料・ベンチのみ、感情的表現禁止 | agent |

### F. セキュリティリスク

| ID | リスク | 影響 | mitigation | owner |
|---|---|---|---|---|
| SEC-01 | credential 漏洩 (env / .env / config) | API 不正利用 | settings*.json 移行済、git-secrets で commit 前 scan | agent |
| SEC-02 | GitHub repo 履歴の secret | 永続的漏洩 | bfg-repo-cleaner で履歴 rewrite + key rotation | user |
| SEC-03 | 自動 push の意図せぬ漏洩 | privacy 侵害 | push 直前に ApprovalBus 承認 + 内容 review | agent |
| SEC-04 | ProductionHttpTimelineSink の token 漏洩 | バックエンド乗っ取り | env 経由のみ、log には mask、rotation 90 日毎 | agent |
| SEC-05 | 自宅サーバの外部公開 → 攻撃面 | RCE / DDoS | VPN 必須、外部公開しない、Tailscale 等の zero-trust | user |

### G. 機会損失リスク

| ID | リスク | 影響 | mitigation | owner |
|---|---|---|---|---|
| OPP-01 | 商標を取らず放置 → 他社先取り | LEG-01 と同じ | 6 ヶ月以内に出願 | user |
| OPP-02 | 環境投資せず時間で失う (時給換算で cloud 課金が割高に) | 累積コスト | Phase 1 で 1 ヶ月使って判断 → 即 BTO | user |
| OPP-03 | コンテンツ更新止まる → 認知拡大止まる | 機会逸失 | GROW-03 scheduler で minimum cadence 維持 | agent |
| OPP-04 | 業界 trend (MCP / Agentic / on-prem) に乗り遅れる | 差別化消失 | RAD で trend 監視、四半期 trend review | agent |

### リスク管理プロセス

1. **monthly risk review** (毎月 1 回、~30 分): 上記 table を見て status
   更新. mitigation が effective か / 新リスク追加か.
2. **incident log**: 発生したリスクは `docs/incidents/YYYY-MM-DD.md` に
   ポストモーテムで記録. [[feedback-benchmark-honest-disclosure]] と同じ精神.
3. **撤退判断点**:
   - BIZ-02 (収益化失敗): Phase β 終了時に月収 ¥10,000 未満なら llgrow
     を pause、戦略見直し
   - HEALTH-01 (バーンアウト): 連続 2 週間で承認待ちが 50 件超積もったら
     llgrow 全停止
   - LEG-01 (商標先取り): 出願済名称の場合は即時 rebrand 検討
4. **絶対遵守ライン**:
   - 健康 (quiet hours / 承認頻度上限) は絶対に技術的に強制
   - HITL ApprovalBus を迂回する自動化を許可しない
   - honest disclosure を取り下げる pressure に屈しない

## Status

- 2026-05-19: 要件追加 (DRAFT) — 本書
- 2026-05-19: リスク抽出 (RISK-FX A-G) 追記
- (今後) Phase α 着手宣言
- (今後) llgrow 独立リポ化
- (今後) PyPI 公開
