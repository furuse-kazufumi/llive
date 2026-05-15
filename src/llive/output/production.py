# SPDX-License-Identifier: Apache-2.0
"""ProductionOutputBus — ApprovalBus gate を通した副作用 emit.

低レベル API: `emit_raw(action, payload, *, on_approved)` で任意の副作用を
approval 越しに実行。

高レベル API: `emit_file(path, content)` / `emit_mcp_push(target, message)` /
`emit_llove_push(view_id, payload)` で典型的副作用を 1 行で。

DENIED / silence 時: 副作用を起こさず、optional `sandbox` (SandboxOutputBus)
に `record_denied_emit` 経由で観測ログを残す (§AB4 silence == denial + §I3
inspectable の両立).

MCP push / llove push の **実装は注入式**: bus 生成時に
`mcp_push_fn=callable` / `llove_push_fn=callable` を渡すことで、本 module は
具体的な transport (MCP client / llove HTTP / 任意) に依存しない。
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from llive.approval.bus import ApprovalBus, Verdict

# Type aliases for injected side-effect functions
McpPushFn = Callable[[str, dict[str, Any]], None]
"""MCP push function: (target, message) -> None. Raises on transport failure."""

LlovePushFn = Callable[[str, dict[str, Any]], None]
"""llove push function: (view_id, payload) -> None. Raises on transport failure."""


@dataclass(frozen=True)
class ProductionRecord:
    """1 回の emit 試行の記録 (approved/denied 問わず残る)."""

    action: str
    payload: dict[str, object]
    verdict: Verdict
    request_id: str
    side_effect_executed: bool
    rationale: str = ""
    error_repr: str = ""
    at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class EmitResult:
    """emit() の戻り値."""

    record: ProductionRecord
    error: Exception | None = None

    @property
    def approved(self) -> bool:
        """副作用が approved + 実行成功した場合のみ True."""
        return (
            self.record.verdict is Verdict.APPROVED
            and self.record.side_effect_executed
            and self.error is None
        )


class ProductionOutputBus:
    """ApprovalBus gate を通した副作用 emit bus.

    Args:
        approval: gate に使う ApprovalBus
        sandbox: DENIED 時 mirror 用 SandboxOutputBus (任意)
        principal: approval request の principal
        mcp_push_fn: emit_mcp_push 用の transport 関数 (注入)
        llove_push_fn: emit_llove_push 用の transport 関数 (注入)
    """

    def __init__(
        self,
        approval: ApprovalBus,
        *,
        sandbox: Any | None = None,  # SandboxOutputBus (循環 import 回避)
        principal: str = "production-bus",
        mcp_push_fn: McpPushFn | None = None,
        llove_push_fn: LlovePushFn | None = None,
    ) -> None:
        self.approval = approval
        self.sandbox = sandbox
        self.principal = principal
        self._mcp_push_fn = mcp_push_fn
        self._llove_push_fn = llove_push_fn
        self._records: list[ProductionRecord] = []
        self._lock = threading.Lock()

    # -- low-level --------------------------------------------------------

    def emit_raw(
        self,
        action: str,
        payload: dict[str, object],
        *,
        on_approved: Callable[[], Any],
        rationale: str = "",
    ) -> EmitResult:
        """approval gate を通して副作用 `on_approved()` を実行する.

        Returns:
            EmitResult — record + 例外 (副作用中の error は raise せず record.error_repr に格納).
        """
        req = self.approval.request(action, dict(payload), principal=self.principal)
        verdict = self.approval.current_verdict(req.request_id)

        executed = False
        err: Exception | None = None
        if verdict is Verdict.APPROVED:
            try:
                on_approved()
                executed = True
            except Exception as e:  # noqa: BLE001 — emit が外部 transport に依存するため捕捉
                err = e

        record = ProductionRecord(
            action=action,
            payload=dict(payload),
            verdict=verdict,
            request_id=req.request_id,
            side_effect_executed=executed,
            rationale=rationale or (f"verdict={verdict.value}" if verdict is not Verdict.APPROVED else ""),
            error_repr=repr(err) if err is not None else "",
        )

        with self._lock:
            self._records.append(record)

        # DENIED / silence は sandbox に mirror (副作用なし)
        if verdict is not Verdict.APPROVED and self.sandbox is not None:
            recorder = getattr(self.sandbox, "record_denied_emit", None)
            if recorder is not None:
                recorder(action=action, payload=payload, request_id=req.request_id, rationale=record.rationale)

        return EmitResult(record=record, error=err)

    # -- high-level wrappers ---------------------------------------------

    def emit_file(self, path: Path | str, content: str, *, encoding: str = "utf-8") -> EmitResult:
        """ファイルに content を書き出す (UTF-8 既定)."""
        p = Path(path)
        return self.emit_raw(
            action="file:write",
            payload={"path": str(p), "bytes": len(content.encode(encoding))},
            on_approved=lambda: (p.parent.mkdir(parents=True, exist_ok=True), p.write_text(content, encoding=encoding)),
        )

    def emit_mcp_push(self, target: str, message: dict[str, Any]) -> EmitResult:
        """MCP client に message を push する.

        Raises:
            RuntimeError: mcp_push_fn 未注入で呼ばれた場合 (gate 通過後に発火).
        """
        return self.emit_raw(
            action="mcp:push",
            payload={"target": target, "message_keys": sorted(message.keys())},
            on_approved=self._make_mcp_push_callback(target, message),
        )

    def _make_mcp_push_callback(self, target: str, message: dict[str, Any]) -> Callable[[], None]:
        def _push() -> None:
            if self._mcp_push_fn is None:
                raise RuntimeError("mcp_push_fn not configured on ProductionOutputBus")
            self._mcp_push_fn(target, message)
        return _push

    def emit_llove_push(self, view_id: str, payload: dict[str, Any]) -> EmitResult:
        """llove view に payload を push する."""
        return self.emit_raw(
            action="llove:push",
            payload={"view_id": view_id, "payload_keys": sorted(payload.keys())},
            on_approved=self._make_llove_push_callback(view_id, payload),
        )

    def _make_llove_push_callback(self, view_id: str, payload: dict[str, Any]) -> Callable[[], None]:
        def _push() -> None:
            if self._llove_push_fn is None:
                raise RuntimeError("llove_push_fn not configured on ProductionOutputBus")
            self._llove_push_fn(view_id, payload)
        return _push

    # -- query -----------------------------------------------------------

    def records(self) -> list[ProductionRecord]:
        with self._lock:
            return list(self._records)

    def approved_records(self) -> list[ProductionRecord]:
        with self._lock:
            return [r for r in self._records if r.verdict is Verdict.APPROVED and r.side_effect_executed]

    def denied_records(self) -> list[ProductionRecord]:
        with self._lock:
            return [r for r in self._records if r.verdict is not Verdict.APPROVED]

    def __len__(self) -> int:
        return len(self._records)


__all__ = [
    "EmitResult",
    "LlovePushFn",
    "McpPushFn",
    "ProductionOutputBus",
    "ProductionRecord",
]
