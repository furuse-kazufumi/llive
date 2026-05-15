"""ApprovalBus — Spec §AB (Approval Bus).

§AB1 replayable — 過去 approval/denial を ledger に残し再現可能
§AB2 principal identification — 誰が approve したかが追跡可能
§AB3 revoke → rollback — 後から取消し可能
§AB4 silence == denial — 沈黙は不承認 (active deny を要求しない)

Production 化 (2026-05-16):
- optional `policy=` で事前 gate (AllowList/DenyList/Composite)
- optional `ledger=` で SQLite 永続化 (再起動越し replay)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from llive.approval.ledger import SqliteLedger


class Verdict(StrEnum):
    APPROVED = "approved"
    DENIED = "denied"
    REVOKED = "revoked"


class _PolicyLike(Protocol):
    def evaluate(self, request: ApprovalRequest) -> Verdict | None: ...


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
    """in-memory pubsub + ledger.

    Args:
        ledger: optional `SqliteLedger` で response/request を永続化. 起動時に
            既存 ledger から pending と response 列を復元する (§AB1).
        policy: optional `ApprovalPolicy` で request を事前評価. Verdict を
            返した場合は人手を待たず即 ledger に書き込む.
    """

    def __init__(
        self,
        *,
        ledger: SqliteLedger | None = None,
        policy: _PolicyLike | None = None,
    ) -> None:
        self._pending: dict[str, ApprovalRequest] = {}
        self._ledger: list[ApprovalResponse] = []
        self._sink: SqliteLedger | None = ledger
        self._policy = policy
        if ledger is not None:
            state = ledger.load()
            self._ledger = list(state.responses)
            # pending = まだ APPROVED/DENIED で決着していない request
            decided: set[str] = {
                r.request_id
                for r in state.responses
                if r.verdict in (Verdict.APPROVED, Verdict.DENIED)
            }
            self._pending = {
                rid: req for rid, req in state.requests.items() if rid not in decided
            }

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
        if self._sink is not None:
            self._sink.append_request(req)
        # policy 事前評価. Verdict 確定なら即応答.
        if self._policy is not None:
            verdict = self._policy.evaluate(req)
            if verdict is not None:
                self._respond(req.request_id, verdict, by="policy:auto", rationale="policy")
        return req

    # -- consumer side ----------------------------------------------------

    def approve(self, request_id: str, *, by: str, rationale: str = "") -> ApprovalResponse:
        return self._respond(request_id, Verdict.APPROVED, by, rationale)

    def deny(self, request_id: str, *, by: str, rationale: str = "") -> ApprovalResponse:
        return self._respond(request_id, Verdict.DENIED, by, rationale)

    def revoke(self, request_id: str, *, by: str, rationale: str = "") -> ApprovalResponse:
        return self._respond(request_id, Verdict.REVOKED, by, rationale)

    def _respond(self, request_id: str, verdict: Verdict, by: str, rationale: str) -> ApprovalResponse:
        # REVOKED は既に決着 (approved/denied) した request にも適用できる必要があるため、
        # pending check は APPROVE/DENY 時のみ。REVOKE は ledger に過去 request_id が
        # 存在することだけ確認する。
        if verdict in (Verdict.APPROVED, Verdict.DENIED):
            if request_id not in self._pending:
                raise KeyError(f"unknown approval request: {request_id!r}")
        else:  # REVOKED
            known = (request_id in self._pending) or any(
                r.request_id == request_id for r in self._ledger
            )
            if not known:
                raise KeyError(f"unknown approval request: {request_id!r}")
        resp = ApprovalResponse(
            request_id=request_id, verdict=verdict, by=by, rationale=rationale
        )
        self._ledger.append(resp)
        if self._sink is not None:
            self._sink.append_response(resp)
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
