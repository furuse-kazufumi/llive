# llive 要件定義 v0.5 — Spatial Memory / Metrology-Grade Gaussian Tokens

**Drafted:** 2026-05-13
**Status:** **要件メモのみ（実装はゆっくり、Phase 2-4 完了後の独立 milestone）**
**Type:** Future-work addendum (Phase 5+ 想定)
**Priority:** Low (現在の高優先度は Phase 2 Adaptive Modular System の実装)

> 「3DGS の SH係数 = LLM 埋め込みの構造化版」というアイデアを、論文化を見据えた研究テーマ
> として llive に紐づけて記録する。実装着手は Phase 4 完了後を想定。本書は **思想と差別化軸の
> 早期固定** を目的とし、詳細仕様は PoC 進捗に応じて加筆する。

---

## 1. 中核アイデア

**「3DGS の Spherical Harmonics 係数を VQ 量子化して LLM のトークンとして扱う」** ことで、空間
情報を計測グレード精度を保ったまま LLM の推論対象にする。

```
3D 計測点群（高精度 XYZ）
  → 色付け (Depth Map 投影手法等)
  → 3DGS 化（Gaussian 単位の SH係数 + scale + quaternion + center）
  → SH 係数を VQ で離散化 → コードブックインデックス列
  → LLM への入力（テキストトークンと同列に扱える整数列）
  → 自然言語で「異常箇所の特定 / 設計 CAD との差分 / 前回計測との差」を回答
```

---

## 2. 既存研究との地図 (公開を阻む競合)

| 研究 | 提供物 | 重なる/異なる |
|---|---|---|
| Point-LLM / 3D-LLM / Chat-3D / LL3DA | 点群を LLM 入力 (PointNet++ 系 encoder) | 重なる: 「3D を LLM トークン化」 |
| LangSplat / Feature 3DGS / OpenGaussian | CLIP/DINO 特徴を 3DGS に**埋め込む** | **逆方向**: あちらは LLM→3DGS、本案は 3DGS→LLM |
| Scaffold-GS / 4D-GS / Trellis | 3DGS の圧縮 / 時間拡張 / 生成 | 重なる: SH 圧縮 |
| VQ-3D / 3D-VQGAN / TVQ-VAE | 3D shape の VQ 量子化 | 重なる: VQ 離散化 |
| Diff Rendering for Inspection (BMW / MS) | CAD vs スキャン diff | LLM 介在せず |

**素直な評価**: 「SH × VQ × LLM」のみを核に書くと既存と差分が薄い。下記 3 軸を束ねて初めて
査読耐性のある独自性が出る。

---

## 3. 差別化軸（査読耐性版、推奨 A+B+C 重畳）

| 軸 | 内容 | 新規性 | ユーザ専門との接点 |
|---|---|---|---|
| **A. 計測精度保存** | Gaussian の中心 (x,y,z) + scale + quaternion を計測グレードで保持、SH は appearance のみに限定。多くの 3D-LLM は downsampling で精度を失う | ★★★★ | ★★★★★ |
| **B. クロス時間比較** | 同一対象の反復計測 → Gaussian 単位での時系列 diff、token-level で LLM が「どの粒子が変化したか」を localize | ★★★★★ | ★★★★ |
| **C. CAD 接地** | CAD primitive (平面/円筒/球) の解析的 SH signature と VQ codebook を bridge、symbolic CAD ↔ continuous 3DGS を LLM で reasoning 接続 | ★★★★ | ★★★★ |
| D. SH 次数階層 = multi-resolution token | degree 0/1/2/3 truncation で hierarchical token、interpretable (DC=色平均 / l=1=方向勾配) | ★★★ | ★★ |

**推奨差別化軸**: A + B + C を束ねた **「Metrology-Grade Gaussian Tokens with CAD Anchoring
for Temporal Defect Reasoning」**。学術 (CV/Graphics) と産業 (Manufacturing) 双方の cover
letter が書け、ユーザの実専門が moat になる。

---

## 4. PoC ロードマップ（最短経路、論文化想定）

| PoC | 目的 | 期間目安 | 中間成果物 |
|---|---|---|---|
| 0 | SH 係数を LLM トークンとして扱える最小実証 | 2-4 週 | 単一シーン → SH-VQ → token id 列 → Claude / Llama に投入、ベースライン測定 |
| 1 | VQ codebook semantics 解析 | 1-2 ヶ月 | 計測スキャン 1k+ で codebook 学習、t-SNE で「平面/曲面/エッジ/穴/傷」分離を検証。**workshop paper 第一候補** |
| 2 | クロス時間 diff + 異常局所化 (軸 B) | 2-3 ヶ月 | 同一部品 T0/T1 → Gaussian alignment → diff token を LLM が localize |
| 3 | CAD anchoring (軸 C) | 2-3 ヶ月 | STEP/IGES の primitive → 解析的 SH → codebook 共有学習、定量評価 (IoU / chamfer / spec deviation mm) |
| 論文化 | A+B+C 統合 | 全 6-9 ヶ月 | 想定 venue: CVPR / ICCV / ICRA / IROS / CASE / IEEE T-ASE / IEEE T-IM |

**Priority note**: 実装着手は **Phase 2-4 完了後**。本要件は「思想を早期固定」が目的であり、
論文化はゆっくり進める。

---

## 5. 現プロジェクトへの落とし込み

| プロジェクト | 役割 |
|---|---|
| **MCP Spatial Asset Profile** (未着手) | PoC 0 の reference implementation ホーム。SH-VQ tokenizer を MCP resource として公開する core spec を詰める |
| **llive Phase 5** | PoC 1-2 の研究実装ベース。4 層メモリに **spatial memory** (5 層目) を追加、Gaussian を MemoryNode として保持、BayesianSurpriseGate を spatial novelty 検出器に転用 |
| **llmesh Phase 4 INT-01** | PoC 2-3 の産業 IoT データパス。LiDAR / 構造化光 / 深度カメラの payload に PointCloud / 3DGS stream を許容 |
| **llove F15+** | 空間 token と画像の対比表示 (TUI 内 3DGS viewer、CAD diff 可視化) |
| **計測 × LLM 研究 memo** | 論文の running notes、先行研究調査、査読対策の集約 |

---

## 6. Spatial Memory 要件 (将来 Phase 5、現時点は概略のみ)

実装着手前にここを詳細化する。現時点では memory layer 構成のみ確定：

- **SPM-01**: spatial memory layer (5 層目) を MemoryNode の `memory_type=spatial` として導入
- **SPM-02**: GaussianToken の永続化 (center / scale / quaternion / SH係数 / VQ codebook id)
- **SPM-03**: BayesianSurpriseGate を spatial novelty 検出に転用
- **SPM-04**: cross-time Gaussian alignment (Gaussian ID 永続化)
- **SPM-05**: CAD primitive と VQ codebook の bridge (CAD STEP → 解析的 SH signature)
- **SPM-06**: ConceptPage の page_type に `spatial_concept` 追加 (LLW-03 拡張)
- **SPM-07**: `llive wiki ingest --type pointcloud|3dgs` を LLW-06 に追加
- **SPM-08**: spatial token を含む LLM prompt の構築 helper (`llive.spatial.prompt`)

---

## 7. Out of Scope (v0.5 段階)

- **PoC 0-3 の具体実装** — 思想の早期固定のみ、実装は Phase 2-4 完了後
- **専用ハードウェア統合** — まずは公開データセット (3DGS scenes) + 手元の OSS toolkit (gsplat, gaussian-splatting-pytorch) で評価
- **論文 venue の確定** — 差別化軸 A+B+C で PoC 0-1 を進めてから venue 選定
- **OSS 公開** — 当面は内部 PoC、論文 acceptance 後に OSS 化検討

---

## 8. 関連 memory / docs

- `memory/project_mcp_spatial_asset.md` — MCP Spatial Asset Profile 全体像
- `memory/project_precision_metrology_llm.md` — 「計測 × LLM」研究テーマ memo (新規)
- `memory/project_llive.md` — llive 全体像
- `docs/family_integration.md` — llmesh / llove との API 互換
- llmesh `ROADMAP.md` Phase 4 INT-01 — sensor bridge 拡張先

---

*Drafted: 2026-05-13*
*Implementation: deferred to Phase 5+ (Phase 2-4 完了後の独立 milestone)*
*Paper-writing: ゆっくり、論文化は PoC 進捗ベースで*
