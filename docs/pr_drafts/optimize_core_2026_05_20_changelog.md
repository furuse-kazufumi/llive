# PR Draft — `optimize/core-2026-05-20` → `main`

**Branch:** `optimize/core-2026-05-20`
**Target:** `main`
**Status:** 草案 (2026-05-21, agent ドラフト). マージ判断は user.

## Summary

3 つの epic を 1 branch で進めたため, PR としては **3 つに分ける案** と
**1 つにまとめる案** がある.

### 案 A: 3 PR に分ける (推奨)

| PR | 内容 | リスク |
|---|---|---|
| **PR #1: B-0〜B-9 収束型最適化** | SynapticSelector + UCB1 + 実 production 注入 (B-9-a/b) | 低 (test 緑, 既存 hot path への影響は kwarg default False) |
| **PR #2: v0.A 外部ランタイム追従** | 要件 + matrix SSoT + smoke skeleton + runtime_metadata helper | 低 (新規 module + 既存 0 件 touch) |
| **PR #3: v0.B 進化型最適化レイヤ** | Phase 1-4 mock skeleton + 5 backend Genome PoC | 低 (新規 package, 既存 import 影響なし) |

各 PR は独立 reviewable で, 1 つ revert しても他に影響しない. **推奨**.

### 案 B: 1 PR にまとめる

| 利点 | 欠点 |
|---|---|
| review 1 度で済む | diff 大 (+40 commits, 40+ files) |
| commit history を直線で残せる | revert 単位が大きい |

review コストが許容できるなら案 B でも可.

## 全体 diff stats (2026-05-21 時点)

| 項目 | 値 |
|---|---|
| commit 数 (auto: 除く) | ~12 |
| 新規 module | `perf/synaptic_selector.py` (B-0) + `perf/evolutionary/` (10 module) + `benchmark/runtime_metadata.py` + `llm/factor_hook.py` (既存) |
| 新規 test 数 | +52 (UCB + evolutionary 26 + scheduler 4 + seeds 8 + fitness_llm 7 + backend_select 2 + runtime_metadata 6 + smoke contract 5 (skip) - 既存重複) |
| llive 全 test | 1518 → **1634 PASS** (+116, 回帰なし) |
| 新規 doc | `docs/requirements_v0.A_external_runtime_tracking.md` + `docs/requirements_v0.B_evolutionary_optimization.md` + `docs/spec/llamacpp_compat_matrix.md` + `docs/experiments/optimize_core_2026_05_20.md` + `docs/experiments/evolutionary_v0_B_2026_05_21.md` + `docs/experiments/low_spec_mock_2026_05_21.md` |
| 新規 demo script | `demo_synaptic_selector.py` / `demo_synaptic_cosine.py` / `demo_synaptic_decay*.py` / `demo_synaptic_sliding_window.py` / `demo_evolutionary_loop.py` / `demo_low_spec_mock.py` |

## CHANGELOG (推奨, CHANGELOG.md に append)

```markdown
## [Unreleased] — 2026-05-20 / 21

### Added (B-0〜B-9 収束型最適化)

- `llive.perf.synaptic_selector` — Hebbian-style ε-greedy + bounded modification
- `llive.perf.UCBSynapticSelector` — UCB1 で早期収束 bias を解消
- B-9-a: `SurpriseGate` / `BayesianSurpriseGate.compute_surprise` に
  `assume_normalized` kwarg (公開 API 後方互換)
- B-9-b: `GiftValueEstimator._history` を `deque` 化 + cooldown evict

### Added (v0.A 外部 LLM ランタイム追従)

- `docs/requirements_v0.A_external_runtime_tracking.md` — 月次追従ルール
- `docs/spec/llamacpp_compat_matrix.md` — 3 段階 pin SSoT
- `tests/contract/test_llamacpp_smoke.py` — `OPENAI_BASE_URL` 未設定時 skip
- `llive.benchmark.runtime_metadata` — 6 metadata helper + publish gate

### Added (v0.B 進化型最適化レイヤ)

- `llive.perf.evolutionary.{Genome,Individual,Population}` (Phase 1)
- `llive.perf.evolutionary.{Tournament,Roulette,Elitism}Selection` (EV-03)
- `llive.perf.evolutionary.{Uniform,Blend}Crossover` (EV-04)
- `llive.perf.evolutionary.{Gaussian,Reset,Chained}Mutation` (EV-05)
- `llive.perf.evolutionary.{sphere,rosenbrock}_fitness` (EV-02)
- `llive.perf.evolutionary.EvolutionLoop` (EV-06)
- `llive.perf.evolutionary.{Multiprocessing,Asyncio}Scheduler` (EV-07)
- `llive.perf.evolutionary.fitness_ucb` (EV-09)
- `llive.perf.evolutionary.fitness_llm` (Phase 4 mock) + 5 軸 fitness
- `llive.perf.evolutionary.seeds` (Phase 3.5 per-individual sub-seed 派生)

### Changed

- `llive.memory.surprise.SurpriseGate.compute_surprise` に `assume_normalized`
  kwarg 追加 (default False, 後方互換)
- `llive.cognitive_mesh.gift_value.GiftValueEstimator._history` を
  `list` → `deque` 化 (内部実装変更, 公開 API 影響なし)

### Test

- 1518 → **1634 PASS** (+116, 回帰なし)
```

## Review 観点 checklist

- [ ] B-9-a の `assume_normalized=True` が安全に意味的等価か (SemanticMemory が
      L2 normalized を返すことを再確認)
- [ ] `runtime_metadata` の publish gate が誤って既存 bench を block しないか
      (default `"unknown"`, 既存 bench は invalid 扱いに変わるが migration が
      必要なら別 PR)
- [ ] v0.B の `MultiprocessingScheduler` が Windows + Python 3.11 で安定動作
      (test_evolutionary_scheduler.py で timeout 30s/60s で確認済)
- [ ] `fitness_llm.py` の 5 軸 mock が **公開ベンチに誤って使われない** よう,
      MockBackend 数値の honest disclosure 警告が `low_spec_mock_2026_05_21.md`
      で十分か
- [ ] non-transformer 5 backend skeleton (5/18 投入済) と v0.B `backend_select`
      Genome の責務分担が clear か

## マージ後の前倒し残作業

| 件 | 着手判断 |
|---|---|
| llama-server + Codestral-Mamba GGUF 実走 | operator (15h marathon 範囲外) |
| RWKV.cpp + RWKV-7 World 7B 実走 | operator |
| lleval v0.1.0a1 (promptfoo subprocess) | user 承認後 (`furuse-kazufumi/lleval` repo init) |
| Phase 4 実 LLM fitness (`fitness_llm` の MockBackend 数値を実 backend で上書き) | credential 復旧後 |
| claude-smart 評価 Session 1 | user が `.worktrees/eval-claude-smart` で Claude Code 起動 |

## 関連

- `docs/requirements_v0.A_external_runtime_tracking.md`
- `docs/requirements_v0.B_evolutionary_optimization.md`
- `docs/experiments/optimize_core_2026_05_20.md`
- `docs/experiments/evolutionary_v0_B_2026_05_21.md`
- `docs/experiments/low_spec_mock_2026_05_21.md`
- portal `docs/spec/lleval_v0_1_implementation_notes.md`
- portal `docs/PROGRESS.md` Phase 0.6 + 0.7 + 0.8
