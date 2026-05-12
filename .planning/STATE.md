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

- **Phase 1 (MVR)**: 進行中 (2026-05-13 着手)
  - ✅ CONTEXT.md (01-CONTEXT.md / 01-DISCUSSION-LOG.md, commit 403d35e)
  - 🔄 PLAN.md / 実装 (8 時間自律セッション中)
- **Phase 2 (Adaptive)**: 未着手
- **Phase 3 (Evolve)**: 未着手
- **Phase 4 (Production)**: 未着手

## Next Action

```
# 自律セッション中。CONTEXT.md 完了後、PLAN.md → 実装 → テストへ自走。
# 中断時は SESSION_SUMMARY.md の "次のアクション" 参照。
```

## Active Workspace

- リポジトリ: `D:/projects/llive/` (git init 済、main ブランチ統一済)
- GitHub: https://github.com/furuse-kazufumi/llive (public, default = main)
- PyPI: 未登録 (Phase 1 完了後に v0.1.0 として `llmesh-llive` で初公開予定、ユーザ確認が前提)

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
