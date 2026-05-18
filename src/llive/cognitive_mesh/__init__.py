# SPDX-License-Identifier: Apache-2.0
"""llive Cognitive Mesh — v0.8 高レイヤ要件群 (COG-MESH-01〜10).

requirements_v0.8_cognitive_mesh.md で定義した 10 件の architecture-level
要件 (FullSenseLoop の周囲に被せる Proactive / Mesh / Safety / Evolution
の 4 レイヤ) を実装するパッケージ。

Phase 5 で骨格 (COG-MESH-04/05/06/07/08)、Phase 6 で拡張 (02/03/10)、
Phase 7 で研究的 (01/09) を段階的に配備する。

設計指針 (`feedback_response_timing` 70 点運用 + 倫理は architecture の一部):

* Quiet Hours / Gift Value / Risk gating は **後付けの policy ではなく**
  各 Loop の必須依存 (コンストラクタで注入されないと起動失敗)
* fail-closed in Quiet Hours: 時刻取得 / TZ / env 設定欠落のいずれでも
  自発行動は抑止側に倒す
* on-prem 完結: 能動発話 content 生成は on-prem LLM 経由
* HITL ゲート維持: 能動発話は ApprovalBus を迂回しない

由来 memory (2026-05-18 一連):
* `user_cognitive_mesh_model`
* `feedback_brain_like_trigger_periodic`
* `feedback_proactive_llm_speech`
* `feedback_quiet_hours`
* `project_proactive_llive_demo`
* `feedback_response_timing`
"""

from llive.cognitive_mesh.quiet_hours import QuietHoursGuard  # COG-MESH-07

__all__ = ["QuietHoursGuard"]
