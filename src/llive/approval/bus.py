"""ApprovalBus — Spec §AB (Approval Bus) の MVP.

§AB1 replayable — 過去 approval/denial を ledger に残し再現可能
§AB2 principal identification — 誰が approve したかが追跡可能
§AB3 revoke → rollback — 後から取消し可能
§AB4 silence == denial — 沈黙は不承認 (active deny を要求しない)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum


class Verdict(StrEnum):
    APPROVED = "approved"
    DENIED = "denied"
    REVOKED = "revoked"


@dataclass(frozen=True)
class ApprovalRequest:
    """approval を求める request."""

    request_id: str
    action: str
    """action の short name (e.g. 'shell:rm -rf', 'mouse:click')."""
    payload: dict[str, object]
    """action 固有の引数 (実 RPA driver が解釈)."""
    principal: str = "agent"
    timeout_s: float = 5.0
    created_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class ApprovalResponse:
    """approve/deny/revoke 結果."""

    request_id: str
    verdict: Verdict
    by: str
    """approve/deny した principal (人間 / 別 agent / policy)."""
    rationale: str = ""
    at: float = field(default_factory=time.time)


class ApprovalBus:
    """in-memory pubsub + ledger (MVP).

    実運用では durable backend (sqlite / disk JSONL) と組合せる。
    """

    def __init__(self) -> None:
        self._pending: dict[str, ApprovalRequest] = {}
        self._ledger: list[ApprovalResponse] = []

    # -- producer side ----------------------------------------------------

    def request(self, action: str, payload: dict[str, object], *, principal: str = "agent", timeout_s: float = 5.0) -> ApprovalRequest:
        req = ApprovalRequest(
            request_id=uuid.uuid4().hex,
            action=action,
            payload=dict(payload),
            principal=principal,
            timeout_s=timeout_s,
        )
        self._pending[req.request_id] = req
        return req

    # -- consumer side ----------------------------------------------------

    def approve(self, request_id: str, *, by: str, rationale: str = "") -> ApprovalResponse:
        return self._respond(request_id, Verdict.APPROVED, by, rationale)

    def deny(self, request_id: str, *, by: str, rationale: str = "") -> ApprovalResponse:
        return self._respond(request_id, Verdict.DENIED, by, rationale)

    def revoke(self, request_id: str, *, by: str, rationale: str = "") -> ApprovalResponse:
        return self._respond(request_id, Verdict.REVOKED, by, rationale)

    def _respond(self, request_id: str, verdict: Verdict, by: str, rationale: str) -> ApprovalResponse:
        if request_id not in self._pending:
            raise KeyError(f"unknown approval request: {request_id!r}")
        resp = ApprovalResponse(
            request_id=request_id, verdict=verdict, by=by, rationale=rationale
        )
        self._ledger.append(resp)
        # APPROVED / DENIED は pending から消す、REVOKED は ledger のみに残す
        if verdict in (Verdict.APPROVED, Verdict.DENIED):
            self._pending.pop(request_id, None)
        return resp

    # -- query ------------------------------------------------------------

    def current_verdict(self, request_id: str) -> Verdict:
        """request の最新 verdict を返す. revoke 後は REVOKED、未応答は DENIED (§AB4 silence)."""
        latest: ApprovalResponse | None = None
        for r in self._ledger:
            if r.request_id == request_id:
                latest = r
        if latest is None:
            # silence == denial (§AB4)
            return Verdict.DENIED
        return latest.verdict

    def pending(self) -> list[ApprovalRequest]:
        return list(self._pending.values())

    def ledger(self) -> list[ApprovalResponse]:
        return list(self._ledger)

    # -- §AB1 replay ------------------------------------------------------

    def replay(self) -> list[tuple[str, Verdict]]:
        """ledger を見て、各 request の最終 verdict 列を返す.

        §AB1 replayable: 同じ ledger で再構築すれば同じ verdict 列が得られる.
        """
        last: dict[str, Verdict] = {}
        order: list[str] = []
        for r in self._ledger:
            if r.request_id not in last:
                order.append(r.request_id)
            last[r.request_id] = r.verdict
        return [(rid, last[rid]) for rid in order]


__all__ = ["ApprovalBus", "ApprovalRequest", "ApprovalResponse", "Verdict"]
