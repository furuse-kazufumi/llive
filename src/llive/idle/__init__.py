# SPDX-License-Identifier: Apache-2.0
"""ICP — Idle-Collaboration Protocol.

User PC が idle なときに別 Local LLM 等と協働できるよう、idle 検出を
読み取り専用 API として提供する。実際の peer 通信は Level 3 + ICP
PeerDispatcher で実装。
"""

from llive.idle.collab import (
    CollabQuery,
    CollabResult,
    IdleCollaborator,
    PeerClient,
    PeerProvider,
    TickReport,
)
from llive.idle.detector import IdleDetector, IdleStatus

__all__ = [
    "CollabQuery",
    "CollabResult",
    "IdleCollaborator",
    "IdleDetector",
    "IdleStatus",
    "PeerClient",
    "PeerProvider",
    "TickReport",
]
