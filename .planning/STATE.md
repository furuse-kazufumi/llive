# STATE: llive

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-13)

**Core value:** コア重みを再学習せず、新しい能力を安全に追加し続けられる LLM 基盤
**Current focus:** Phase 1 (Minimal Viable Research Platform) 進行中 — 自律実装セッション

## Current Status

- **Phase 0 (Scaffolding / Spec drafting)**: ✅ 完了 (2026-05-13)
  - 要件定義 v0.1〜v0.3 累積完成
  - 設計文書 14 ファイル
  - 公開 LLM ひな形 4 種 (Qwen2.5-7B / Llama-3.1-8B / Mistral-7B-v0.3 / Phi-3.5-mini)
  - 標準 SubBlockSpec 4 ファイル (common / attention / ffn / llive_extensions)
  - TRIZ リソース 3 ファイル (40 原理 / 39×39 マトリクス / 39+11 特性)
  - GSD ワークフロー初期化完了 (.planning/)

- **Phase 1 (MVR)**: ✅ 完了 (2026-05-13)
  - 16/16 requirements validated, 49 tests pass, 82% coverage
  - PyPI 公開済: https://pypi.org/project/llmesh-llive/0.1.1/ (tag v0.1.1)
  - 詳細: `.planning/phases/01-mvr/01-VERIFICATION.md`
- **Phase 2 (Adaptive)**: ✅ 完了 (2026-05-13)
  - 02-CONTEXT.md / 02-PLAN.md / 02-VERIFICATION.md 揃い
  - 24 requirements (v2 9 + LLW 4 + AC 8 + CONC 3) 実装
  - 308 tests pass / 99% coverage / 0 lint warnings (commit 0fbd8e6)
  - 詳細: `.planning/phases/02-adaptive/02-VERIFICATION.md`
- **Phase 3 (Evolve)**: 未着手 — 次の着工対象
- **Phase 4 (Production)**: 未着手
- **Phase 5-7 (Rust acceleration)**: 要件のみ定義済 — `docs/requirements_v0.7_rust_acceleration.md` (RUST-01〜14)

## Next Action

```
# Phase 3 (Controlled Self-Evolution) discuss-phase → PLAN.md → 実装
# 別軸: v0.2.0 PyPI 公開 (ユーザ確認後)
# 中断時は SESSION_SUMMARY.md の "次のアクション" 参照。
```

## Active Workspace

- リポジトリ: `D:/projects/llive/` (main ブランチ統一済、origin/main sync)
- GitHub: https://github.com/furuse-kazufumi/llive (public, default = main)
- PyPI: ✅ v0.1.1 公開済 (https://pypi.org/project/llmesh-llive/0.1.1/)
- Phase 2 完了で v0.2.0 PyPI 公開予定 (ユーザ確認後)

## Open Questions / Decisions Pending

すべての主要 open question は 01-CONTEXT.md で `--auto` モードにより解決：

- ✅ Base model: Qwen2.5-0.5B (dev) + Phi-3.5-mini (mid) — D-02
- ✅ Semantic memory: Faiss + JSONL row store — D-11
- ✅ Episodic memory: DuckDB — D-12
- ✅ Embedding: sentence-transformers all-MiniLM-L6-v2 — D-13

Phase 2 で再検討する deferred 項目は 01-CONTEXT.md `<deferred>` セクション参照。

## Recent Activity

| Date | Activity |
|---|---|
| 2026-05-13 | Project scaffolding + docs/specs 生成 + 3 commits |
| 2026-05-13 | TRIZ 内蔵章 (v0.3) + resources 追加 |
| 2026-05-13 | .planning/ 初期化 (PROJECT.md / REQUIREMENTS.md / ROADMAP.md / STATE.md / config.json) |
| 2026-05-13 | Phase 1 CONTEXT.md 生成 (commit 403d35e) — 自律実装フェーズ着手 |

## Configuration

See `.planning/config.json`:
- Mode: YOLO (Max plan 自律性方針に従い対話最小化)
- Granularity: Coarse (4 phases)
- Parallelization: Parallel
- Commit docs: Yes
- Research: No (既存 docs/ + raptor RAD コーパスで代替)
- Plan Check: Yes
- Verifier: Yes
- Model Profile: Inherit (現セッションモデル継承)

---
*Last updated: 2026-05-13 — Phase 1 自律実装セッション着手*
