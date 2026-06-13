# 2026-05-21 夜 marathon 進捗統合 — llive v0.E quality-diversity + governance + persona import + release wiring

> Author note: feedback_daily_progress_article / feedback_articles_as_agent_context
> に従い、本セッション (15h marathon goal 内) で着地した実装と docs を 1 本に
> 統合する。次セッション開始時の context 補完源として使う。

## 1. 着地サマリ

| 項目 | 件数 | 場所 |
|---|---|---|
| 新規 module | 5 (quality_diversity / coevolution_governance / persona_import / persona_survival / persona_corpus_loader) | `src/llive/perf/evolutionary/` |
| 新規 test ファイル | 5 件 | `tests/unit/test_evolutionary_*.py` |
| 追加 test ケース | **130** ケース (41 + 28 + 26 + 16 + 19) すべて PASS | — |
| ruff 警告 | **0** (`src/llive/perf/evolutionary/` 範囲) | — |
| CHANGELOG 追記 | E.17 / E.4 / E.12 / [Unreleased] 整理 | `CHANGELOG.md` |
| 新規 docs | rust hotspot addendum / v0.6.0a1 PR plan | `docs/rust_hotspot_v0E_addendum.md` / `docs/release/v0.6.0a1_PR_PLAN.md` |
| atomic commit 件数 | 7 件 (semantic) + auto commit 群 | branch `optimize/core-2026-05-20` |

## 2. 着地した v0.E module

### 2.1 E.17 — Quality Diversity (CE-25 + CE-26)

**`PersonaOverlapPenalty`**: `fitness' = fitness + λ × mean_dissimilarity(self, others)`.
λ=0 で挙動は base. λ↑ で集団内 persona overlap を罰す. integration test で
λ=10 のときに rare な persona が逆転して trump fitness 最大化を確認.

**`MAPElitesGrid`** (Mouret & Clune 2015 を 4 軸化): persona 2 軸 ×
thought_factor 2 軸 = 4 次元 archive. `submit(individual, fitness, features)`,
`coverage`, `best`, `best_per_persona_slice`, `fitness_grid` を公開.
default feature extractor は PersonaComposition.effective_factor_affinity
の mean/std + factor_structurize/factor_exploration.

### 2.2 E.12 — Persona Import (CE-20)

派生間 persona 部分採用. cosine 類似度ベースの affinity_threshold で
incompatible persona を拒否し, 上限 max_imports_per_event で cap.
3 blend strategy:

- `extend`: persona_ids に append + weights renormalize.
- `replace`: 末尾 N 件を入れ替え (dedup).
- `blend_weights`: 同名 persona は target/source weight 平均, 新規は append.

決定論性: `rng` 注入で同入力 → 同出力. plan は frozen dataclass.

`PersonaZoneShareEvent` は COG-MESH-05 Quarantined Memory zone への通知
envelope. 本 module は event を返すだけで実 zone 操作は別 module.

### 2.3 E.4 — Governance skeleton (CE-06 + CE-07 + CE-08)

`CollusionDetector` → `CoevolutionGovernance` → ApprovalBus / TonicRiskMonitor
の wiring. 共謀疑い (variance / symmetry / concentration の 3 指標) のとき:

- `ApprovalBus.request("coevolution.suspected_collusion", payload)` で
  人手介入要請を発火.
- `TonicRiskMonitor.tick(state)` で世代単位 risk score を投入し
  cooldown / interrupt_threshold 超過で `RiskAlert` 発火.

`collusion_risk_score` は module-level で再利用可能. variance 0 → risk 1,
symmetry 高 → risk 高, concentration 低 → risk 高, is_suspected フラグで
+0.1 bonus. 空 state はリスク評価不能として 0.

### 2.4 CE-22 — PersonaSurvivalAnalysis

派生集団内の persona 組合せ生存統計. `SurvivalRateTracker` を decorator
として持ち, PersonaComposition から canonical signature (sorted persona_ids
の `|` 連結) を作って observe. 新 query API: `hybrid_distribution()`,
`persona_appearance_count()`, `hybrid_ratio()`, `survival_by_size()`.
H8 仮説 (hybrid persona の優位性) を hybrid_ratio + survival_by_size で
定量観察可能.

### 2.5 CE-23 — PersonaCorpusLoader skeleton

外部 LLM / 実 RAD path 横断は次フェーズ. 本セッションでは offline 動作する
keyword fallback で skeleton 着地:

- `ThoughtPatternExtractor` Protocol (LLM 注入点).
- `keyword_extractor` (10 思考因子 × 代表キーワード mapping, 日英 mixed).
- `affinity_from_counts` (log1p → max-normalize).
- `PersonaCandidate.to_persona()` で既存 `Persona` に変換.
- `PersonaCorpusLoader.merge_into_ontology` で PERSONA_ONTOLOGY コピーに
  追加 (副作用なし).
- `find_persona_snippets_in_text_file` (utf-8 → cp932 fallback).

## 3. Release wiring

### 3.1 CHANGELOG.md

[0.6.0a1] セクションに E.17 / E.4 / E.12 の 3 サブセクションを追加.
中段にあった [Unreleased] (2026-05-16 Brief API) を [0.6.0a0] にリネームし
冒頭に新たな [Unreleased] (v0.7 Rust 高速化 / E.5 League / E.6 Debate /
lleval bridge を planned として) を新設.

### 3.2 README.md

ステータス先頭に `[Unreleased] v0.6.0a1` 行を追加. 本日着地内容 + PR plan
へのリンクを明示.

### 3.3 docs/release/v0.6.0a1_PR_PLAN.md (新規)

`optimize/core-2026-05-20` branch を 5 PR に論理分割する plan を明文化.
依存順序 (PR1 → 5), rollback ストラテジ, ruff gate を明記. push 解禁後の
リリース手順 (test pypi で alpha 配布 → v0.6.0 stable で本配布) も併記.

### 3.4 docs/rust_hotspot_v0E_addendum.md (新規)

memory `goal_release_ready_v0E_rust` に対応する Rust 高速化候補 5 件
(RUST-15 persona_dissimilarity / RUST-16 collusion_score / RUST-17
NoveltyScorer / RUST-NEW-B MAPElites bin / RUST-18 parity test) を
hot-path 視点で棚卸し. 実装は v0.7 次セッション.

## 4. 数字で見る (本日のみ)

| 指標 | Before | After | Δ |
|---|---|---|---|
| evolutionary module 数 | 24 | 29 (+5) | +5 |
| evolutionary test (本日追加分のみ) | — | 130 PASS | +130 |
| ruff `src/llive/perf/evolutionary` 警告 | 7 | **0** | -7 |
| CHANGELOG `[0.6.0a1]` セクション | 既存 | + E.17 / E.4 / E.12 = +41 行 | +41 |
| docs (release + rust addendum) | 0 | 2 ファイル + 271 行 | +271 |

## 5. 次セッションへの引き継ぎ

### 5.1 確実に着手すべきもの

1. **Rust 高速化 RUST-15** (persona_dissimilarity Rust 化) —
   `docs/rust_hotspot_v0E_addendum.md` の RUST-15 spec を実装. 5x gate
   通過必須. parity test を hypothesis に追加.
2. **lleval bridge v0.1.0a2** — `D:/projects/lleval/bridges/llive.py`
   の skeleton を実 promptfoo subprocess 経路と llive Genome →
   ProviderSpec mapping に拡張.
3. **CE-22 / CE-23 を実 EvolutionLoop に配線** — `PersonaSurvivalAnalysis`
   を `EvolutionLoop.on_generation_end` に hook. `PersonaCorpusLoader`
   は raptor RAD pathなめ + LLM 抽出を追加.

### 5.2 検討事項 (どちらに進むか判断点)

- v0.E E.5 (League mode) — credential 復旧後. Anthropic / OpenAI
  judge LLM が必要.
- v0.E E.6 (Debate mode) — credential + judge LLM 必須.
- v0.7 Rust acceleration を先行か, E.5 / E.6 と並列か.

### 5.3 注意

- branch `optimize/core-2026-05-20` は **未 push**. constraints
  `no-push` は claude-loop queue task の制約として受領済み.
- 5 PR plan は draft のみ. 実 PR 送信は user 確認後.
- pyproject.toml version は `0.6.0` のまま (CHANGELOG では `[0.6.0a1]`).
  リリース時に version bump.

---

> 関連: [[project_llive_v0E_coevolution]] / [[goal_release_ready_v0E_rust]] /
> [[feedback_max_plan_autonomy]] / [[feedback_session_marathon]].
