# SPDX-License-Identifier: Apache-2.0
"""RPAR Approval Bus — Spec §AB.

Level 3 (Permitted-action) で必要な approval channel の MVP skeleton。
in-memory pubsub + replayable ledger を提供する。実 RPA driver はこのバスに
依存するため、テスト用 fake と本物 (Level 3) で同じ API を保てる。
"""

from llive.approval.bus import ApprovalBus, ApprovalRequest, ApprovalResponse, Verdict
from llive.approval.ledger import LedgerState, SqliteLedger
from llive.approval.policy import (
    AllowList,
    ApprovalPolicy,
    CompositePolicy,
    DenyList,
    deny_overrides,
)

__all__ = [
    "AllowList",
    "ApprovalBus",
    "ApprovalPolicy",
    "ApprovalRequest",
    "ApprovalResponse",
    "CompositePolicy",
    "DenyList",
    "LedgerState",
    "SqliteLedger",
    "Verdict",
    "deny_overrides",
]
