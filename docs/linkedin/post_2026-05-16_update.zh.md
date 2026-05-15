# 2 天内 9 个核心轴上线 — llive v0.6.0 更新

> 距[上次发文 (2026-05-14)](./post_2026-05-14_overview.zh.md)仅过去 2 天。
> `llmesh-llive` 从「8 个设计支柱」推进到「9 轴 MVP skeleton 完成 +
> 第一轴 production 化 + dual-license 切换」。这是一份记录速度的短篇更新。

## 变化对比 (2026-05-14 → 2026-05-16)

| 项目 | 2026-05-14 | 2026-05-16 |
|---|---|---|
| 测试数 | 444 PASS | **815 PASS** (+371) |
| 架构轴 | 8 个设计柱 | **9 轴 skeleton 完成**（KAR / DTKR / APO / ICP / TLB / Math / PM / RPAR / SIL） |
| Conformance Manifest | 未跟踪 | **holds=24 / violated=0 / undecidable=1** |
| Approval Bus | in-memory MVP | **policy + SQLite ledger 完成 production 化**（C-1 完成） |
| License | MIT | **Apache-2.0 + Commercial dual-license**（v0.6.0） |
| 治理文件 | 仅 LICENSE | NOTICE / CONTRIBUTING (DCO) / SECURITY / TRADEMARK 已齐 |
| SPDX 头部 | 无 | **全部 204 个 .py 文件加入 `SPDX-License-Identifier: Apache-2.0`** |

## 9 轴 skeleton — FullSense Spec v1.1 的最终形态

- **KAR (Knowledge Autarky)** — 把 RAD 从 49 个分野扩张到 100 个，长期知识主权路线图
- **DTKR (Disk-Tier Knowledge Routing)** — MoE 的磁盘版，1 个 skill = 1 个文件，便于模块化进化
- **APO (Autonomous Performance Optimization)** — §E2 bounded modification 下的自我调优
- **ICP (Idle-Collaboration Protocol)** — idle 时段与其他 Local LLM 协作（继承 LLMesh 思想）
- **TLB (Thought Layer Bridge)** — Manifold Cache + Global Coordinator 抑制多视角组合爆炸
- **Math Toolkit** — 各轴从 RAD 数学语料直接引出根据
- **PM (Publication Media)** — asciinema / SVG / GIF / mp4 嵌入 README
- **RPAR (Robotic Process Automation Realisation)** — Sandbox → Permitted-action 分阶段迁移
- **SIL (Self-Interrogation Layer)** — 5 个 Interrogator 多角度盘问

**holds=24 / violated=0** 表明 9 轴 MVP 通过 Spec 一致性检查。

## Approval Bus production 化（C-1 完成）

RPA 层一旦接触真实副作用，approval bus 就是承重梁。v0.5.x 仅有 in-memory MVP，v0.6.0 推出:

- **Policy 抽象** — `AllowList` / `DenyList` / `CompositePolicy`，`deny_overrides(allow, deny)` 一行写出 "deny 优先" 组合
- **SQLite 持久化** — 仅依赖 stdlib `sqlite3`。schema v1（requests / responses / meta），跨重启可 replay
- **向后兼容** — `ApprovalBus()` 不带参数与旧行为完全一致（旧 8 个测试 0 修改）

下一步：`@govern(policy)` 接入 ProductionOutputBus（C-2）。

## 为什么 dual-license

为兼顾 OSS 普及、长期专利风险防御、商用合作余地，v0.6.0 从 MIT 切换到 **Apache-2.0 + Commercial**:

- Apache-2.0 — 给用户提供明确的**专利 grant**，对寄予者的专利反诉风险显著降低
- Commercial — 给需要 SLA / 赔偿 / 闭源集成的企业留出独立通道

同时整理 NOTICE / CONTRIBUTING (DCO 1.1) / SECURITY / TRADEMARK，与 `@apache` / `@cncf` 圈惯例对齐。

## 职业角度新增收获

在上次列表基础上，本周末新增 4 条：

1. **用 unit test 固定 9 轴 spec** — 不是形式验证，而是 runtime conformance manifest 每次 CI 都检查
2. **后置 production 化 approval bus** — auto-policy + persistent ledger + 向后兼容，三者一次性 retrofit
3. **划清 OSS / 商用界线** — 能够用利益相关者听懂的语言解释 dual-license 的合理性
4. **SPDX / NOTICE / DCO / SBOM 操作** — 把 "license 质量" 当作 CI 信号，与 code 质量并列

第 3 条是 AI 创业团队和受监管行业 AI 团队**容易卡在文档上**的环节。

## 当前数字

- **v0.6.0**（今天 cut）— 9 轴 skeleton + C-1 production + dual-license
- **815 tests / ruff clean**（v0.5.0 是 444 + 之后 +371）
- PyPI: `pip install llmesh-llive`
- 并行运行 4 个仓库: llive / llmesh / llove / llmesh-demos

## 想呈现什么

简言之：**个人项目也能维持这种节奏**——前提是路线图具体、测试先行（0→1 估算不漂移）、Spec 钉死在 CLAUDE.md 与 CONTRIBUTING.md（决策不绕圈）。

> GitHub: <https://github.com/furuse-kazufumi/llive>
> PyPI: `pip install llmesh-llive`

#AI #LLM #ContinualLearning #MLOps #OpenSource #ApacheLicense #IndieDev
