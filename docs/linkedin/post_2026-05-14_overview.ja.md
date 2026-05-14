# LLM の「忘却」と向き合うための個人プロジェクト ― llive

> 自己進化型モジュラー記憶 LLM フレームワーク `llmesh-llive` を設計・実装している話。
> AI を理解する手段として、また自分のキャリアの軸を作る手段として、このプロジェクトを進めています。

## なぜ作ったか

LLM をプロダクトに組み込むほど、ある共通の壁にぶつかります。

> 新しい知識を覚えさせると、なぜか古い判断基準が壊れる。

この **catastrophic forgetting (破滅的忘却)** は、規制業界や監査必須の現場で AI 活用が止まる最大の理由のひとつです。`llive` は、この問題を「コアの巨大な LLM 重みを再学習せずに、どう継続的に能力を吸収するか」という設計問題に置き換えて取り組む個人プロジェクトです。

公開してみると、これは AI を **使う側** にとっても、AI を **作る側** にとっても、最も基礎的な理解を求められるテーマでした。仕事で機械学習や LLM を扱う人なら、必ず一度は説明責任を求められる領域です。

## llive の設計の核

`llmesh-llive` は次の 8 つの設計方針で構成されています。

1. **固定コア + 可変周辺** — Decoder-only LLM コアは凍結。Adapter / LoRA / 4 層外部記憶 / 可変長 BlockContainer で能力を吸収。
2. **4 層メモリの責務分離** — semantic（知識）/ episodic（経験）/ structural（関係）/ parameter（差分重み）。
3. **宣言的構造記述** — sub-block 列を YAML で表現。AI が提案・比較しやすい単位に揃える。
4. **審査付き自己進化** — オンラインは memory write と軽微 routing のみ、構造変更はオフライン審査経由。
5. **生物学的記憶モデルを直接埋め込み** — 海馬-皮質 consolidation cycle、surprise score、phase transition。
6. **形式検証付き promotion** — Lean / Z3 / TLA+ による構造的不変量検査を LLM 評価より前に挟む。
7. **llmesh / llove ファミリー統合** — 産業 IoT センサを episodic memory に直結、TUI で HITL を完結。
8. **TRIZ アイデア出しを内蔵** — 40 原理 + 39×39 矛盾マトリクス + ARIZ + 9 画法を mutation policy として実装し、メトリクスの矛盾を自動検出 → 原理マッピング → CandidateDiff 生成まで自走。

## なぜキャリアの観点で重要だったか

LLM 周辺の技術は陳腐化が早く、表面的なキャッチアップだけでは差別化しにくい領域です。`llive` を作る過程で、自分の中に残ったのは次のような**設計判断の蓄積**でした。

- **継続学習をプロダクトに組み込む難しさを、机上ではなく実装レベルで言語化できる**ようになった。
- **形式検証 (Lean / Z3 / TLA+)** を LLM の評価より前に挟むことで、評価コストとリスクを下げる設計パターンを身につけた。
- **生物学的記憶モデルを CS の世界に翻訳する作業**を通じて、複数分野の知見をブリッジする能力が鍛えられた。
- **TRIZ 40 原理を mutation policy** に落とすという「特許の世界の知」を ML に持ち込む経験を得た。
- **Ed25519 署名 + SHA-256 監査チェーン** を継続学習に組み込む設計を経験し、規制業界 AI に近づくための基礎が見えた。

これらは、AI スタートアップでも、規制業界での AI 導入チームでも、研究開発チームでも問われる種類のスキルです。

## 数字で見る現在地 (2026-05-14)

- **v0.5.0** Phase 5 first wire-in リリース ― Rust kernel をホットパスへ接続。
- **444 tests / 0 lint** (v0.4.0 439 + RUST-03 parity 5)。
- Z3 静的検証 / Failed Reservoir / Reverse-Evo Monitor / TRIZ Self-Reflection / Ed25519 Signed Adapter / SHA-256 Audit Chain は v0.3.0 で確立済。
- v0.4.0 で Rust acceleration skeleton (PyO3 0.22 + Cargo workspace + RUST-13 parity harness) 確立。v0.5.0 で `compute_surprise` (MEM-07) を Rust 経路へ自動委譲、不在時 numpy fallback、**1e-6 parity 保証**。
- [Unreleased]: F25 (g) `LoveBridge` writer ― llive ↔ llmesh ↔ llove を MCP 経由で繋ぐ shim 完成。
- PyPI: `pip install llmesh-llive`

## どこに向かうか

この OSS は、規制業界の現場で AI 導入を進めたいエンジニアが「実装ベースで議論できる雛形」になることを目指しています。`llmesh` (オンプレ MCP ハブ) と `llove` (TUI dashboard) を組み合わせると、クラウドを使わず、監査証跡を残し、現場で観測できる継続学習基盤になります。

興味のある方は、まず PyPI から触れてみてください。設計判断・失敗・進化過程を、可能な限りリポジトリと docs に残しています。

> GitHub: <https://github.com/furuse-kazufumi/llive>
> PyPI: `pip install llmesh-llive`

#AI #LLM #ContinualLearning #MLOps #FormalVerification #OpenSource #個人開発 #キャリア
