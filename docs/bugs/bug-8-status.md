# LLIVE Bug 8 件 Status 表 (Week 1 Day 1)

> 2026-05-18 作成. memory [[project-llive-bug-2026-05-16]] の 8 件 (+ 1 件 D-DEBUG)
> について、`docs/BUGS_2026-05-16_brief_ab.md` の更新 + git log + memory
> [[project-llive-brief-api-done]] 確認の上で resolved/open 状態を確定.

## Summary

| 状態 | 件数 |
|---|---|
| ✓ Resolved (検証済) | 3 件 (LLIVE-001/002/006) |
| △ 部分対応 (継続改善) | 1 件 (LLIVE-004) |
| ✗ Open | 4 件 (LLIVE-003/005/007/008) |
| 🆕 追加実装済 | 1 件 (LLIVE-D-DEBUG) |

→ memory `project_llive_bug_2026_05_16.md` の「8 件未解消」想定からは大幅に進展.
**Critical 2 件 (001/002) は 5/16 で resolved**、Week 1 dogfooding は **High 残 3 件**
+ **Medium 残 2 件** に絞れる.

## 詳細表

| ID | Severity | 内容 | Status | 検証 | 次アクション |
|---|---|---|---|---|---|
| **LLIVE-001** | 🔴 critical | LLM backend が `FullSenseLoop` に未接続、`_inner_monologue` が template だけ | **✓ Resolved (2026-05-16)** | `LLIVE_LLM_BACKEND=ollama:llama3.2` で実 LLM thought 出力確認、9 tests pass、cloud backend は `LLIVE_ALLOW_CLOUD_BACKEND=1` 必須 (purity guard) | dogfooding で実利用、ollama / mock backend の安定性確認 |
| **LLIVE-002** | 🔴 critical | Brief API (CLI/MCP) 不在、`process(Stimulus)` のみ | **✓ Resolved (2026-05-16)** | memory `project_llive_brief_api_done.md` で end-to-end 完走確認、progressive matrix で overhead < 1% 実測 | Brief API を Week 1 dogfooding で実 use case に投入、UX gap 抽出 |
| **LLIVE-003** | 🟠 high | `thought.text` が `Observation about ...` 定型文 | **✗ Open (LLIVE-001 派生改善要)** | LLIVE-001 wire 後でも `_inner_monologue` の prompt 最適化が必要 | prompt template の改善、Brief 本文を 140 chars 以上活用、Week 2 で着手 |
| **LLIVE-004** | 🟠 high | TRIZ 検出が natural-language Brief で空配列 | **△ 部分対応 (2026-05-17)** | 5/17 commit `feat(grounding): TRIZ trigger に word-boundary + 否定文脈を導入` (e6de261)、ただし morphological matching / 分類器までは未到達 | morphological matcher 強化、または LLM 経由 TRIZ 検出に Week 2-3 で着手 |
| **LLIVE-005** | 🟠 high | `ego_score / altruism_score` が 0.1 固定、Brief 内容を解析していない | **✗ Open** | git log で `EgoAltruismScorer` 関連 commit 見えない | Week 2: `EgoAltruismScorer.score()` 実装確認、Brief 内容を反映、または基準値として明示 |
| **LLIVE-006** | 🟡 medium | `run_brief.py` が Windows cp932 stdout で crash | **✓ Resolved (2026-05-16)** | `sys.stdout.reconfigure(encoding="utf-8")` 追加 | 同種の Windows 互換性問題が他にないか、CONTRIBUTING に記載 |
| **LLIVE-007** | 🟡 medium | salience 落ち cycle の `stages.thought` 欠落、A/B diff しづらい | **✗ Open (documented design)** | SILENT path の design として認知済、ただし dict 構造が sparse | Week 2: `stages.thought = None` placeholder で diff tool に対応 |
| **LLIVE-008** | 🟡 medium | Approval Bus + SQLite Ledger が `FullSenseLoop._finalise` に配線されていない | **✗ Open (戦略的重要)** | C-1 自体は完了 ([[project-llive-9axis-skeleton]])、`process()` から呼ばれていない状態 | **Week 1-2 最優先**: `_finalise` に Ledger record + Approval Bus gate、SIL 差別化軸の核 |
| **LLIVE-D-DEBUG** | (新規) | DebugMode 追加要望 | **🆕 Implemented (2026-05-16)** | `FullSenseLoop(debug=True)` で backend name / prompt / raw response / wall time / template inputs 等を `stages["thought"].debug` に attach、release では zero overhead | dogfooding で実 debug 体験、改善点抽出 |

## Severity 別 Week 計画 (修正版)

### Week 1 (dogfooding 主目的、bug 修正は incidental)
- **LLIVE-008 (Approval Bus 配線)** を **dogfooding を回しながら最優先で配線**
  → SIL 差別化軸の核、これが動かないと llive の存在意義の半分が空中分解
- 残 LLIVE-001/002/006 の dogfooding 検証 (実 use case で問題が出ないか)
- LLIVE-D-DEBUG を使って observe_grounding に統合し、Brief 経過を見える化

### Week 2 (bug 修正集中)
- **LLIVE-003** (thought prompt 改善) — LLIVE-001 wire 済を前提に prompt 強化
- **LLIVE-004** (TRIZ morphological / LLM 統合) — 部分対応を完全化
- **LLIVE-005** (ego/altruism scorer 解析) — score logic を Brief 内容に反応させる

### Week 3 (品質改善)
- **LLIVE-007** (SILENT path stage placeholder) — A/B diff tooling 整備
- 残 incidental items

## 重要 insight (status 表作成で得た)

1. **memory `project_llive_bug_2026_05_16.md` は 5/16 時点の snapshot で、その後の
   進展 (5/16-5/17 の commit + 5/17 memory `project_llive_brief_api_done.md`) を
   反映していなかった**. Day 0 で status 化することで Critical 2 件が既に resolved
   と判明、Week 1 計画の重さが約半分に
2. **LLIVE-008 (Approval Bus 配線) が戦略上の急所**. [[feedback-competitor-benchmark]]
   差別化 4 軸の「HITL」が現状 Brief 経路で未配線 = 差別化が機能していない. これを
   Week 1 dogfooding 中に配線する優先度は上がる
3. **LLIVE-001/002 resolved により Brief 経路の core path が動く** → Week 1
   dogfooding は「動く前提」で実 use case 投入できる. これは [[project-llove-day0-gap]]
   と整合 — llove 観測 pane に llive Brief 出力を流す実機運用が可能になる
4. **memory drift 監視の必要性**. 1 日 (5/16→5/17) で memory と現実が乖離した. 週次
   drift 監視 ([[project-fullsense-ear-origin]] 関連 cross-cutting issue) を回さないと
   戦略判断が古い情報に基づくリスク

## 関連 memory / docs

- [[project-llive-bug-2026-05-16]] — 原 memory (本 status で update 推奨)
- [[project-llive-brief-api-done]] — LLIVE-001/002 resolved 確認元
- [[project-llive-9axis-skeleton]] — C-1 Approval Bus 完了状態
- [[feedback-competitor-benchmark]] — 差別化 4 軸 (HITL = LLIVE-008 配線必須)
- [[feedback-implementation-status-record]] — 4 段階 status taxonomy (本表で適用)
- `D:/projects/llive/docs/BUGS_2026-05-16_brief_ab.md` — 詳細記述 (一次資料)
- [[project-30day-action-plan-2026-05]] — Week 1-4 全体タイムライン

## 改訂履歴

- 2026-05-18 — v1 作成 (Week 1 Day 1 タスク、約 30 分)
