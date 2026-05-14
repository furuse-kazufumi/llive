# 一个直面 LLM "遗忘"问题的个人项目 — llive

> 我正在设计并实现 `llmesh-llive`：一个自演化的模块化记忆 LLM 框架。
> 既是为了**更深地理解 AI**，也是为了**把自己的工程职业锚定在真正困难的问题上**。

## 为什么开始

LLM 越是被推到真实产品里，就越频繁撞上同一堵墙：

> 让模型学新知识，老的判断标准就莫名其妙地坏了。

这种**灾难性遗忘 (catastrophic forgetting)**，是受监管行业和审计驱动场景中 AI 落地停滞的最大原因之一。`llive` 是我把这种痛点重新表述成设计问题的尝试：*在不重训巨大冻结 LLM 内核的前提下，如何持续吸收新能力？*

实践下来发现，这是一个**AI 用户和 AI 构建者都被迫思考的问题**。在生产中触碰 LLM 的人，迟早都得为自己的答案辩护。

## llive 的 8 个设计支柱

1. **冻结内核 + 可塑外围** — 解码器型 LLM 内核保持冻结。Adapter / LoRA / 4 层外部记忆 / 可变长 BlockContainer 负责吸收新能力。
2. **4 层记忆职责分离** — semantic（知识）/ episodic（经验）/ structural（关系）/ parameter（差分权重）。
3. **声明式结构描述** — 子块序列以 YAML 表达，单位粒度让 AI 自己也能提案与对比。
4. **审查制自演化** — 仅有记忆写入和轻微路由调整在线发生；结构性变更走离线审查路径。
5. **生物记忆模型直接嵌入** — 海马–皮层巩固周期、surprise 评分、相位转换。
6. **形式验证作为 promotion 门禁** — Lean / Z3 / TLA+ 在 LLM 评估**之前**校验结构不变量。
7. **原生融合 llmesh / llove** — 工业 IoT 传感器直接进入 episodic memory；HITL 在 TUI 内闭环。
8. **内置 TRIZ 创新方法** — 40 发明原理 + 39×39 矛盾矩阵 + ARIZ + 9 画法实现为 mutation policy。指标矛盾被自动检测、映射到原理、引用研究语料、生成 CandidateDiff，整套自走。

## 为什么这对我的职业很重要

LLM 周边工具迭代极快，看上去很流利却没有真深度，是这个领域的常见状态。做 `llive` 的过程，让我留下了一堆**可以辩护的设计判断**，而不是只剩 buzzword：

- 我能在实现层面，把"生产级持续学习有多难"说清楚。
- 我把形式验证（Lean / Z3 / TLA+）放在 LLM 评分**之前**，作为降低评估成本与风险的设计模式。
- 我把生物记忆模型翻译成 CS 语言，磨砺了跨领域桥接的能力。
- 我把 **TRIZ 发明原理实装成 mutation policy**，把专利世界的推理方式带进 ML 系统。
- 我把 **Ed25519 签名 adapter 与 SHA-256 审计链** 嵌入持续学习，逼近受监管行业 AI 真正需要的形态。

这些技能，无论在 AI 创业公司、受监管行业的导入团队，还是研究型 R&D 团队，都被实际需要。

## 当前状态 (2026-05-14)

- **v0.5.0** — Phase 5 first wire-in：Rust kernel 已接入生产热路径。
- **444 个测试 / 0 lint**（v0.4.0 基线 439 + RUST-03 parity 5）。
- Z3 静态验证、Failed Reservoir、Reverse-Evolution Monitor、TRIZ Self-Reflection、Ed25519 签名 adapter、SHA-256 审计链 ─ v0.3.0 起已就位。
- v0.4.0 建立 Rust 加速 **骨架**（PyO3 0.22 + Cargo workspace + RUST-13 parity harness）。v0.5.0 把 `compute_surprise` (MEM-07) 自动委派到 Rust，扩展不存在时回退 numpy，保证 **1e-6 parity**。
- [Unreleased]: F25 (g) `LoveBridge` writer ─ 把 llive ↔ llmesh ↔ llove 通过 MCP 串起来的 shim。
- PyPI: `pip install llmesh-llive`。

## 走向哪里

这个 OSS 的目标，是成为**工程师在受监管环境推进 AI 落地时可以拿来论证的参考实现**。把 `llive` 与 `llmesh`（本地 MCP 枢纽）、`llove`（TUI dashboard）组合起来，就构成一套不依赖云、保留审计证迹、可在现场观测的持续学习栈。

如果对你有共鸣，最简单的入口是 `pip install llmesh-llive`。设计判断、失败、演化过程，我都尽可能透明地保留在仓库与 docs 中。

> GitHub: <https://github.com/furuse-kazufumi/llive>
> PyPI: `pip install llmesh-llive`

#AI #LLM #持续学习 #MLOps #形式验证 #开源 #个人项目 #职业发展
