# SPDX-License-Identifier: Apache-2.0
"""@govern decorator — function を ApprovalBus 越しに gate する.

使用例::

    bus = ApprovalBus(policy=AllowList.of({"file:write"}))

    @govern(bus, action="file:write")
    def write_file(path: Path, content: str) -> None:
        path.write_text(content)

    write_file(Path("a.txt"), "hello")  # policy 経由で gate

`payload_fn` を渡すと action payload をカスタマイズできる::

    @govern(
        bus,
        action="net:fetch",
        payload_fn=lambda url, **kw: {"url": url, "method": kw.get("method", "GET")},
    )
    def fetch(url: str, *, method: str = "GET") -> str: ...

`on_denied` を渡すと DENIED/silence 時の代替戻り値 (or 副作用なし fallback) を指定可能.
None の場合は `None` を返す.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

from llive.approval.bus import ApprovalBus, Verdict

P = ParamSpec("P")
R = TypeVar("R")


def _default_payload(*args: Any, **kwargs: Any) -> dict[str, object]:
    return {"args": [repr(a) for a in args], "kwargs": {k: repr(v) for k, v in kwargs.items()}}


def govern(
    bus: ApprovalBus,
    action: str,
    *,
    principal: str = "agent",
    payload_fn: Callable[..., dict[str, object]] | None = None,
    on_denied: Callable[..., R] | None = None,  # type: ignore[valid-type]
    rationale: str = "",
) -> Callable[[Callable[P, R]], Callable[P, R | None]]:
    """ApprovalBus 越しに function call を gate する decorator factory.

    Args:
        bus: ApprovalBus instance (policy/ledger を内包していれば自動 gate)
        action: approval request の action 識別子 (e.g. "file:write")
        principal: request の principal フィールド
        payload_fn: (args, kwargs) から approval payload を作る関数. None なら
            args / kwargs の repr を payload に入れる
        on_denied: DENIED/silence 時に呼ぶ関数. None なら None を返す
        rationale: 静的な rationale 文字列 (decorator 自体には反映されない、
            将来 audit log 用に保留)
    """
    _ = rationale  # reserved for future audit annotations

    def decorator(fn: Callable[P, R]) -> Callable[P, R | None]:
        @functools.wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | None:
            payload = (
                payload_fn(*args, **kwargs) if payload_fn is not None else _default_payload(*args, **kwargs)
            )
            req = bus.request(action, payload, principal=principal)
            verdict = bus.current_verdict(req.request_id)
            if verdict is Verdict.APPROVED:
                return fn(*args, **kwargs)
            if on_denied is not None:
                return on_denied(*args, **kwargs)
            return None

        return wrapper

    return decorator


__all__ = ["govern"]
