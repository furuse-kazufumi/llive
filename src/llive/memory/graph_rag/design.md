# GraphRAG layer — design notes

## Goal

llive の 4 層メモリ (sensory / short_term / working / long_term) のうち、**long_term 層と外部 knowledge graph を結ぶ retrieval bridge** を提供する。
従来の semantic memory (`llive.memory.semantic.SemanticMemory` — faiss / numpy fallback の IP cosine ベクトル検索) は単一の embedding 類似度に閉じており、

- 「概念 A → 概念 B → 概念 C」のような **多段関係 (multi-hop)** を辿る retrieval、
- 「同じ embedding でも relation が違う」ような **型付き edge** に基づく絞り込み、
- 「retrieval 結果に provenance graph を添える」コンテキスト構築

を扱えない。GraphRAG layer はこのギャップを埋め、`SemanticMemory` と並走する **secondary index** として機能する。

## Non-goals (skeleton 段階)

- 完全な neo4j 統合 / Cypher query 対応。
- 自動 entity extraction / coreference resolution (LLM consolidation cycle 側の責務)。
- 永続化レイヤ (現状 `to_dict` / `from_dict` のみ。kùzu / sqlite backend は将来 swap)。
- distributed 化 / sharding (single-process in-memory が対象)。

## 4 層メモリとの境界

| 層 | 既存実装 | GraphRAG との関係 |
| --- | --- | --- |
| sensory | (encoder / ingestion 段、専用 layer file は無し) | GraphRAG に **書かない**。雑音が多すぎる |
| short_term | working buffer (consolidation 直前) | GraphRAG に **書かない**。寿命が短すぎる |
| working | 推論中の active set | retrieval 時に GraphRAG を **読む側**。書き込みなし |
| long_term — semantic | `src/llive/memory/semantic.py` (`SemanticMemory`) | GraphRAG は **副 index**。`entry_id` を Node.payload に保持して相互参照 |
| long_term — episodic | `src/llive/memory/episodic.py` (`EpisodicMemory`, DuckDB) | event Node の payload に `event_id` を保持 |
| long_term — structural | `src/llive/memory/structural.py` (`StructuralMemory`, kùzu) | **重複に注意**: structural は厳格 schema (固定 6 種類 rel_type)、GraphRAG は free-form relation。役割分担は「structural = 内部 provenance graph / GraphRAG = 外部 KG 連動 retrieval」 |
| long_term — concept | `src/llive/memory/concept.py` (`ConceptPage`) | concept Node として double-bookkeeping。`concept_id` を Node.id に流用可能 |
| long_term — tier | `src/llive/memory/tier.py` (`TierCache` — hot/warm/cold/frozen) | 直交。GraphRAG store 全体が WARM tier に乗ることを想定 |

**移行ルール (consolidation 後の long_term 投入時):**

1. `EpisodicEvent` を `SemanticMemory` に write、`entry_id` を取得。
2. consolidator が cluster → ConceptPage を作る (LLW-02 既存 pipeline)。
3. 同タイミングで **GraphRAG に Node を 1 つ** 追加 (`kind="concept"`)、`payload["entry_ids"]` に semantic の entry_id を、`payload["concept_id"]` に ConceptPage.concept_id を保持。
4. cluster 間の co-occurrence が閾値超なら `Edge(relation="co_occurs_with")` を張る。
5. 外部 KG (DBpedia / Wikidata / 自前) からの import は `kind="entity"` Node + `relation="mentioned_in"` Edge で繋ぐ。

## Hybrid score 計算式

retrieval スコアは以下の凸結合:

```
score(node) = (1 - alpha) * cosine(query_embedding, node.embedding)
            + alpha * graph_proximity(node)
```

- `alpha`: graph 寄与のミックス比 (default `0.4`、`__init__` で調整可)。
- `cosine`: 標準的な L2 正規化済み内積。embedding が `None` の node は `0.0` とする。
- `graph_proximity(node)`: 各 seed (= cosine 上位の node) から hop 距離 `d` で減衰した寄与の合計:

```
graph_proximity(node) = sum_over_seeds( seed_weight * hop_decay^d * edge_weight_product )
```

- `hop_decay`: default `0.5`。1 hop で 0.5、2 hop で 0.25、…。
- `edge_weight_product`: 経路上の edge.weight を BFS 訪問時に乗じる (skeleton では 1 hop 分だけ反映 — 多経路は加算、経路上の積分は将来)。
- `max_hops`: 呼び出し時引数 (default `2`)。`0` を渡すと proximity 項は **seed 自身のみ** になり、純粋な embedding 検索に縮退。

α と hop_decay は store 単位、max_hops と k は query 単位で指定する。

## Swap candidate trade-off

| 候補 | 強み | 弱み | adopt 判断 |
| --- | --- | --- | --- |
| **dict adjacency (現状)** | 依存 numpy のみ、PyPI wheel ゼロ、test 起動 < 100 ms | shortest path / centrality 等のアルゴリズム自前実装 | 10^5 node まで。それ以下なら据え置き |
| **networkx** | アルゴリズム豊富 (Dijkstra / PageRank / community detection)、pure-python で wheel 軽量 | 単一プロセス・永続化なし、10^6+ node で性能劣化 | アルゴリズム需要が出たら最初の swap |
| **kùzu** (既に structural.py で採用) | embedded graph DB、Cypher、on-disk 永続化、structural との一体化 | schema 強制、free-form relation との相性悪、Windows wheel 制約 | structural と統合する判断が立ったら |
| **neo4j** | スケール、production graph DB、Cypher、可視化 | 別プロセス・別ポート、license (Community 4 GB 制限)、依存重 | 数百万 node 規模 or マルチプロセス共有が必要になったら |

**現時点の選択**: dict adjacency。理由は (a) skeleton 段階で外部依存を増やさない、(b) llive の test 起動コスト基準 (LLIVE_DISABLE_RAD_GROUNDING 等で意図的に軽量化) を維持、(c) `from_dict` / `to_dict` で他 backend への migration path は確保済。

## 参照した既存 long_term layer file

- `src/llive/memory/semantic.py` — SemanticMemory (faiss/numpy IP index)
- `src/llive/memory/episodic.py` — EpisodicMemory (DuckDB)
- `src/llive/memory/structural.py` — StructuralMemory (kùzu)
- `src/llive/memory/concept.py` — ConceptPage / ConceptPageRepo
- `src/llive/memory/consolidation.py` — Wiki Compile pass (LLW-02)
- `src/llive/memory/tier.py` — DTKR Tier (hot/warm/cold/frozen)
- `src/llive/memory/encoder.py` — MemoryEncoder (将来 query_embedding 供給元)

## TODO (next phase)

- [ ] `MemoryEncoder` を `GraphRAGStore.query` に optional inject し text→embedding を内部で実行
- [ ] consolidation hook で ConceptPage 作成と同時に Node + co_occurs_with Edge 投入
- [ ] networkx backend swap (アルゴリズム需要が出たタイミング)
- [ ] structural との重複監査 — 同じ Node を双方に持つ場合の SSoT 決定
- [ ] hop > 2 の積分 (経路上の edge_weight 乗算) と Dijkstra 風の最短距離 proximity
