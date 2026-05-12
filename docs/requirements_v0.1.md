# 自己進化型モジュラー記憶 LLM フレームワーク 要件定義書 (v0.1)

> 原型版。ユーザから 2026-05-13 に受領した要件定義原文を保存したもの。
> v0.2 以降の拡充（TRIZ 由来要件・設計パターン・llmesh/llove 統合）は `requirements_v0.2_addendum.md` を参照。

## 文書の目的
本書は、自己進化的な拡張能力を持つ次世代LLMフレームワークの要件定義をまとめたものである。対象は、既存のDecoder-only LLMを安定した中核として利用しつつ、外部記憶、モジュラー構造、可変長ブロックコンテナ、構造進化マネージャを追加し、新しいアイデアを継続的に取り込める研究開発基盤を構築することである。

本仕様は、Claude Code のようなAI実装支援環境に入力しやすいよう、要件、責務分離、データモデル、拡張ポイント、評価指標、品質条件、実装フェーズを明示的に定義する。固定重みへの一括学習だけでは継続学習時の忘却や改修コストが大きいため、近年は modular memory や外部記憶を使って安定性と適応性を分離する設計が重要とされている。

## 背景と設計方針
大規模言語モデルに対して、新しい能力を追加する方法としては、重み全体を再学習する方式、軽量アダプタやLoRAを差し込む方式、外部知識を参照する方式、構造自体を探索して変化させる方式がある。研究では、LLMを用いたアーキテクチャ探索や、反省型フィードバックを取り入れた探索効率化、継続学習向けの modular memory の有効性が報告されている。

本フレームワークでは、次の3つの矛盾を主な設計対象とする。

- 安定な中核重みを維持したいが、新しい能力はすばやく追加したい。
- 探索空間は広く取りたいが、評価コストは抑えたい。
- 記憶容量を増やしたいが、ノイズや忘却を抑えたい。

これらに対し、本仕様では「固定コア + 可変モジュール + 多層外部記憶 + 審査付き進化」という分離設計を採用する。構造進化をオンラインで本体へ直接反映せず、オンライン適応とオフライン昇格審査を分離することで、研究の自由度と運用時の安全性を両立する。

## システムの到達目標
本システムの到達目標は、単一のLLMモデル実装ではなく、能力の追加・切り替え・検証・失敗解析・再評価・昇格を繰り返せる「進化可能なAI基盤」を作ることである。

到達目標は以下の通りとする。

- 既存の7B〜14B級 Decoder-only モデルを中核として採用し、重み全体を頻繁に更新しなくても能力拡張できること。
- 外部記憶を semantic memory、episodic memory、structural memory、parameter memory に分離し、相互参照可能であること。
- Transformer block を固定単位ではなく、サブブロック列を持つ可変長コンテナとして記述・評価できること。
- 構造候補や差分候補をYAMLなどの宣言的形式で表現し、AIが生成・変更・比較しやすいこと。
- 品質、遅延、VRAM、忘却耐性、モジュール利用率、メモリ汚染率を同時に監視し、多目的最適化できること。
- 将来的に新しい sub-block、memory backend、routing policy、進化アルゴリズムを追加しても、既存資産を壊さず拡張できること。

## 対象範囲

### 対象内
- 既存Decoder-only LLMをラップする実行基盤
- 可変長ブロックコンテナの定義・解釈・評価機構
- 多層外部記憶の統合インターフェース
- ルータおよびモジュール選択機構
- 自己進化候補の提案、評価、昇格、ロールバック機構
- 実験管理、可観測性、トレーサビリティ、ベンチマーク機構
- 研究用途から将来のプロダクションPoCへ移行可能な開発構造

### 対象外
- 基盤モデルそのものの大規模事前学習の全面再実装
- 大規模GPUクラスタスケジューラの独自開発
- 完全自律で人間レビューなしに本番構造変更を行う機構

## 用語定義

| 用語 | 定義 |
|---|---|
| Core Model | ベースとなる既存 Decoder-only LLM。本仕様では頻繁に直接変更しない安定中核。 |
| Block Container | Transformer block を構成するサブブロック列を保持する可変長実行単位。 |
| Sub-block | attention、memory_read、adapter、ffn、memory_write 等の再利用可能な最小機能要素。 |
| Router | 入力状態やメタ情報に基づき、どの block container / sub-block / adapter を使うか決定する機構。 |
| Semantic Memory | 埋め込み検索主体の知識記憶層。 |
| Episodic Memory | 実行履歴、観測系列、失敗履歴などの時系列経験記憶層。 |
| Structural Memory | グラフ構造や依存関係など、関係性中心の記憶層。 |
| Parameter Memory | LoRAやAdapterなどの差分重みセットを管理する記憶層。 |
| Evolution Manager | 構造候補や差分候補の生成、評価、昇格判定、ロールバックを担う制御層。 |
| Surprise Score | 想定外度や既存知識での説明困難度を示す指標。memory write や deeper path 選択に利用する内部シグナル。 |

## 全体アーキテクチャ
本システムは、6 層構成とする。

1. Interface Layer
2. Orchestration Layer
3. Core Model Layer
4. Memory Layer
5. Evolution Layer
6. Observability & Benchmark Layer

> v0.2 で **8 層**（llmesh I/O 層 + llove HITL 層を分離）に拡張する案あり。`requirements_v0.2_addendum.md` 参照。

各層の責務は原文記載のとおり（Interface / Orchestration / Core Model / Memory / Evolution / Observability）。

## 中核コンセプト

1. **固定コア + 可変周辺** — コアモデルは安定維持、能力追加は adapter / LoRA / memory / routing / container variation で吸収
2. **記憶と重みの責務分離** — 即時知識・経験・構造・能力差分は外部層または差分重みに保持
3. **構造変更は宣言的に扱う** — sub-block の追加・削除・順序変更・条件分岐は YAML/JSON スキーマで定義
4. **進化は審査付き** — オンラインで本体構造を勝手に変えない、オフライン審査を経て昇格

## 機能要件（FR-01〜FR-11）

- **FR-01** Core Model 抽象化（`BaseModelAdapter` で HF / vLLM 等を統一）
- **FR-02** Block Container 定義（宣言的、複数 sub-block、順序・分岐・コストメタ）
- **FR-03** Sub-block プラグイン（pre_norm / causal_attention / GQA / memory_read / cross_memory_attention / adapter / lora_switch / ffn_small / ffn_large / moe_ffn / memory_write / compress / skip / reflective_probe）
- **FR-04** Router（token 特徴 / hidden state / task_id / memory 結果 / surprise / 過去性能、deterministic/stochastic/policy、explanation log）
- **FR-05** 多層 Memory（semantic vector / episodic time-series / structural graph / parameter adapter、共通 ID）
- **FR-06** Memory Read/Write 制御（条件付き write、surprise / novelty / confidence drop / human feedback / outcome、provenance 必須、TTL/merge/dedup）
- **FR-07** Evolution Manager（YAML diff 自動生成、zero-cost proxy、人間レビュー、昇格・却下・保留・ロールバック）
- **FR-08** 評価機構（task quality / latency / VRAM / forgetting / ablation / route usage / pollution / dead block）
- **FR-09** 実験トレーサビリティ（experiment_id / candidate_id / dataset_id / model hash / config hash）
- **FR-10** 可視化（container 利用率 / sub-block 発火率 / memory link graph / 忘却推移 / 性能フロンティア）
- **FR-11** 人間レビュー介在（昇格前 HITL、観点: 安全性 / 再現性 / 過学習 / 解釈性 / コスト）

> v0.2 で **FR-12〜FR-22** を追加。

## 非機能要件（NFR-01〜NFR-06）

- **NFR-01** 拡張性（plugin で sub-block / backend / routing / evolution / modality 追加可能）
- **NFR-02** ロバスト性（backend 落ち・router 異常・未知 sub-block への縮退/拒否）
- **NFR-03** 可観測性（構造化ログ、OpenTelemetry 互換、暗黙状態禁止）
- **NFR-04** 保守性（仕様駆動、schema 必須、コメントで意図表現）
- **NFR-05** テスト容易性（sub-block / router / memory のモック、軽量 CI ベンチ）
- **NFR-06** 安全性（署名付き承認フロー、unsafe source の write 制限、experiment / production 名前空間隔離）

## 論理コンポーネント / データモデル / 宣言的スキーマ / 拡張ポイント / 自己進化運用 / 評価 / 品質保証 / ディレクトリ構成 / Claude Code 実装ガイド / フェーズ / リスクと対策 / 受け入れ基準 / 将来研究テーマ / 優先順

原文記載のとおり（本ファイルは原型保存目的）。詳細項目は v0.2 追補章で構造化済の拡充版を参照。

## 実装フェーズ

- **Phase 1: Minimal Viable Research Platform** — BaseModelAdapter / Semantic+Episodic memory / Rule-based Router / ContainerSpec schema / 単一 candidate 評価
- **Phase 2: Adaptive Modular System** — Structural+Parameter memory / Adapter bank / surprise-gated write / Container variation / 可視化
- **Phase 3: Controlled Self-Evolution** — AI candidate generation / mutation templates / zero-cost proxy / promotion・rollback / forgetting bench 自動化
- **Phase 4: Multimodal / Advanced Research** — external encoder bridge / graph reasoning / uncertainty-aware routing / population-based evolution / production PoC

## 受け入れ基準

最低限以下を満たすこと:
- ContainerSpec を読み込み、3 種類以上の sub-block を順序実行
- semantic + episodic memory の read/write
- router で 2 経路以上選択 + 理由ログ
- candidate diff 読込 + A/B ベンチ評価
- forgetting を含む評価レポート
- memory link と route trace の可視化
