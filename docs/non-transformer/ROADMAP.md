# Non-Transformer llive Roadmap — Transformer 以外で llive を完成させる戦略 (draft v0.2)

> 2026-05-18 作成. ユーザー要望「Transformer 以外のアプローチで LLM として
> llive を完成させたい」を受けて、12 ヶ月 + 30 日アクションプランを策定.
>
> v0.2 (同日追記): ユーザーから 2 制約追加
> 1. **拡張性ファースト** — 戦略だけ立てない、まず全候補を skeleton で繋ぎ、
>    性能担保後に最適化で必要機能に絞り込むスタイル
> 2. **低スペック個人 PC で実用化** — そこに届けば普及力は最大化される
>
> 起点 docs: `D:/projects/fullsense/docs/architecture/triz-ssm-vs-transformer.md`

## 0. ゴール宣言

llive (FullSense 思考層) の **LLM backend を Transformer 以外で完成**させ、
**低スペック個人 PC で実用速度に到達**させる.

- **必須**: on-prem 完結、EAR + 中国規制下でも動く、Apache-2.0 系で配布可
- **必達**: 256k+ token 長コンテキストを線形コストで処理
- **必達 (追加 v0.2)**: 個人 PC (CPU only / 8-16GB RAM / GPU 任意) で
  「実用速度」(= Brief 1 件あたり 30 秒以内) を達成
- **望ましい**: llive 思考因子と LLM 内部状態が相互作用 (Transformer 不可能)
- **回避**: cloud API 依存、独自ライセンス、地政学リスク高い model

## 0.1 開発スタイル原則 (v0.2 で明文化)

ユーザーの作業スタイルに合わせて以下を採用:

1. **拡張性ファースト** — 5 候補すべての backend skeleton を先に繋ぐ.
   性能・速度・コストは後段で最適化. 早期最適化は禁止.
2. **段階的削ぎ落とし** — 全 candidate 実装 → bench → 必要機能だけ
   生き残らせる. 削れる機能を削るのが最適化フェーズの主軸.
3. **低スペック PC primary target** — ベンチ環境は「ユーザーの個人 PC」を
   primary、GPU クラスタは secondary. memory `feedback_d_drive_preference`
   と整合 (D ドライブ運用、C 故障時の復旧性確保).
4. **honest disclosure 厳守** — 異常に良い結果が出たら必ず内訳を疑う
   (memory `feedback_benchmark_honest_disclosure`).

## 0.2 低スペック PC 性能目標 (測定対象)

memory `feedback_benchmark_progressive_tokens` の xs/s/m/l/xl 5 段階に
**低スペック PC 系列**を主軸として追加:

| token size | 目標 latency (個人 PC, CPU only) | 目標 RAM 占有 |
|---|---|---|
| xs (~500 tok) | < 3 秒 | < 4 GB |
| s (~2k tok) | < 8 秒 | < 6 GB |
| m (~8k tok) | < 20 秒 | < 8 GB |
| l (~32k tok) | < 60 秒 | < 10 GB |
| xl (~128k tok) | < 180 秒 | < 14 GB |

GPU 有り環境 (16GB VRAM 想定) は上記を 1/3〜1/5 で目指す.

---

## 1. 5 アーキ案 (deep dive)

### 案 A — Pure Mamba 7B (短期、3 ヶ月)

**設計**:
- Codestral-Mamba 7B (Mistral, Apache-2.0) を base model に
- llive 9 軸 skeleton ([[project_llive_9axis_skeleton]]) はそのまま、backend
  だけ MambaBackend に置換
- llama.cpp (b8864+) で Mamba 推論、`llama-server` 経由 OpenAI 互換 API
  → 既存 `OpenAIBackend` + `OPENAI_BASE_URL` で **改修ゼロ運用可**

**強み**:
- 既存インフラ流用 (今セッションの h.1 + LLIVE_OPENAI_MODEL 改修と整合)
- 256k context (Codestral-Mamba の native 仕様)
- 推論速度 Transformer 7B 比 3-5× 高速 (実測ベース)
- on-prem 7B クラスで GPU 8GB から動く

**弱み**:
- in-context learning が Transformer 7B より弱い (実測差 ~5pt)
- 多言語 (特に中文/日本語) が Mistral 系のため英語寄り
- 推論層の論文化ネタとして弱い (既知技術の組合せ)

**実装工数**: 1 週間 (LLIVE_OPENAI_MODEL 経路 + Codestral-Mamba pull + bench)

### 案 B — Jamba Hybrid (中期、6 ヶ月)

**設計**:
- AI21 Jamba (mixed Mamba + Attention layers, 一部 OSS) を base model に
- llive 6 stage で **stage ごとに backend を切替**
  - Salience / Curiosity / Ego → Mamba 層を主に使う pass
  - Inner Monologue / Action Plan → Attention 層を主に使う pass
- 新 env: `LLIVE_LLM_BACKEND_BY_STAGE` (JSON), stage 単位 backend 指定

**強み**:
- in-context learning は Attention 層で確保、効率は Mamba 層で確保
- llive 思考 stage と backend 特性のマッピングが自然
- 長コンテキストと表現力の両立 (TRIZ 原理 5 Merging)
- Jamba-1.5 (52B mini / 398B large) があり on-prem 規模選択肢広い

**弱み**:
- Jamba 全 OSS ではない (商用ライセンス制限あり、要確認)
- stage 単位切替の overhead (state 移行コスト)
- 実装複雑度上昇 (案 A の 3 倍)

**実装工数**: 1 ヶ月 (stage-wise backend infra + Jamba bench + license clear)

### 案 C — 思考因子 → SSM Δ 橋渡し (長期、12 ヶ月、論文)

**設計** (FullSense 独自):
- llive 10 思考因子 (uncertainty / structurize / reconstruct / ego / altruism /
  curiosity / salience / governance / consensus / risk) を Mamba の
  **離散化ステップサイズ Δ** に直結
- 因子値が高い (不確実 / 整合的 / 注意要 等) → Δ 値変化 → 状態遷移調整
- 数学的には Mamba の動的 Δ パラメータ ([[project_llive_oka]] の MathVerifier
  と接続) を可微分パイプラインで思考層から制御

**強み**:
- **論文化最強候補** (Transformer ベース LLM では実装不能、認知科学 ×
  アーキの新規軸、精密工学・計測会 + AI 学会 で両軸論文化可)
- llive の核 (思考因子) と LLM が architectural-level に統合される
- mcp-3d v4 ([[project_precision_metrology_llm]]) との結合可能

**弱み**:
- 実装難度極高 (Mamba 内部に hook 追加 + 訓練データ再整備)
- 既存 model を流用できず、ある程度 pre-training 必要
- 撤退条件を厳しく設定する必要

**実装工数**: 6-12 ヶ月 (Phase 5 マイルストーン、論文 PoC 含む)

### 案 D — Diffusion + Mamba ハイブリッド (実験、9 ヶ月)

**設計**:
- 粗生成: Diffusion LM (Mercury / ELYZA-LLM-Diffusion の経路)
- 精密化: Mamba ベース自己回帰でリファイン
- llive 6 stage で "Inner Monologue" 段階に Diffusion を組込み、
  "Action Plan / Finalise" 段階で Mamba 自己回帰

**強み**:
- 並列生成で latency 削減 (memory `feedback_benchmark_progressive_tokens` の
  xs/s 領域で有利)
- 推敲プロセスが人間の思考に近い (llive コンセプト整合)
- Diffusion + SSM のハイブリッドはまだ前例少ない → 論文化余地

**弱み**:
- 訓練インフラの複雑度
- Diffusion LM 自体がまだ実用域に入りきってない (品質安定性)
- 日本語 ELYZA-LLM-Diffusion は ELYZA ライセンス依存

**実装工数**: 6 ヶ月以上 (R&D 強め)

### 案 E — RWKV-7 ベース (軽量、CPU 推論最強、3 ヶ月)

**設計**:
- RWKV-7 (RNN 形 LLM, Apache-2.0) を base model に
- 推論時 RNN 形なので **CPU でも秒数百 token** 出る
- llive を真の意味で「CPU だけで動く on-prem AI」にする
- llove 表示層の token-by-token stream と相性が良い

**強み**:
- CPU only 環境 (会社 PC で GPU 無し) で実用速度
- メモリ占有が極小 (state_dim 固定)
- llove TUI の streaming 表示が滑らか
- RWKV community が活発、多言語版もある

**弱み**:
- 大規模化 (70B 級) の RWKV モデルがまだ少ない
- in-context learning が Transformer 同サイズ比で劣る
- 商用品質に達したか未検証 (要 progressive matrix で実測)

**実装工数**: 2-3 週間 (RWKV.cpp 経由で OpenAI 互換 server、既存経路流用)

---

## 2. 比較行列 (詳細は COMPARISON.md)

| 案 | 工数 | on-prem fit | 長 context | 品質 | 論文化 | リスク |
|---|---|---|---|---|---|---|
| A. Pure Mamba 7B | 1 週 | ◎ | ◎ (256k) | ○ | △ | 低 |
| B. Jamba Hybrid | 1 ヶ月 | ○ | ○ | ◎ | ○ | 中 (license) |
| C. 思考因子-Δ 橋渡し | 6-12 ヶ月 | ◎ | ◎ | ?? | ◎◎ | 高 (R&D) |
| D. Diffusion + Mamba | 6 ヶ月 | △ | ○ | ?? | ○ | 中-高 |
| E. RWKV-7 CPU | 2-3 週 | ◎◎ | ○ | △ | △ | 低 |

詳細は `COMPARISON.md` 参照.

---

## 3. 推奨戦略 — 3 軸並走 (低スペック PC primary)

memory `project_llive_dev_style` (第二の脳型スパイラル) +
`feedback_session_marathon` + 「拡張性ファースト + 低スペック PC primary」
の v0.2 制約を踏まえると、単一案に賭けず **3 軸並走**が筋. ただし
**低スペック PC 性能目標 (§0.2)** を最優先評価軸とする.

### 軸 1: 低スペック PC 実用化 (案 E + A)
- **案 E (RWKV-7) を最優先** — CPU only 環境で xs/s 領域 (§0.2 表) を満たす唯一の現実解
- 案 A (Pure Mamba 7B Q4) — 並走で動かし、GPU 有り環境のベースライン
- 1-3 ヶ月で個人 PC bench (`benchmark/low_spec.py`) を整備、§0.2 表を埋める

### 軸 2: 中期差別化 (案 B + stage-wise)
- 4-6 ヶ月で Jamba hybrid + stage-wise backend infra (`StageBackendRouter`)
- llive 6 stage と Mamba/Attention 層を直結
- license clear 後に商用品質まで上げる
- stage ごとに **軽い backend ↔ 重い backend を動的選択**で低スペック PC でも動作

### 軸 3: 長期論文化 (案 C)
- 7-12 ヶ月で思考因子-Δ 橋渡し PoC (`ThoughtFactorDeltaHook`)
- 精密工学会 + 認知科学系学会で論文
- mcp-3d v4 とセットで「精密計測 × 認知 × LLM 内部状態」3 軸論文

### 案 D は実験トラック (時間あれば、6 ヶ月以降)

---

## 4. 12 ヶ月ロードマップ

```
Month 1   案 A Pure Mamba 7B PoC → bench (progressive xl)
Month 2   案 E RWKV-7 CPU bench (xs/s 領域有利、ベースライン)
Month 3   案 A/E 切替 env + llove 表示層統合 (h.4)
Month 4   案 B Jamba hybrid 立上げ + license clear
Month 5   stage-wise backend infra (LLIVE_LLM_BACKEND_BY_STAGE)
Month 6   Jamba x llive 6 stage 実測 + 中期差別化評価
Month 7   案 C 思考因子-Δ 橋渡し 数学的設計 + 論文骨子
Month 8   PoC 実装 (Mamba 内部 hook + 訓練データ整備)
Month 9   案 D 実験 (Diffusion 粗 + Mamba 精)
Month 10  論文 draft (精密工学会向け + AI 系)
Month 11  llive v1.0 RC1 — Transformer 完全離脱完了
Month 12  v1.0 release + 多言語 docs + コミュニティ展開
```

---

## 5. 直近 30 日アクションプラン (高解像度)

memory `project_30day_action_plan_2026_05` (Week 1 dogfooding+需要定量化 /
Week 2 Engine 抽出+Core 軽量化 / Week 3 Research IDE+中国 LLM / Week 4
配布+rc1) と整合させる:

### Week 1 (5/19-5/25) — Mamba PoC 着手
- [ ] `ollama pull` できる Mamba 系 model を 2 つ選定 (Codestral-Mamba 7B
      候補と Falcon-Mamba 候補のライセンスチェック)
- [ ] llama.cpp b8864+ で Mamba 推論動作確認 (`llama-server --model ...`)
- [ ] llive 既存 `LLIVE_OPENAI_MODEL` 経路で接続 → 1 Brief 実機検証
- [ ] progressive matrix xs/s/m を実測、Transformer 7B/13B と比較

### Week 2 (5/26-6/1) — F25 Phase h.2.b + Mamba progressive matrix
- [ ] llive BriefRunner → engine bus emit bridge (h.2.b)
- [ ] Mamba progressive matrix l/xl/xxl (32k/128k/256k token) 実測
- [ ] honest disclosure 記録 (memory `feedback_benchmark_honest_disclosure`)

### Week 3 (6/2-6/8) — RWKV-7 立上げ + h.4 5 pane
- [ ] RWKV.cpp で RWKV-7 World 7B を on-prem 起動
- [ ] CPU only 環境で xs/s 実測 (Mamba 比、Transformer 7B 比)
- [ ] llove 5 pane (Memory / Loop / Thought Factors / Annotations / Brief Output)
      に Mamba/RWKV backend 経路で実 stream 流す

### Week 4 (6/9-6/15) — non-transformer rc1 + 公開準備
- [ ] llive v0.7-rc1 candidate (Mamba + RWKV backend + stage-wise infra alpha)
- [ ] docs/non-transformer/* を全部 v0.2 まで磨く
- [ ] 内部レビュー + 案 C (思考因子-Δ 橋渡し) の数学的設計に着手

---

## 6. 撤退条件 (案ごと)

| 案 | 撤退条件 |
|---|---|
| A | progressive xl で品質 5pt 以上劣化 + 改善見込み無し |
| B | Jamba ライセンス商用配布不可確定 |
| C | 数学的設計で発散 (Δ 操作が訓練不安定化) |
| D | Diffusion 部分の品質が Mamba 単体より劣る |
| E | RWKV-7 が CPU only でも実用速度に届かない |

3 軸並走で 1 案撤退しても他軸が生きる構造を堅持.

---

## 7. リスク総括

1. **EAR/地政学リスク** — 中国系 SSM/RWKV モデルを使う場合、米国輸出規制
   との関係を要確認. memory `project_fullsense_ear_origin` の起源と整合.
2. **ライセンス分散** — Apache-2.0 / Mistral / AI21 / TII Falcon 等が混在.
   FullSense 全体の dual-license (Apache-2.0 + Commercial) と衝突しないか
   model ごとに check.
3. **コミュニティ規模** — Transformer 系の半分以下. 商用品質の保証は
   FullSense 側で integration test を厚く取る必要.
4. **論文化のリスク** — 案 C は既存研究との独自性主張に時間がかかる.
   先行研究調査 (RAD コーパスで bci/neuroscience/cognitive_ai 分野) を厚く.

---

## 8. 関連 docs / memory

- `D:/projects/fullsense/docs/architecture/triz-ssm-vs-transformer.md` (起点)
- `COMPARISON.md` (本ディレクトリ、5 案比較行列詳細)
- memory `project_llive_9axis_skeleton` — 既存 skeleton への non-transformer 取込
- memory `project_llive_oka` — OKA-FX 数学層との接続
- memory `project_llive_cog_fx_factors` — 10 思考因子 (Δ 橋渡し対象)
- memory `project_precision_metrology_llm` — 3DGS × Mamba 256k context
- memory `project_llive_v07_rust_acceleration` — Rust 化候補に Mamba 推論層
- memory `project_30day_action_plan_2026_05` — Week 1-4 整合
- memory `feedback_competitor_benchmark` — Claude Code / Perplexity etc. との比較軸

---

## 改訂履歴

- 2026-05-18 — draft v0.1 (ユーザーゴール「Transformer 以外で llive 完成」を
  受けて、5 案 deep dive + 12 ヶ月 + 30 日アクション + 3 軸並走戦略を策定)
