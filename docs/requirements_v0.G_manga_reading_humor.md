# llive 要件定義 v0.G — 漫画読解 (VLM 補助) と現代ユーモア獲得

**Drafted:** 2026-05-22
**Status:** **要件登録 (構想)** — 実装は VLM 基盤 (Phase C-1.3 multimodal) の続きで.
**Type:** Multimodal extension — comics/manga understanding as humor-acquisition subsystem
**Trigger:** ユーザー指摘 (2026-05-22):

> AI が漫画とか読めたらいいのにと思います。今だったら、画像認識機能を別子に設けて漫画も読めるんじゃないですかね？ VLM やマルチモーダル LLM の補助機能として llive に入れて欲しいですね。
>
> なぜ、漫画とか読めたらいいのにと思うのかというと、トレンドに近いユーモアを獲得できるからです。以前、漫才や落語などを参照させて記事を書かせた内容が酷くてちょっとこまりました。

---

## 1. 動機 — 「漫才・落語ではダメ、漫画なら良い」

### 1.1 漫才・落語参照の失敗例

過去に llive (もしくは Claude) に **漫才/落語のスタイルを直接参照** させて記事を書かせたところ、**現代から乖離した古臭い文体 / 文脈ずれ / オチが滑る** という結果になった。原因仮説:

- 漫才・落語の教科書的データセット (青空文庫系古典など) が **昭和以前の語彙・社会通念** に依存
- LLM がスタイル模倣しても **時代感覚・トレンド・社会の流れ** が反映されない
- 「面白い言い回し」の構造 (構造的笑い / 三段オチ / 天丼) は抽出できても、**何が今の読者に響くか** は学習できない

### 1.2 漫画なら「現代ユーモア」が取れる仮説

漫画 (特に 2010 年代以降の連載作品) は:

- **現代の言語感覚** がリアルタイムで反映される (作家が同時代を生きている)
- **トレンド** (SNS 文化 / 流行語 / ミーム) が作中に出現
- **絵 + 台詞** の合わせ技で「現代の間」が学習できる
- panel transition / SFX / 表情演出など **構造的ユーモア要素** がメソッド化されている (McCloud 系)

つまり漫画読解 = **トレンド感覚 + 言語感覚 + 視覚的ユーモア構造** を一括取得する経路。記事執筆 ([[feedback_article_humor_style]]) の品質改善に直結する。

---

## 2. 設計柱

### 柱 A: 漫画特化 panel reader

汎用 VLM 単体では漫画の構造を理解しない (panel 順序 / 吹き出し帰属 / SFX). llive は **専用 subsystem** で前処理する.

#### A-1. Panel Segmentation

- ページ画像から panel 矩形を検出 (既存 OSS: `Magi` / `MangaDLR` / `Comic-Text-Detector` を参照)
- 日本マンガは **右→左、上→下** が default、洋コミックは **左→右、上→下**
- panel 順序を確定して JSON 出力

#### A-2. Speech Bubble / Narration / SFX 分離

- 吹き出し (speech bubble) — 角型 / 雲型 / トゲ型で speaker 推定
- ナレーション (narration box) — 四角形枠
- SFX (擬音語) — 漢字+カタカナの非吹き出し配置、書き文字
- 各テキスト要素を OCR (Manga OCR / Tesseract jpn_vert / vendor VLM)
- speaker attribution: 吹き出しのトゲがどのキャラに向いているかを幾何解析

#### A-3. Character Tracking

- panel 横断でキャラを同一視 (顔特徴 + 服装 + 髪型 embedding)
- 名前は台詞 / ナレーションから anchor 取得
- ストーリー進行で再登場するキャラを連結

#### A-4. Panel Transition Classification

- McCloud (1993) の 6 種類分類: moment-to-moment / action-to-action / subject-to-subject / scene-to-scene / aspect-to-aspect / non-sequitur
- どの transition が使われたかで **「間」「省略」「飛躍」** の検出
- ユーモア構造 (三段オチ / 天丼 / ボケツッコミ) の panel-level 検出も同レイヤ

### 柱 B: LLMBackend Bridge

漫画読解結果を llive 内部の LLMBackend (現状 Mamba/Jamba/RWKV/transformer 系) へ **構造化済 context** として注入:

```json
{
  "page_id": "...",
  "panels": [
    { "order": 1, "speaker": "char_A", "text": "...", "transition_from_prev": "action-to-action", "sfx": [...] },
    ...
  ],
  "characters": [ { "id": "char_A", "name": "...", "first_appearance": "page X panel Y" } ],
  "humor_signals": { "三段オチ": true, "天丼": false, "ボケツッコミ": [...] }
}
```

VLM (Gemini Vision / Claude Vision / Qwen-VL / GPT-4o) は **panel 単体の描写** にとどめ、構造化と connect は llive 側で行う (cloud LLM 依存を最小化、local 推論可能な範囲を残す)。

### 柱 C: 現代ユーモア知識ベース (HumorKB)

漫画読解で抽出した「**構造パターン**」を蓄積する.
**注意**: 既存 [[feedback_article_humor_style]] (2026-05-20 修正) は **架空対話の捏造 / 落語の枕的喩え話 / 過剰なオノマトペ + AI 擬人化** を禁止. 漫画本文を **直接引用** することも (柱 D の著作権制約からも) 禁止. HumorKB は **構造のみ** を扱う.

#### C-1. 抽出する「構造」と除外する「コピー」

- ✅ **抽出 (構造)**: panel リズム (短-短-長 / 短-中-オチ) / 視線誘導 / SFX 配置 / 三段オチ / 天丼 / ツッコミ pattern / 間の取り方 (cut to / black panel) / 期待裏切りの depth
- ❌ **除外 (コピー)**: 台詞そのまま / キャラ固有口癖 / 作品固有ミーム / 流行語そのもの / 架空対話の生成

#### C-2. メタ構造のみのスキーマ

```json
{
  "structure_id": "...",
  "category": "三段オチ" | "天丼" | "黙りオチ" | "視点ジャンプ" | "状況逆転" | ...,
  "rhythm": ["short", "short", "long-then-cut"],
  "year_observed": 2024,
  "genre": "日常コメディ",
  "abstraction_level": "structural",
  "examples_paraphrased": ["[paraphrased structure description, no direct quote]"],
  "applicability": ["技術記事の section closer", "ベンチ結果の honest disclosure 直前"]
}
```

直接の台詞・キャラ名・作品固有 phrase は保存しない. 抽象化 (paraphrase) された構造記述のみ.

#### C-3. 記事執筆プロンプトでの利用

- 利用は **構造ガイドの形** ([[feedback_article_humor_style]] OK 項目「事実ベースの軽妙な書き口」と整合): 「ここで三段オチの rhythm を使い、第三項で期待を裏切る」程度のヒント
- **架空対話を生成させない** (NG 項目): HumorKB を理由に「ボケ『〜』 ツッコミ『〜』」を書かせない
- 年代タグで古いミームを抑制 / 失敗パターン (漫才/落語直接参照) は **明示的なネガティブサンプル** として「これは使うな」リストに

#### C-4. 失敗パターン登録

- 2026-05-20 の漫才/落語参照失敗 ([[feedback_article_humor_style]]) を **negative example** として HumorKB に登録
- 同類の失敗を繰り返さないよう、生成前 lint で「捏造ダイアログ / 落語枕 / AI 擬人化」を検出

### 柱 D: 法的・倫理的配慮

- 入力は **ユーザーが正規入手した漫画** 限定 (海賊版 PDF をスキャンしない)
- 学習データに著作権ありの漫画を直接埋め込まない (HumorKB は **構造パターン + 短い引用** のみ、全文保存しない)
- VLM への送信は **権利確認済 cloud 利用** が前提、local VLM (Qwen-VL local / Llama 3.2 Vision) を優先
- FullSense local-first 原則 ([[project_fullsense_ear_origin]]) を維持

---

## 3. 実装ロードマップ (要件のみ、実装は次フェーズ)

| ID | 内容 | 依存 |
|---|---|---|
| MNG-01 | Panel segmentation (OSS Magi 等のラッパー) | C-1.3 multimodal |
| MNG-02 | Speech bubble / narration / SFX 分離 + OCR | MNG-01 |
| MNG-03 | Speaker attribution (幾何 + 顔特徴) | MNG-02 |
| MNG-04 | Character tracking (cross-panel embedding) | MNG-02 |
| MNG-05 | Panel transition classification (McCloud 6 種) | MNG-01 |
| MNG-06 | Humor structure detector (三段オチ / 天丼 / ボケツッコミ) | MNG-05 |
| MNG-07 | LLMBackend bridge (structured context injection) | MNG-01..06, LLMBackend 既存 |
| MNG-08 | HumorKB schema + storage | MNG-06, MEM-06 parameter memory |
| MNG-09 | 記事執筆プロンプト統合 (年代タグ + ジャンル加重) | MNG-08 |
| MNG-10 | 失敗パターン記録 (漫才/落語事例 + 評価フィードバック) | MNG-09, lleval LE-01 |
| MNG-11 | A/B test: 漫才/落語 baseline vs 漫画 HumorKB 適用 | MNG-09, [[feedback_eval_methodology_continuous_update]] |
| MNG-12 | 著作権チェック gate (権利確認 + 引用率上限) | 全 MNG |

---

## 4. 先行研究 / 参考

- **Scott McCloud (1993)** "Understanding Comics" — panel transition 6 分類
- **Manga109** (Aizawa Lab) — 公開漫画データセット (アカデミック利用)
- **Magi** (https://github.com/ragavsachdeva/magi) — manga panel + character detection
- **Manga OCR** (kha-white) — Japanese manga 専用 OCR
- **comic-text-detector** — speech bubble detection
- **Qwen-VL / Llama 3.2 Vision** — local VLM 候補
- **Gemini 1.5 / Claude Sonnet Vision / GPT-4o** — cloud VLM (権利確認時のみ)

---

## 5. リスクと honest disclosure

| リスク | 影響 | 対策 |
|---|---|---|
| 著作権侵害 | 法的 + 倫理的 | 柱 D (権利確認 / 引用率上限 / local 優先) |
| VLM の描写ハルシネーション | HumorKB に虚偽パターンが混入 | A/B + 人手検証 (lleval) |
| 現代ユーモアの陳腐化 | 半年で古い | 年代タグ + 定期 refresh (月次) |
| panel 順序誤検出 (見開き / 変則 layout) | 文脈崩壊 | manga109 で benchmark + fallback heuristic |
| SFX OCR 精度低 | ユーモア構造取り逃し | manga OCR 専用モデル + 手書き SFX 別 model |
| local VLM 性能不足 | 検出精度低下 | cloud VLM ハイブリッド (権利確認時のみ) |

---

## 6. 連動 memory / docs

- `[[feedback_article_humor_style]]` — 漫才/落語/漫画的言い回し要請 (本要件で「漫才/落語直接参照は失敗」を補足)
- `[[project_llive_multimodal_c13]]` — C-1.3 multimodal 拡張 (audio/sensor) — 本要件は manga 軸の追加
- `[[project_llive_vlm_future]]` — VLM-FX 将来要件 (画像処理/三次元計測)
- `[[feedback_articles_concept_hook]]` — 記事執筆コンセプト hook (HumorKB が改善経路)
- `[[feedback_qiita_long_form]]` — 長文記事スタイル (HumorKB が長文の retention 向上)
- `[[feedback_eval_methodology_continuous_update]]` — A/B test + 統計駆動 (MNG-11 で適用)
- `[[project_fullsense_ear_origin]]` — local-first 原則 (柱 D で維持)

---

> Drafted by Claude (Opus 4.7) on 2026-05-22 in response to user feedback (動機: 漫才/落語参照で記事が酷くなった失敗から、現代漫画でユーモア獲得を試みる方向).
> 実装着手は VLM 基盤 (C-1.3) 完了後。
