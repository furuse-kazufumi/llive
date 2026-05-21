# PR 分割計画 — `optimize/core-2026-05-20` → `main`

**Drafted:** 2026-05-21
**Status:** 草案 (agent 自律ドラフト). マージ判断は user.
**Trigger:** Stop hook feedback「PR ドラフト分割未了」を受けて作成.

## 0. 現状

- branch: `optimize/core-2026-05-20`
- main から **127 commits ahead** (auto-hook の編集前 snapshot 込)
- 実質 feat commit は ~25 件 (auto 除く)
- llive 全件: 1881 PASS (回帰なし)
- 累計 +208 test (1673 → 1881)

## 1. 推奨: 5 PR 分割

各 PR は独立 reviewable + revertable.

### PR #1 — B-series 収束型最適化 + v0.A 外部ランタイム追従

**Scope:**
- `src/llive/perf/synaptic_selector.py` + `UCBSynapticSelector`
- B-9-a/b 実 production 注入 (assume_normalized / GiftValue deque)
- v0.A 要件 + matrix SSoT + smoke skeleton + runtime_metadata helper

**Risk:** 低 (kwarg default False, 既存 hot path への影響なし)
**Test 増分:** +52
**Reviewers の focus:** UCB1 数式 / Hebbian update / runtime metadata SHA 整合

### PR #2 — v0.B/v0.C 進化型最適化レイヤ

**Scope:**
- `src/llive/perf/evolutionary/` の v0.B 基盤 (Genome / Individual /
  Population / EvolutionLoop / Selection / Crossover / Mutation /
  Scheduler / seeds / fitness / fitness_ucb / fitness_llm)
- v0.C llive_variant (19 dim genome + 5 chromosome SegmentCrossover)
- v0.C variant_runner (subprocess CLI mock)
- v0.C lineage (winners.jsonl + Mermaid)
- v0.C bridges/llive (lleval bridge skeleton)
- v0.C Phase 2 `VariantSubprocessScheduler` (subprocess transport)
- `scripts/demo_evolutionary_loop.py` + `demo_self_adaptive_variant.py`

**Risk:** 低 (新規 package, 既存 import 影響なし)
**Test 増分:** +50 程度
**Reviewers の focus:** GA loop の数式 + checkpoint/resume + subprocess fault isolation

### PR #3 — v0.D Self-referential + LLM operators (要件 + 着地分)

**Scope:**
- `docs/requirements_v0.D_self_referential_and_llm_operators.md`
- `src/llive/perf/evolutionary/self_adaptive.py`
  (`SelfAdaptiveGaussianMutation` Schwefel σSA-ES, log-normal σ update)
- `src/llive/perf/evolutionary/meta_mutation.py`
  (`MetaMutation` strategy_id 埋込, 集団内 4 戦略並走)
- `src/llive/perf/evolutionary/llive_variant_extras.py`
  (LV 19 dim → 38/20/39 dim high-level API)

**Risk:** 低 (PR #2 の package に追加, 既存壊さない)
**Test 増分:** +38 (SR-01 14 / SR-02 10 / LV-extras 14)
**Reviewers の focus:** Schwefel 学習率 τ' τ / log-normal stability / genome layout

### PR #4 — v0.E 競争的協調進化 (大規模)

**Scope:**
- `docs/requirements_v0.E_competitive_coevolution.md` (34 IDs)
- `src/llive/perf/evolutionary/peer_evaluation.py` (CE-01)
- `src/llive/perf/evolutionary/diversity.py` (E.14-18)
- `src/llive/perf/evolutionary/persona.py` (E.10/11)
- `src/llive/perf/evolutionary/mating.py` (E.19/20)
- `src/llive/perf/evolutionary/speciation.py` (E.21)
- `src/llive/perf/evolutionary/nsga2.py` (E.31)
- `src/llive/perf/evolutionary/island_model.py` (E.33)
- `src/llive/perf/evolutionary/expert_council.py` (E.7/8)
- `src/llive/perf/evolutionary/expert_evolution.py` (E.9)
- `fullsense/docs/research/llm_evolutionary_prior_art.md` (別 repo, 並走)

**Risk:** 中 (大規模 PR だが新規 module 群なので既存破壊なし)
**Test 増分:** +120 (CE-01 14 + diversity 15 + persona 27 + mating 13 +
speciation 12 + NSGA-II 13 + IslandModel 17 + ExpertCouncil 20 +
ExpertEvolution 22 — 一部 overlap)
**Reviewers の focus:**
- peer evaluation matrix の共謀検出 3 指標
- NSGA-II Pareto front + crowding distance の正当性
- Persona ontology の factor_affinity 妥当性 (heuristic, 後で corpus 化)
- ExpertCouncil 4 protocol の決定論性

**Split sub-option:** PR #4a (CE-01 + diversity + persona + mating) と
PR #4b (speciation + NSGA-II + IslandModel + ExpertCouncil + ExpertEvolution)
に分けるのも可. PR #4 全体だと review 重い場合に検討.

### PR #5 — Release-ready + Rust spec

**Scope:**
- `docs/requirements_v0.7_rust_acceleration_v0DE_addendum.md` (RUST-15〜20)
- `src/llive/__init__.py` version 0.2.0.dev0 → 0.6.0a1
- `CHANGELOG.md` [0.6.0a1] section
- ruff cleanup 95/126 fix
- `docs/pr_drafts/PR_split_plan_2026_05_21.md` (本ファイル)
- (将来) Rust skeleton `rust_ext/` (cargo init + pyo3 binding)

**Risk:** 低 (cosmetic + spec)
**Test 増分:** 0 (test 維持)
**Reviewers の focus:** version 整合 / CHANGELOG 正確性

## 2. PR 順序

```
main ──→ PR #1 ──→ PR #2 ──→ PR #3 ──→ PR #4 ──→ PR #5
        (B+v0.A)  (v0.B/C)  (v0.D)    (v0.E)    (Release+Rust spec)
```

各 PR は前 PR の merge を前提に rebase.

## 3. 代替案: 単一 PR

レビュー側のコストが許容できるなら 1 PR で merge する案も可能.

- 利点: review 1 回, commit history が直線
- 欠点: 127 commits 同時 review, revert 単位が大きい

memory `feedback_max_plan_autonomy` 「Max 契約で自律進める」と整合的なのは
**自律で 5 PR draft を作る + マージは user 判断** という本計画.

## 4. 各 PR の CHANGELOG section

`CHANGELOG.md` の `[0.6.0a1]` (本 branch ですでに追加済) を 5 セクションに
**さらに分割** したい場合のドラフト案:

```markdown
## [0.6.0a1] — 2026-05-21

### Added — B-series + v0.A (PR #1)
...

### Added — v0.B/v0.C Evolutionary core (PR #2)
...

### Added — v0.D Self-referential mutation (PR #3)
...

### Added — v0.E Competitive coevolution (PR #4)
...

### Changed / Chore — Release readiness (PR #5)
...
```

## 5. Push 計画 (user 承認後)

1. PR #1 用 sub-branch を切る: `git checkout -b release/pr1-b-series-v0a optimize/core-2026-05-20`
2. PR #1 用 commit のみ残して rebase
3. `git push origin release/pr1-b-series-v0a`
4. GitHub UI で PR 作成 + 本 file の PR #1 section を description にコピー
5. 同手順で PR #2 〜 #5

**自動化候補**: `scripts/split_branch_to_prs.sh` (将来) で PR 分割を半自動化.

## 6. References

- 関連 maintainer memory:
  - `goal_release_ready_v0E_rust` (本 Goal)
  - `feedback_publishing_workflow` (公開フロー)
  - `feedback_competitor_benchmark` (差別化 4 軸)

- 関連 docs:
  - `docs/CHANGELOG.md` (v0.6.0a1)
  - `docs/requirements_v0.D_self_referential_and_llm_operators.md`
  - `docs/requirements_v0.E_competitive_coevolution.md`
  - `docs/requirements_v0.7_rust_acceleration_v0DE_addendum.md`
