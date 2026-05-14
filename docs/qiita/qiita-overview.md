<!--
title: LLM の「忘却」に正面から向き合う ― 4 層メモリ × 形式検証 × TRIZ 自演化 × Rust ホットパスを Python で実装した話 (llive v0.5.0)
tags: Python,LLM,継続学習,形式検証,Rust
-->

# LLM の「忘却」に正面から向き合う ― 4 層メモリ × 形式検証 × TRIZ 自演化 × Rust ホットパスを Python で実装した話 (llive v0.5.0)

> Self-evolving modular memory LLM framework — `pip install llmesh-llive`

## TL;DR

- **llive** は、固定 LLM コアの周りに **4 層外部記憶** (semantic / episodic / structural / parameter) と **可変長 BlockContainer** を配置し、コア重みを再学習せずに能力を継続的に取り込む Python フレームワーク。
- promotion (構造変更) は **Lean / Z3 / TLA+ による形式検証** を LLM 評価より先に通す。これだけで promote 失敗の早期検出と評価コスト削減ができる。
- **TRIZ 40 原理 + 39×39 矛盾マトリクス + ARIZ + 9 画法** を mutation policy として実装。メトリクスの矛盾を自動検出 → 原理マッピング → CandidateDiff 生成まで自走する。
- **v0.5.0** (2026-05-14) で Phase 5 first wire-in を達成。Rust kernel をホットパス (`compute_surprise` / 時間減衰) に接続し、Python fallback と **1e-6 parity** を保証。**444 tests / 0 lint**。
- v0.3.0 で Phase 3 (Controlled Self-Evolution MVR) + Phase 4 (Production Security MVR) を同時リリース、Ed25519 署名 adapter + SHA-256 audit chain 完備。
- リポジトリ: <https://github.com/furuse-kazufumi/llive> / PyPI: `pip install llmesh-llive`

```bash
pip install llmesh-llive            # core (cryptography 同梱)
pip install llmesh-llive[torch]     # HF transformers + faiss + peft + hdbscan
pip install llmesh-llive[verify]    # Z3 SMT 検証レイヤ (EVO-04)
```

---

## なぜ作ったか

LLM をプロダクトに組み込むほどぶつかる壁:

> 新しい知識を覚えさせると、なぜか古い判断基準が壊れる。

これは **catastrophic forgetting (破滅的忘却)** と呼ばれ、規制業界・監査必須環境で AI 活用が止まる最大の理由のひとつ。「巨大な LLM コアを再学習せずに、継続的に能力を吸収する設計問題」に翻訳して取り組んでいるのが `llive` です。

## 設計の核

### 1. 固定コア + 可変周辺

Decoder-only LLM コアは凍結。能力吸収は次の周辺コンポーネントが担う。

| 層 | 担当 |
|---|---|
| Adapter / LoRA | 関数的 fine-tune |
| 4 層外部記憶 | 知識・経験・関係・差分重み |
| BlockContainer (可変長) | 構造的能力拡張 |

### 2. 4 層メモリの責務分離

```
semantic      ─ 知識 (事実・概念・定義)
episodic      ─ 経験 (時系列イベント、surprise score 付)
structural    ─ 関係 (グラフ、依存、参照)
parameter     ─ 差分重み (Adapter / LoRA / 部分 fine-tune)
```

書き込みは **surprise-gated** ― コア LLM が予測できる平凡なものは書かない。

### 3. 宣言的構造記述 (YAML)

```yaml
container:
  name: erp_v3
  blocks:
    - kind: lora
      target: q_proj,v_proj
      rank: 16
    - kind: memory_router
      to: semantic
      hint: "ERP 業務知識"
```

AI 自身がこれを **提案・比較しやすい単位** にしている。

### 4. 形式検証付き promotion

ここが他の継続学習系との最大の差。promote (構造変更) を本番反映する前に、

1. **Quarantined zone** で shadow run
2. **Lean / Z3 / TLA+** で構造的不変量を証明
3. それから LLM 評価 (eval スイート)

を回す。形式検証で**先に弾ける promote** は、LLM 評価を回さずに済む。これは検証時間と GPU コストの両方に効く。

### 5. 生物学的記憶モデル直接埋め込み

海馬 - 皮質 consolidation cycle を擬似的に実装:

| イベント | 動作 |
|---|---|
| episodic write 蓄積 | 短期記憶溜まる |
| consolidation cycle (周期実行) | semantic / structural へ昇華 |
| phase transition 検知 | 大規模再構成のトリガ |

### 6. TRIZ Self-Reflection (40 原理 mutation)

llive 内で「メトリクスの矛盾」が観測されると、TRIZ 矛盾マトリクスから**改善するパラメータ × 悪化するパラメータ**で原理を引く。

例: BWT (古い知識保持) vs 新規タスク習得速度 → TRIZ #1「分割」/ #15「動的性」/ #35「パラメータ変更」など。

これを mutation policy として CandidateDiff に変換し、Quarantined zone で評価する。

### 7. Failed Reservoir + Reverse-Evo Monitor

- **Failed Reservoir**: 過去の失敗 promote を「学習データ」として再利用。同じパターンで失敗しないようにする。
- **Reverse-Evo Monitor**: 本番 BWT 劣化を検知すると、前バージョン署名済 adapter を rollback 候補に出す (auto-promote はしない、人間 approve 必須)。

### 8. Ed25519 + SHA-256 audit chain

| 何を | どう守るか |
|---|---|
| adapter promote | release_manager の Ed25519 鍵で署名 |
| 全 inference / memory write / model change | SHA-256 chain に append |
| audit verify | `llive audit verify` で全期間チェーン整合検証 |

これで FDA 21 CFR Part 11 / J-SOX / バーゼル III に対する**実装ベースの説明材料**が揃う。

---

## 実装で気を付けたこと

### Z3 を「LLM 評価より先に挟む」設計の効能

LLM 評価は遅いし高い。Z3 で先に静的検証することで、

- 構造的に矛盾する promote を **GPU を回す前に弾ける**
- 形式検証 fail のメッセージは LLM 評価 fail より**人間に説明しやすい**
- 規制側にも「自動検証で stop した」と明確に言える

### TRIZ × LLM の組み合わせ

「LLM がブレインストームすればよい」と片付けがちだが、TRIZ は **過去 100 万件以上の特許** から抽出された矛盾解決の知。LLM の即興より体系性で勝る場面が多い。
RAD コーパス (本フレームワーク内蔵) と接続することで「TRIZ #15 動的性 を使う前例が、医療 AI 領域でも n 件ある」という裏付けが取れる。

### 並行パイプラインの分離

オンライン経路 (memory write + 軽微 routing) と、オフライン経路 (構造変更 promote) を厳密に分けた。レイテンシ予算と安全境界の両方が綺麗になる。

---

## 数字で見る現在地 (2026-05-14)

- **v0.3.0** Phase 3 + Phase 4 同時リリース
- **429 tests / 98% coverage / 0 lint warnings**
- Z3 静的検証 / Failed Reservoir / Reverse-Evo Monitor / TRIZ Self-Reflection / Ed25519 Signed Adapter / SHA-256 Audit Chain
- 次期: Phase 5+ Rust 高速化 (要件 v0.7 定義済)

---

## ファミリー構成

`llive` は単独でも使えますが、ファミリーで組むと真価が出ます。

| プロダクト | 役割 |
|---|---|
| **llive** (本記事) | 自己進化型モジュラー記憶 LLM |
| **llmesh** | セキュア LLM ハブ (オンプレ MCP サーバ + プライバシーフィルタ) |
| **llove** | TUI dashboard (BWT / 監査 / 概念グラフを観測) |

詳細はそれぞれのリポジトリを参照。

---

## まとめ

- LLM の「忘却」は実運用の本丸。**コア固定 + 周辺可変** で取り組むと、再学習コストとコンプライアンス問題の両方が下がる。
- promote の前に **Z3 / Lean / TLA+** を挟むだけで、LLM 評価コストとリスクが大きく減る。
- TRIZ を mutation policy にすると、ブレストではなく**体系的な矛盾解決**として継続学習を回せる。

OSS なので、規制業界の AI 落としどころで困っている方は、ぜひ実装を眺めて議論の叩き台にしてください。

> GitHub: <https://github.com/furuse-kazufumi/llive>
> PyPI: `pip install llmesh-llive`
