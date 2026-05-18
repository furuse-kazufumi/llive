# Non-Transformer LLM 比較行列 — llive backend 候補 (draft v0.1)

> 2026-05-18 作成. `ROADMAP.md` の 5 アーキ案 (A-E) について、定量/定性
> 評価軸を細かく比較. 評価は文献 + 公開ベンチ + 想定値の混在 — 必ず
> on-prem 実機で再検証する前提.

## 0. 評価軸 (12 項目)

1. **実装工数** — 既存 llive infra への組込時間
2. **on-prem fit** — GPU 不要〜小規模 GPU で動くか
3. **EAR/地政学 fit** — 米国輸出規制 + 中国規制両立可能か
4. **長 context** — 100k token 以上での実用性
5. **品質 (in-context learning)** — 同サイズ Transformer 比
6. **推論速度** — 同サイズ Transformer 比
7. **訓練可能性** — base model 入手 + fine-tune 可能か
8. **ライセンス** — Apache-2.0 / 商用配布可
9. **コミュニティ規模** — 質問対応・派生 model の入手性
10. **論文化ネタ** — 新規性の主張容易性
11. **llive 思考層との適合** — 6 stage / 10 因子との結合
12. **撤退コスト** — 失敗時の戻し容易性

---

## 1. 案ごとの詳細評価

### 案 A — Pure Mamba 7B (Codestral-Mamba ベース想定)

| 軸 | 評価 | 根拠 / 備考 |
|---|---|---|
| 実装工数 | ◎ (1 週) | LLIVE_OPENAI_MODEL + llama-server で OpenAI 互換、既存 backend 再利用 |
| on-prem fit | ◎ | 7B Q4 で 6GB RAM 動作、CPU でも実用速度 |
| EAR fit | ○ | Mistral (フランス) 製、米国輸出規制対象外、Apache-2.0 |
| 長 context | ◎ | 256k token native 対応 |
| 品質 (ICL) | ○ | Transformer 7B 比 ~5pt 劣 (公開ベンチ) |
| 推論速度 | ◎ | 同サイズ Transformer 比 3-5× (実測ベース) |
| 訓練可能性 | ○ | mamba-ssm ライブラリ + base model 入手可 |
| ライセンス | ◎ | Apache-2.0 (Codestral-Mamba) |
| コミュニティ | ○ | mamba-ssm / llama.cpp 共に活発 |
| 論文化ネタ | △ | 既知技術組合せ、新規性弱い |
| llive 適合 | ○ | backend 差替えのみ、stage-level 統合は浅い |
| 撤退コスト | ◎ | env 1 つ戻すだけ |

### 案 B — Jamba Hybrid (AI21 Jamba-1.5 mini / large)

| 軸 | 評価 | 根拠 / 備考 |
|---|---|---|
| 実装工数 | ○ (1 ヶ月) | stage-wise backend infra + Jamba 接続 |
| on-prem fit | △-○ | Jamba-1.5 mini 12B、large 398B (large は GPU クラスタ必要) |
| EAR fit | ○ | AI21 (イスラエル) 製、Apache-2.0 系 |
| 長 context | ○ | 256k 公称、実効 ~100k |
| 品質 (ICL) | ◎ | Attention 層で ICL 保持、Mamba 層で効率 |
| 推論速度 | ○ | hybrid のため Transformer より 1.5-2× |
| 訓練可能性 | △ | mini で fine-tune 可、large は非現実的 |
| ライセンス | ○ | mini は Apache-2.0、large は要 commercial check |
| コミュニティ | △ | mamba 派生としては小規模 |
| 論文化ネタ | ○ | stage-wise backend + Jamba は新規性中 |
| llive 適合 | ◎ | 6 stage × backend 切替が自然 |
| 撤退コスト | ○ | stage-wise infra は他 backend にも使い回せる |

### 案 C — 思考因子 → SSM Δ 橋渡し (FullSense 独自設計)

| 軸 | 評価 | 根拠 / 備考 |
|---|---|---|
| 実装工数 | ✗ (6-12 ヶ月) | 内部 hook + 訓練データ再整備 + PoC 検証 |
| on-prem fit | ◎ | 思考因子は llive 内、Mamba 推論は on-prem |
| EAR fit | ◎ | 独自設計、輸出規制対象外 |
| 長 context | ◎ | Mamba ベースなので継承 |
| 品質 (ICL) | ?? | 実証前、理論的には Δ 動的化で改善期待 |
| 推論速度 | ○ | Mamba 同等 + 思考層 overhead 数 ms |
| 訓練可能性 | △ | 既存 base 不可、pre-training 一部必要 |
| ライセンス | ◎ | FullSense Apache-2.0 (オリジナル設計) |
| コミュニティ | ✗ | 新規、コミュニティゼロから |
| 論文化ネタ | ◎◎ | **最強候補**。認知科学 × LLM 内部状態 |
| llive 適合 | ◎◎ | architectural-level に統合 |
| 撤退コスト | ✗ | 投資した R&D 時間が回収できない |

### 案 D — Diffusion + Mamba ハイブリッド

| 軸 | 評価 | 根拠 / 備考 |
|---|---|---|
| 実装工数 | △ (6 ヶ月) | Diffusion + Mamba 二系統の統合 |
| on-prem fit | △ | Diffusion 部分が GPU 中規模必要 |
| EAR fit | ○ | Mercury / ELYZA は US 系、要確認 |
| 長 context | ○ | Mamba 部分は ◎、Diffusion は △ |
| 品質 (ICL) | ?? | 並列生成 vs 自己回帰の組合せ未検証 |
| 推論速度 | ◎ (xs/s 領域) | 並列生成で latency 大幅減 |
| 訓練可能性 | △ | Diffusion LM 自体まだ研究段階 |
| ライセンス | △ | ELYZA-LLM-Diffusion は ELYZA license |
| コミュニティ | △ | Diffusion LM コミュニティは小規模 |
| 論文化ネタ | ○ | Diffusion + SSM の hybrid は新規 |
| llive 適合 | ○ | Inner Monologue → Action Plan に hybrid |
| 撤退コスト | △ | Diffusion infra は再利用しにくい |

### 案 E — RWKV-7 ベース (CPU 推論最強)

| 軸 | 評価 | 根拠 / 備考 |
|---|---|---|
| 実装工数 | ◎ (2-3 週) | RWKV.cpp + OpenAI 互換 wrapper |
| on-prem fit | ◎◎ | **CPU only 環境で実用速度** |
| EAR fit | △ | RWKV community 主導は元中国系 (要確認)、Apache-2.0 自体は OK |
| 長 context | ○ | 64k-100k 程度、Mamba より小さい |
| 品質 (ICL) | △ | Transformer 7B 比 ~10pt 劣 (実測) |
| 推論速度 | ◎ (CPU) | CPU で秒数百 token 出る |
| 訓練可能性 | ○ | RWKV-7 fine-tune は活発 |
| ライセンス | ◎ | Apache-2.0 |
| コミュニティ | ○ | RWKV community 活発、多言語版あり |
| 論文化ネタ | △ | 既知、新規性弱い |
| llive 適合 | ○ | streaming 表示 (llove TUI) と相性 ◎ |
| 撤退コスト | ◎ | 単体 backend 切替で済む |

---

## 2. 軸別ランキング

| 軸 | 1 位 | 2 位 | 3 位 |
|---|---|---|---|
| 実装工数 | A | E | B |
| on-prem fit | E | A | C |
| EAR fit | C | A | B |
| 長 context | A / C | B | D / E |
| 品質 (ICL) | B | A | E |
| 推論速度 | D (xs/s) | A | E |
| 論文化 | C | B | D |
| llive 適合 | C | B | E |
| 撤退コスト | A / E | B | D |

---

## 3. 推奨ポートフォリオ

ROADMAP.md §3 の 3 軸並走と整合:

| 投資配分 | 案 | 期間 | 目的 |
|---|---|---|---|
| 30% | A (Pure Mamba) | 1-3 ヶ月 | 短期実用化、運用知見蓄積 |
| 20% | E (RWKV-7) | 1-3 ヶ月 | CPU only 領域カバー、ベースライン |
| 30% | B (Jamba) | 4-6 ヶ月 | 中期差別化、stage-wise infra |
| 20% | C (思考因子-Δ) | 7-12 ヶ月 | 長期論文化、独自軸 |
| 0% (現在) | D (Diffusion + Mamba) | 6 ヶ月+ | 案 A/B 立上り後の実験トラック |

---

## 4. 決定済 / 未決定の論点

### 決定 (本 v0.1 時点)
- 短期投資は A + E の 2 軸並走
- 中期で B (Jamba) に投資
- 長期 R&D は C (思考因子-Δ) を最優先論文ネタに

### 未決定 (今後の検討)
- Jamba large 398B を社内 GPU クラスタで扱うかどうか
- 案 C の数学的設計の細部 (Δ をどの空間でどう操作するか)
- 中国系 SSM/RWKV モデルを採用する場合の規制 review
- mcp-3d v4 ([[project_precision_metrology_llm]]) との結合タイミング

---

## 5. 改訂履歴

- 2026-05-18 — draft v0.1 (5 案 × 12 評価軸 + 推奨ポートフォリオ + 未決定事項)
