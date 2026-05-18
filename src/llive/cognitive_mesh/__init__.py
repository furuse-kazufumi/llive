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

from llive.cognitive_mesh.brief_containers import (  # COG-MESH-08
    BriefDeque,
    BriefMap,
    BriefRef,
    BriefTree,
)
from llive.cognitive_mesh.brief_runner_bridge import (  # COG-MESH-08 完成配線
    BriefDequeRunnerBridge,
)
from llive.cognitive_mesh.embedding_similarity import (  # COG-MESH-02 拡張
    EmbeddingSimilarityFn,
)
from llive.cognitive_mesh.gift_value import (  # COG-MESH-05
    DEFAULT_THRESHOLD,
    GiftValue,
    GiftValueEstimator,
)
from llive.cognitive_mesh.grammar_layer import (  # COG-MESH-09
    GrammarChangeStatus,
    GrammarLayer,
    GrammarSnapshot,
    ProposedChange,
    UsageEvidence,
)
from llive.cognitive_mesh.idle_training import (  # COG-MESH-04
    IdleTrainingScheduler,
    InfoSource,
    IngestEvent,
)
from llive.cognitive_mesh.intervention import (  # COG-MESH-03 完成配線
    RiskInterventionAdapter,
)
from llive.cognitive_mesh.mesh_5w1h import (  # COG-MESH-10
    ALL_CHANNELS,
    GRANULARITY_ORDER,
    Granularity,
    Mesh5W1HEdge,
    Mesh5W1HGraph,
    Mesh5W1HNode,
    annotate_5w1h,
    channel_name,
    granularity_of,
    is_finer,
)
from llive.cognitive_mesh.mesh_annotator import (  # COG-MESH-10 完成配線
    Mesh5W1HAnnotator,
)
from llive.cognitive_mesh.multi_brief import (  # COG-MESH-01
    CoherenceEvent,
    MultiBriefCoherenceManager,
)
from llive.cognitive_mesh.proactive import (  # COG-MESH-06
    ConsistencyViolation,
    ProactiveEvent,
    ProactiveLoop,
    ProactiveUtterance,
    SuppressedUtterance,
)
from llive.cognitive_mesh.quiet_hours import QuietHoursGuard  # COG-MESH-07
from llive.cognitive_mesh.title_recall import (  # COG-MESH-02
    Foreshadow,
    RecallReport,
    RecallStatus,
    TitleRecallPlanner,
)
from llive.cognitive_mesh.tonic_risk import (  # COG-MESH-03
    RiskAlert,
    RiskModel,
    TonicRiskMonitor,
)

__all__ = [
    # Note: alphabetical (RUF022)、COG-MESH ID 別の整理は本ファイル
    # 中段の import 順を参照
    "ALL_CHANNELS",
    "DEFAULT_THRESHOLD",
    "GRANULARITY_ORDER",
    "BriefDeque",
    "BriefDequeRunnerBridge",
    "BriefMap",
    "BriefRef",
    "BriefTree",
    "CoherenceEvent",
    "EmbeddingSimilarityFn",
    "Foreshadow",
    "GiftValue",
    "GiftValueEstimator",
    "GrammarChangeStatus",
    "GrammarLayer",
    "GrammarSnapshot",
    "Granularity",
    "IdleTrainingScheduler",
    "InfoSource",
    "IngestEvent",
    "Mesh5W1HAnnotator",
    "Mesh5W1HEdge",
    "Mesh5W1HGraph",
    "Mesh5W1HNode",
    "MultiBriefCoherenceManager",
    "ProactiveLoop",
    "ProactiveUtterance",
    "ProposedChange",
    "QuietHoursGuard",
    "RecallReport",
    "RecallStatus",
    "RiskAlert",
    "RiskInterventionAdapter",
    "RiskModel",
    "SuppressedUtterance",
    "TitleRecallPlanner",
    "TonicRiskMonitor",
    "UsageEvidence",
    "annotate_5w1h",
    "channel_name",
    "granularity_of",
    "is_finer",
]
