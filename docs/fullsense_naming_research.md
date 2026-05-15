# FullSense — 命名リスク調査 (2026-05-15)

> llive サブシステムとして `src/llive/fullsense/` を立ち上げる前提の、命名と
> 配布チャネルの可用性チェック。商標の最終判断は弁理士に委ねること。

## 調査対象

ユーザ要望: **Furuse → FullSense** に少しいじって OSS として普及させたい。

## 結果一覧

| 候補 | PyPI | GitHub user/org | Web 言及 | 総合判定 |
|---|---|---|---|---|
| `fullsense` | 空 | 既存 (id 69564714、個人、低活動: stock_market fork + Config files) | 直接競合なし | ⚠ user 取得不可、repo / PyPI は使える |
| `llmesh-fullsense` | 空 | n/a | n/a | ✓ PyPI で確保推奨 |
| `fullsense-ai` | 空 | n/a | n/a | ✓ サブブランド候補 |
| `sentire` | 空 | 既存 (Junko Hsu、0 repos、休眠) | n/a | ⚠ 似た事情 |
| `senseloop` | 空 | (未確認、要確認) | n/a | ◯ 候補 |
| `triggermind` | 空 | (未確認、要確認) | n/a | ◯ 候補 |
| `autosense` | 空 | (未確認、要確認) | n/a | ◯ 候補 |
| `pulse` | **取得済 (0.1.2)** | 複数 | 一般名詞 | ✗ 避ける |

## 観測した近隣ブランド (区別が必要)

| 名称 | 何か | 影響 |
|---|---|---|
| **AlphaSense** | 市場インテリジェンス / GenAI 検索プラットフォーム (大手) | 同じ "Sense" 系列、混同可能性あり |
| **6sense** | ABM プラットフォーム (revenue intelligence) | 同上 |
| **SenseAI** | AI 投資評価 | 別物だが近い |
| **AlphaSense Product Updates** | 月次プロダクト更新 | 上記の活発な存在 |

→ `FullSense` 単体は web で大手競合の言及が確認できず。
ただし "Sense" を冠する大手 (AlphaSense, 6sense) があるので、ロゴ・配色・
カテゴリ (営業 SaaS) では明確に距離を取ること。**OSS / 開発者向け / autonomy 軸**で
ブランディングすれば衝突は避けやすい。

## 推奨構成 (進める場合)

### 命名

* **概念名 (ブランド)**: `FullSense Loop` — 名詞句として独自性が出る
* **PyPI**: `llmesh-fullsense` (本体)、将来 `fullsense` 単独 PyPI も確保しておく
* **GitHub repo**: `furuse-kazufumi/fullsense-llive` (user fullsense は既存のため
  個人 namespace 配下 + `-llive` で曖昧性を排除)
* **モジュール**: `src/llive/fullsense/`

### 商標

* USPTO TESS / 日本 IPDL での全文検索が必要 (本調査では未実施)
* 弁理士に「FullSense / FullSense Loop」両方を IC9 (software) / IC42 (SaaS) で
  検索依頼を推奨
* それまでは OSS としての使用 (商業利用前) に留め、商標主張はしない

## 代替案 (FullSense にこだわらない場合)

| 名称 | 意味的フィット | 利点 |
|---|---|---|
| `SenseLoop` | 直接的、Loop は既知パターン語 | 短い、衝突低い |
| `Sentire` | 伊「感じる」、技術名で珍しい | ユニーク、商標的にクリア |
| `TriggerMind` | 自発トリガを直訳 | 機能直感的 |
| `AutoSense` | autonomous + sense | 機能直感的 |

## 次のアクション

1. **本セッション**: `src/llive/fullsense/` MVP (Sandbox 限定) を実装、コードレベルで命名コミット
2. **後続**: 弁理士に商標検索を依頼 (FullSense / FullSense Loop)
3. **後続**: PyPI `llmesh-fullsense` 名を予約 (空パッケージで先取り)
4. **後続**: GitHub repo を `furuse-kazufumi/fullsense-llive` で確保 (公開は実装後)

## 結論

**FullSense は技術的に進行可能、ただし `github.com/fullsense` 用户は既存
(低活動な個人)** のため user/org としての取得は不可。代わりに
`furuse-kazufumi/fullsense-llive` を repo 名、`llmesh-fullsense` を PyPI 名、
ブランド概念として `FullSense Loop` を使う構成を推奨。商標は実装が落ち着いた
後に弁理士に正式検索を依頼。

---

調査ソース (web search): [USPTO TMSearch](https://tmsearch.uspto.gov/) /
[PyPI](https://pypi.org/) / [GitHub /fullsense](https://github.com/fullsense)
