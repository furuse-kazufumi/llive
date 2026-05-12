# STATE: llive

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-13)

**Core value:** コア重みを再学習せず、新しい能力を安全に追加し続けられる LLM 基盤
**Current focus:** Phase 0 完了 → Phase 1 (Minimal Viable Research Platform) 着手準備

## Current Status

- **Phase 0 (Scaffolding / Spec drafting)**: ✅ 完了 (2026-05-13)
  - 要件定義 v0.1〜v0.3 累積完成
  - 設計文書 14 ファイル
  - 公開 LLM ひな形 4 種 (Qwen2.5-7B / Llama-3.1-8B / Mistral-7B-v0.3 / Phi-3.5-mini)
  - 標準 SubBlockSpec 4 ファイル (common / attention / ffn / llive_extensions)
  - TRIZ リソース 3 ファイル (40 原理 / 39×39 マトリクス / 39+11 特性)
  - GSD ワークフロー初期化完了 (.planning/)

- **Phase 1 (MVR)**: 未着手
- **Phase 2 (Adaptive)**: 未着手
- **Phase 3 (Evolve)**: 未着手
- **Phase 4 (Production)**: 未着手

## Next Action

```
/gsd-discuss-phase 1
```

または skip して直接：

```
/gsd-plan-phase 1
```

## Active Workspace

- リポジトリ: `D:/projects/llive/` (git init 済、master ブランチ、3 commits)
- GitHub: 作成依頼中 (`furuse-kazufumi/llive` を public で手動作成 → push 予定)
- PyPI: 未登録 (Phase 1 完了後に v0.1.0 として `llmesh-llive` で初公開予定)

## Open Questions / Decisions Pending

- Phase 1 で採用する base model のデフォルト選定
  - 候補: Qwen2.5-0.5B (開発高速) / TinyLlama 1.1B (CI 軽量) / Qwen2.5-7B (本命想定)
  - 推奨: 開発時 0.5B〜1.1B、ベンチ時 7B
- Semantic memory backend の本命
  - 候補: Faiss (ローカル軽量) / Qdrant (永続化) / pgvector
  - 推奨: Phase 1 は Faiss、Phase 2 で Qdrant 追加
- Graph backend
  - 候補: Kùzu (embedded, fast) / Neo4j (mature) / NetworkX + sqlite (simple)
  - 推奨: Kùzu

## Recent Activity

| Date | Activity |
|---|---|
| 2026-05-13 | Project scaffolding + docs/specs 生成 + 3 commits |
| 2026-05-13 | TRIZ 内蔵章 (v0.3) + resources 追加 |
| 2026-05-13 | .planning/ 初期化 (PROJECT.md / REQUIREMENTS.md / ROADMAP.md / STATE.md / config.json) |

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
*Last updated: 2026-05-13 after initialization*
