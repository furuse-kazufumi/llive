# llive 要件定義 v0.4 — LLM Wiki 視点での再整理

**Drafted:** 2026-05-13
**Status:** **要件追加（実装は Phase 2 以降、本ドキュメントでは設計指針のみ確定）**
**Type:** Addendum to v0.1 + v0.2 + v0.3 — v0.3 完了後の概念整理

> v0.1〜v0.3 で「自己進化型モジュラー記憶 LLM 基盤」として要件を積み上げてきたが、
> Karpathy が 2026-04 に提案した **LLM Wiki パターン** と llive の memory fabric / consolidation
> サイクルが構造的にほぼ同型であることを認識した。本書は v0.3 までの要件を **LLM Wiki の
> 観点で再解釈し、不足要件を追加する** ことで、設計の説明可能性と外部への位置づけを強化する。

---

## 1. LLM Wiki パターンとは

Andrej Karpathy が 2026-04 に Gist として提案した知識管理アーキテクチャ。3 層構造で構成される：

1. **生ソース層 (raw sources)** — 論文 / 記事 / 画像 / コードなどの変更不可の原資料
2. **Wiki 層 (compiled knowledge)** — LLM が管理する Markdown ベースの概念ページ群、相互リンクと要約付き
3. **スキーマ層 (schema / prompts)** — どんなページを作るか、どう更新するかを定義する設計図

RAG (オンデマンド検索拡張) との違いは、**知識を毎回検索するか、一度コンパイルしてから使い回すか**。LLM Wiki は「編集済み知識キャッシュ」を継続的に育てる **コンパイル型** アプローチ。

参考: https://cloco.co.jp/blog/karpathy-llm-wiki-rag-alternative 他

---

## 2. llive と LLM Wiki の対応関係

llive の既存設計 (v0.1〜v0.3) は、明示的に意図したわけではないが LLM Wiki の 3 層構造を内包している：

| LLM Wiki の概念 | llive 既存要素 (v0.1〜v0.3) | 対応する FR/REQ |
|---|---|---|
| 生ソース層 | episodic memory (時系列 append-only) | FR-05 / MEM-02 |
| Wiki 層 | semantic memory + structural memory (graph) | FR-05 / MEM-01 + MEM-05 |
| スキーマ層 | ContainerSpec / SubBlockSpec / CandidateDiff YAML | FR-02 / FR-03 / FR-07 |
| LLM 編集者 | Hippocampal Consolidation Scheduler | FR-12 |
| 矛盾指摘 | Contradiction Detector | FR-23 |
| ページ間リンク | structural memory (graph) edges | FR-05 / MEM-05 |
| ソース追跡 (provenance) | Provenance dataclass + signed_by | FR-06 / MEM-03 |
| 改ざん検知 | Quarantined Memory Zone + 署名検証 | FR-17 / SEC-01 |

**結論：llive を「LLM Wiki の参照実装」として外向きに位置づけることが可能。** Karpathy の提案は静的な Markdown ファイル群を前提としているが、llive は同じ思想を「コアモデル不可侵 + 構造進化 + 形式検証付き promotion」まで拡張する。

---

## 3. 追加要件 (v0.4 LLW シリーズ)

v0.3 までで未明示だった、LLM Wiki として運用する上で必要な要件を **LLW-01 〜 LLW-08** として追加する。実装フェーズは v0.1 ロードマップに合わせて割り当てる。

### LLW-01: Wiki ページの第一級表現
**Phase: 2 (MEM-08 consolidation の出力強化として)**

semantic memory に蓄積される個別 entry に加え、**「概念ページ (ConceptPage)」** という上位構造を導入する。ConceptPage は以下を持つ：

- `concept_id` (kebab-case slug)
- `title`
- `summary` (LLM が consolidation 時に生成)
- `linked_entries` (semantic memory entry_id のリスト、エビデンス)
- `linked_concepts` (他 ConceptPage への `[[slug]]` 形式リンク)
- `last_updated_at`
- `provenance` (どの episodic events からコンパイルされたか)
- `schema_version`

ConceptPage は structural memory (graph) のノードとして表現され、entries / concepts はエッジでつながる。Markdown 表現 (`wiki/<concept_id>.md`) への dump / load 機能を備える。

### LLW-02: Wiki Compilation Pipeline
**Phase: 2 (FR-12 の拡張)**

Hippocampal Consolidation Scheduler を「**Wiki Compiler**」として再定義する。サイクル内で：

1. episodic memory の未コンパイル events を batch で読む
2. 既存 ConceptPage との関連を LLM に問い合わせ
   - 新規概念か / 既存ページの更新か / 既存ページの統合 (merge) か / 既存ページの分割 (split) か
3. 該当 ConceptPage を作成・更新・統合・分割
4. linked_concepts をリンク張替えし、グラフ整合性を保つ
5. consolidation 結果を candidate diff として記録 (rollback 可能)

### LLW-03: Wiki Schema (Page Type) 定義
**Phase: 2**

ConceptPage には `page_type` 属性を持たせ、用途別のテンプレート (= スキーマ層) を YAML で定義する。例：

- `domain_concept` (例: "BlockContainer", "surprise gate")
- `experiment_record` (CandidateDiff 結果のページ)
- `failure_post_mortem` (Failed-Candidate Reservoir の説明ページ)
- `principle_application` (TRIZ 原理 × llive 文脈の応用例)

各 page_type ごとに JSON Schema を `specs/wiki_schemas/` に置き、ConceptPage の structured fields を検証する。

### LLW-04: 矛盾検出と Wiki への反映
**Phase: 3 (TRIZ-02 / FR-23 と統合)**

Contradiction Detector が運用メトリクスからではなく、**ConceptPage 内容 (summary / linked_entries の主張)** からも矛盾を抽出できるようにする：

- 2 つの ConceptPage が同一トピックで異なる結論を示している
- linked_entries 間で数値や方針が食い違う
- 旧版と新版で線形に矛盾している (改訂忘れ)

検出された矛盾は新規 ConceptPage (`contradiction_report`) として書き戻され、TRIZ Principle Mapper への入力になる (FR-24)。

### LLW-05: Wiki diff & 履歴管理
**Phase: 2-3**

ConceptPage の更新は **CandidateDiff** スキーマを再利用する：

- 既存 `insert_subblock` / `remove_subblock` / `replace_subblock` パターンの類似で、`add_concept` / `update_concept` / `merge_concepts` / `split_concept` を追加
- 各 diff は invert 可能、Saga パターンで段階 rollback 可能
- Wiki への変更も Evolution Manager (L6) を経由する → audit / HITL / 形式検証 gate が自動適用される

### LLW-06: 外部生ソースの ingest
**Phase: 2**

llmesh I/O Bus 経由で受信した外部データ (論文 / 記事 / sensor stream) を episodic memory に書き込むだけでなく、Wiki Compiler が ingest 対象に含められるようにする：

- ingest 専用 CLI: `llive wiki ingest --source <path|url> --type paper|article|sensor`
- 大きなソースは chunking + 要約 → episodic events 群として書き込み、provenance に `derived_from: [source_id]` を残す
- ingest 時点で「どの ConceptPage 候補と関連が高いか」を LLM に推定させ、Wiki Compiler のヒントとして渡す

### LLW-07: llove TUI での Wiki 閲覧
**Phase: 2-4 (FR-20 の拡張)**

llove TUI で ConceptPage を読めるようにする (markdown viewer + graph viz)：

- ページ閲覧モード (`llove wiki view <slug>`)
- グラフ閲覧モード (concept ↔ concept のリンクを可視化、ATT&CK-style)
- 編集モード (HITL: LLM の提案を承認 / 修正 / 拒否、修正は candidate diff として記録)
- 矛盾レポートの highlight

### LLW-08: RAG との二層運用
**Phase: 2-4**

llive を **「Wiki 編集者」**、RAG (semantic memory query) を **「Wiki 検索者」** として二層運用する：

- 推論時の memory_read は **まず Wiki 層 (ConceptPage) を query**、必要に応じて Wiki から linked_entries (episodic / 生ソース) を辿る
- 単純 embedding nearest-neighbor 検索より、概念的にまとまった ConceptPage を返す方が context 効率が良い
- 「整理された Wiki を RAG で検索する」(LLM Wiki 解説で言及される理想形) の実装になる

---

## 4. 既存 v0.1〜v0.3 要件との整合性

| 既存 ID | 影響 | 対応 |
|---|---|---|
| MEM-01 (semantic) | 拡張 | ConceptPage を上位構造として追加、既存 entry は linked_entries として残る |
| MEM-05 (structural) | 拡張 | ConceptPage と linked_entries / linked_concepts のグラフ表現 |
| MEM-08 (consolidation) | **redefine** | "episodic → semantic への consolidation" を "episodic → ConceptPage コンパイル" に格上げ |
| FR-12 | **redefine** | "Hippocampal Consolidation Scheduler" を "Wiki Compiler (内部実装は biological-inspired)" に再定義 |
| FR-23 (Contradiction Detector) | 拡張 | metrics + Wiki content 両方を入力 |
| EVO-02 (ChangeOp) | 拡張 | Wiki diff (add_concept / merge / split) を ChangeOp に追加 |
| OBS-03 (llove HITL) | 拡張 | Wiki viewer / graph viz / 矛盾レポート閲覧モードを追加 |

---

## 4b. Anti-Circulation Safeguards (思考循環の防止)

LLM Wiki アーキテクチャの最大の落とし穴は **思考の循環 (thought circulation)** — LLM が
自ら書いた Wiki ページを後で読み、それを根拠に新しいページを書き、結果として元のソースを
忘れ、ハルシネーションが「合意」として固定化される現象。Phase 2 LLW-02 着手前に、
以下の **8 つの安全装置** を実装/設計仕様として明示する。

### LLW-AC-01: Source-anchored Provenance (Phase 2 必須)

ConceptPage の `provenance.derived_from` は **必ず raw episodic event_id を含む**。他の
ConceptPage を参照する場合は別フィールド `derived_from_concepts` に分離して記録、最終的な
"権威性" は raw events のみが持つ。`derived_from` が他 ConceptPage しか含まないページは
**invalid** として reject。

### LLW-AC-02: Drift Detection (Phase 3 計画)

定期的に各 ConceptPage の summary を、その `linked_entry_ids` の embedding 平均と比較し、
**cosine drift > θ** なら `needs_review` フラグ。HITL review なしに自動更新を続けない。

### LLW-AC-03: Evidence-anchored Prompts (Phase 2 必須)

Wiki Compiler の LLM prompt は **raw events と既存 ConceptPage summary を明示的に区別**し、
"raw events are authoritative; existing pages are working drafts" と明記。LLM が既存
ページに合わせて新しい事実を歪めることを抑制。

### LLW-AC-04: Diversity Preservation (Phase 2)

Consolidator は **低 overlap な cluster の merge を禁止**。`linked_entry_ids` の共通比率
< 0.3 なら merge action を新規ページ作成にダウングレード。少数派の証拠を消さない。

### LLW-AC-05: One-pass Guarantee (Phase 2 必須)

Wiki Compiler は **1 サイクル内で chain せず、新規作成された ConceptPage を同じサイクルで
再度コンソリしない**。「自分が今書いたものを次のクラスタの evidence にする」ループを禁止。
これは Consolidator のアーキテクチャ制約として実装。

### LLW-AC-06: Iteration Counter (Phase 3 計画)

各 ConceptPage に `auto_update_count` を持たせ、N (default 5) 回連続で LLM 更新された後は
**`needs_human_review` 状態に固定**、HITL レビューが通るまで自動更新を停止。

### LLW-AC-07: External Ground-Truth Anchors (Phase 2 推奨, Phase 4 必須)

`page_type = experiment_record / principle_application / failure_post_mortem` は
**immutable external citation を最低 1 件**持つことを Schema で要求 (CAD spec / 計測データ
hash / 論文 DOI / 形式検証結果)。LLM が改ざんできない anchor を全ページに張る。

### LLW-AC-08: Diversity-aware Replay Select (Phase 2)

Consolidator の Replay Select は surprise-weighted reservoir sample だけでなく、
**時間窓 × source_type の二次元層別サンプリング**を行う。直近の異常事象だけに over-fit
しない。

### LLW-AC-09: Edge Weight Semantics (Phase 2 必須)

`StructuralMemory` の MemoryEdge には `weight: DOUBLE` が既に存在するが、Phase 1 / Phase 2
着手時点では単に default 1.0 / 0.5 が入る placeholder。LLM Wiki が circular feedback を
起こさないために **rel_type 別に明確な weight semantics** を定義する：

| rel_type | weight 計算 | 範囲 | 更新タイミング |
|---|---|---|---|
| `linked_concept` | Jaccard(linked_entry_ids_src, linked_entry_ids_dst) | [0, 1] | Consolidator が edge 追加 / 既存 edge 更新時 |
| `derived_from` | 1.0 (binary, asymmetric) | {1.0} | 一度設定後 immutable |
| `contradicts` | 1.0 - cosine(summary_src, summary_dst) を 0.5 で clip | [0.5, 1.0] | Phase 3 LLW-04 で実装 |
| `generalizes` | 1.0 (binary, asymmetric) | {1.0} | 一度設定後 immutable |
| `temporal_after` | 1 / log(1 + Δt_hours) | (0, 1] | event 書込時 |
| `co_occurs_with` | min(count / 10, 1.0)、減衰 EMA | [0, 1] | consolidation cycle ごとに更新 |

**重み伝播のルール**：

- `query_neighbors` は `min_weight` パラメタで filter 可能、結果は `weight DESC` で sort
- Wiki Compiler が ConceptPage の "近隣" を LLM prompt に流す際は **`min_weight=0.2` を default** にして低信頼 edge を除外
- weight が時間で減衰する種別 (`co_occurs_with`) は cron で half-life ベース更新 (Phase 2 後半 or Phase 3)
- 同じ src-dst-rel_type ペアで edge 重複が出たら weight は max を採用 (`upsert` semantics)、count 集約は別 metadata

**循環防止との連動**：

- AC-04 の "merge 拒否" は **新規 evidence と既存 page の Jaccard < 0.3** で判定。LLW-AC-09 と一致した重み定義を持つことで「merge する/しない」の閾値と「edge 重み」が同じ尺度になり、運用が一貫する。

### Phase 2 で必須化する Anti-Circulation 機能 (まとめ)

- ✅ LLW-AC-01 (source-anchored provenance)
- ✅ LLW-AC-03 (evidence-anchored prompts)
- ✅ LLW-AC-04 (diversity preservation)
- ✅ LLW-AC-05 (one-pass guarantee)
- ✅ LLW-AC-08 (diversity-aware replay select)
- ✅ LLW-AC-09 (edge weight semantics, Jaccard for linked_concept)

LLW-AC-02 / 06 / 07 は Phase 3-4 に倒すが、**設計時点で hooks を残しておく**。

---

## 5. ロードマップ調整

v0.1〜v0.3 のロードマップは維持しつつ、Phase 2 で LLW-01〜03/06、Phase 3 で LLW-04/05、Phase 4 で LLW-07/08 を実装する。Phase 1 (MVR, 完了) には LLW は含めない。

| Phase | LLW 追加分 | 既存ロードマップ |
|---|---|---|
| Phase 1 (MVR, 完了) | — | 16 requirements |
| Phase 2 (Adaptive) | LLW-01 / LLW-02 / LLW-03 / LLW-06 | 9 requirements + 4 LLW |
| Phase 3 (Evolve) | LLW-04 / LLW-05 | 12 requirements + 2 LLW |
| Phase 4 (Production) | LLW-07 / LLW-08 | 9 requirements + 2 LLW |

総 v1.0 完了時の requirements: 46 → **54** (LLW 8 追加)。

---

## 6. ブランディング / 説明文の見直し

v0.4 取り込み後、READMEや family_integration.md の説明をこう書き直す候補：

> llive は **自己進化型 LLM Wiki 基盤** である。Karpathy の LLM Wiki パターンを参照実装としつつ、TRIZ 内蔵による発想力、形式検証 gate、産業 IoT メッシュ直結、TUI HITL を加えた **「生物学的記憶モデル × LLM Wiki × 形式検証 × 産業 IoT × TRIZ」5 軸交差点** に位置する。

これにより、既存類似研究 (MemGPT / LongMem / MERA) との差別化を Karpathy 公式パターンの拡張として説明できるようになる。

---

## 7. Out of Scope (v0.4 段階)

- **Wiki の自動公開 (HTML / GitHub Pages)** — 外向き公開は Phase 4 以降、まずは内部ツールとして運用
- **multi-user 共同編集** — llive は single-tenant で十分、multi-llive 連携は v1.0 後
- **Karpathy 互換 Markdown 形式** — ConceptPage の Markdown export は対応するが、ファイル構造は独自で良い (Karpathy 提案も実装非依存)

---

*Drafted: 2026-05-13*
*Implementation: deferred to Phase 2+ (本書は要件追加のみ、実装は順次)*
