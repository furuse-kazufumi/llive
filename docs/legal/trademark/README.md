# FullSense Trademark Filings — Draft Workspace

このディレクトリは、**FullSense ™ およびその子ブランド (llmesh / llive / llove)
の商標出願準備**用 draft 資料を集約する。実際の出願はユーザ (or 代理人) が
別途行う前提で、Claude が単独で準備できる範囲のテンプレートを揃える。

## 優先順位

| Wave | Mark      | Jurisdictions      | Status (2026-05-16) |
|------|-----------|--------------------|---------------------|
| 1    | FullSense | JP / US / EU       | draft               |
| 2    | llmesh    | JP / US / EU       | (after Wave 1)      |
| 2    | llive     | JP / US / EU       | (after Wave 1)      |
| 2    | llove     | JP / US / EU       | (after Wave 1)      |

各 mark について以下の構成で draft を置く:

```
docs/legal/trademark/
├── README.md                          (この案内)
├── J-PlatPat_FullSense_draft.md       (JP 出願 draft)
├── USPTO_FullSense_draft.md           (US 出願 draft)
├── EUIPO_FullSense_draft.md           (EU 出願 draft)
└── (将来) J-PlatPat_llive_draft.md など子マーク draft
```

## 商品・役務の指定 (共通方針)

ソフトウェア / SaaS で押さえるべき Nice 分類:

- **9 類**: ダウンロード可能なコンピュータプログラム (e.g. on-prem インストールされる LLM フレームワーク本体)
- **42 類**: SaaS / クラウドホスティング / ソフトウェア開発・設計 (e.g. ホスティング型 FullSense サービス、API 提供)

これに加え、必要に応じて以下も検討:

- **16 類**: 印刷物 (documentation 配布)
- **41 類**: 教育 / 訓練 (workshop, conference)

## ジャージドクション別の留意点

### JP (J-PlatPat)
- 出願は <https://www.j-platpat.inpit.go.jp/>
- 既存登録の確認: 「商標称呼検索」で "フルセンス" / "fullsense" を search
- 自己出願なら 1 件 1 区分 ¥12,000 (印紙代) + ¥32,900 (登録料 / 10 年)
- 代理人 (弁理士) 依頼で +¥80,000 〜 ¥150,000 程度

### US (USPTO)
- 出願は <https://www.uspto.gov/trademarks>
- TEAS Standard $350/class, TEAS Plus $250/class
- US 出願は **意図使用** (Intent-to-use, ITU) で先に押さえ、後で actual use を提出可
- Specimen 必要 (production 状態の screenshot 等)

### EU (EUIPO)
- 出願は <https://euipo.europa.eu/>
- EU Trade Mark (EUTM) 1 件 €850 (1 class) + €50 (2nd class) + €150 (each subsequent)
- 単一申請で EU 27 加盟国カバー

### Madrid Protocol (国際登録)
- 日本商標を base に国際出願可
- 個別出願より割安、特に 5+ 国狙うなら検討

## 商標調査 (出願前必須)

以下を出願前にチェック:

  - [ ] J-PlatPat で "FullSense" / "Full Sense" / "フルセンス" 既登録なし
  - [ ] USPTO TESS で "FullSense" 既登録なし
  - [ ] EUIPO eSearch で "FullSense" 既登録なし
  - [ ] WIPO Madrid Monitor で国際登録なし
  - [ ] Google 検索で混同を生む先行商標がない
  - [ ] ドメイン取得状況: fullsense.com / .ai / .dev / .io / .org

## 関連文書

- `TRADEMARK.md` (リポジトリルート) — 商標ポリシー
- `NOTICE` — 著作権 + 商標表示
- `docs/v1.0_migration_plan.md` — PyPI 名との整合
