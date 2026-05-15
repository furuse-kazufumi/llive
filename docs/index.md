---
layout: default
title: "FullSense ™ — llive Documentation"
description: "Self-evolving modular memory LLM framework"
---

# FullSense ™ — llive

> **Part of the [FullSense ™](../TRADEMARK.md) family** — `llmesh` ・ **llive** ・ `llove` の 3 製品で構成される FullSense ブランドの中で、本サイトは **llive (self-evolving modular memory LLM framework)** の公式 documentation です。

---

## FullSense Family

```
                  FullSense ™   (umbrella brand & spec)
                  /     |     \
              llmesh   llive   llove
              (hub)   (memory) (TUI)
```

| Product   | Role                                       | GitHub                                                |
|-----------|--------------------------------------------|-------------------------------------------------------|
| **llmesh** | secure LLM hub / on-prem MCP server        | <https://github.com/furuse-kazufumi/llmesh>          |
| **llive**  | self-evolving modular memory LLM framework | <https://github.com/furuse-kazufumi/llive>           |
| **llove**  | TUI dashboard / HITL workbench             | <https://github.com/furuse-kazufumi/llove>           |
| llmesh-suite | one-shot installer                       | <https://github.com/furuse-kazufumi/llmesh-suite>    |

PyPI から: `pip install llmesh-llive` (v0.6.0 時点。v1.0.0 で `fullsense-llive` へ rename 予定 — [v1.0_migration_plan.md](v1.0_migration_plan.md) 参照)

## Quick Start

```bash
# install
pip install llmesh-llive

# minimal demo
python -m llive.demo
```

詳細は [README.md](https://github.com/furuse-kazufumi/llive#readme) を参照。

## What's New (v0.6.0, 2026-05-16)

- **9 axes skeleton** 完成 — KAR / DTKR / APO / ICP / TLB / Math / PM / RPAR / SIL
- **Approval Bus production 化** (Policy + SQLite Ledger, C-1)
- **`@govern` + ProductionOutputBus** (Policy gate × 副作用 emit, C-2)
- **Cross-substrate migration spike** (§MI1, C-3)
- **Apache-2.0 + Commercial dual-license** に切替
- **FullSense umbrella ブランド** 導入

詳細: [CHANGELOG](https://github.com/furuse-kazufumi/llive/blob/main/CHANGELOG.md)

## 設計の核

1. **固定コア + 可変周辺** — Decoder-only LLM コアは凍結、周辺で能力を吸収
2. **4 層メモリの責務分離** — semantic / episodic / structural / parameter
3. **宣言的構造記述** — sub-block 列を YAML で表現
4. **審査付き自己進化** — オンラインは memory write、構造変更はオフライン審査
5. **生物学的記憶モデル** — 海馬-皮質 consolidation cycle、surprise score
6. **形式検証付き promotion** — Lean / Z3 / TLA+
7. **llmesh / llove ファミリー統合**
8. **TRIZ アイデア出しを内蔵** — 40 原理 + 39×39 マトリクス + ARIZ + 9 画法
9. **FullSense Spec v1.1** リファレンス実装 — 9 軸 (KAR/DTKR/APO/ICP/TLB/Math/PM/RPAR/SIL) Conformance Manifest holds=24

## Documentation

| Topic                          | File                                                  |
|--------------------------------|-------------------------------------------------------|
| FullSense Spec v1.1            | [fullsense_spec_eternal.md](fullsense_spec_eternal.md) |
| Roadmap                        | [roadmap.md](roadmap.md)                              |
| Architecture                   | [architecture.md](architecture.md)                    |
| Data model                     | [data_model.md](data_model.md)                        |
| MCP integration                | [mcp_integration.md](mcp_integration.md)              |
| Security model                 | [security_model.md](security_model.md)                |
| Testing strategy               | [testing_strategy.md](testing_strategy.md)            |
| Evaluation metrics             | [evaluation_metrics.md](evaluation_metrics.md)        |
| Glossary                       | [glossary.md](glossary.md)                            |
| v1.0 migration plan            | [v1.0_migration_plan.md](v1.0_migration_plan.md)      |

### Requirements (バージョン別)

- [v0.1](requirements_v0.1.md)
- [v0.2 addendum (RAD)](requirements_v0.2_addendum.md)
- [v0.3 (TRIZ self-evolution)](requirements_v0.3_triz_self_evolution.md)
- [v0.4 (LLM Wiki)](requirements_v0.4_llm_wiki.md)
- [v0.5 (spatial memory)](requirements_v0.5_spatial_memory.md)
- [v0.6 (concurrency)](requirements_v0.6_concurrency.md)
- [v0.7 (Rust acceleration)](requirements_v0.7_rust_acceleration.md)

## Articles

- LinkedIn 概観: [ja](linkedin/post_2026-05-14_overview.ja.md) / [en](linkedin/post_2026-05-14_overview.en.md) / [zh](linkedin/post_2026-05-14_overview.zh.md)
- 2026-05-16 update: [ja](linkedin/post_2026-05-16_update.ja.md) / [en](linkedin/post_2026-05-16_update.en.md) / [zh](linkedin/post_2026-05-16_update.zh.md)
- Qiita 概観: [qiita-overview.md](qiita/qiita-overview.md)

## Legal

- [LICENSE](https://github.com/furuse-kazufumi/llive/blob/main/LICENSE) — Apache-2.0
- [LICENSE-COMMERCIAL](https://github.com/furuse-kazufumi/llive/blob/main/LICENSE-COMMERCIAL)
- [NOTICE](https://github.com/furuse-kazufumi/llive/blob/main/NOTICE)
- [TRADEMARK.md](https://github.com/furuse-kazufumi/llive/blob/main/TRADEMARK.md)
- [SECURITY.md](https://github.com/furuse-kazufumi/llive/blob/main/SECURITY.md)
- [CONTRIBUTING.md](https://github.com/furuse-kazufumi/llive/blob/main/CONTRIBUTING.md)
- [Trademark drafts](legal/trademark/) — Wave 1 (FullSense) + Wave 2 (llmesh/llive/llove)

## Links

- **GitHub**: <https://github.com/furuse-kazufumi/llive>
- **PyPI**: <https://pypi.org/project/llmesh-llive/>
- **Contact**: `kazufumi@furuse.work`

---

*FullSense ™ / llive ™ / llmesh ™ / llove ™ are trademarks of Kazufumi Furuse.*
*Code distributed under Apache-2.0; commercial license available.*
