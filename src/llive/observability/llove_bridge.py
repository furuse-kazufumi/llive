"""F25 (g) — llove bridge writer (route_trace / memory_link / bwt).

`docs/llove_jsonl_v1.md` v1 仕様 (Phase 2 OBS-03 凍結) に従い、llive が
3 種データを以下のいずれか / 両方の経路で publish できる薄い shim:

1. **JSONL writer** (既定): `logs/llove/{route_trace, memory_link, bwt}.jsonl`
   への append。llmesh / llove が tail / poll で読む。

2. **MCP ingest push** (opt-in): `LLIVE_MCP_INGEST_URL` 環境変数が
   設定されていれば、同じ event を llmesh の ``POST /timeline/ingest``
   にも投げる。リアルタイム連携用。

設計判断:

- **既存 `bwt.py` / `trace.py` は変更なし**: llive 本体の breaking
  change を避け、bridge は完全な新規 module として独立。既存 caller は
  従来 jsonl を書き続ける + bridge 経由でも emit できる、という重畳構造。
- **依存ゼロ**: stdlib `urllib.request` (llove と同じ哲学)。MCP push
  失敗は fail-closed (JSONL writer は成功、HTTP は warn only)。
- **同期 API**: caller が `threading.Thread` / `asyncio.to_thread` で
  逃がす。bridge 自体は時間軸を持たない。
- **task_id (UUID v4) 必須**: llmesh ingest endpoint の検証に合わせる
  ため、UUID v4 でない caller には例外を投げる (誤った publish を
  許さない fail-fast)。

llmesh ingest endpoint 側仕様: `D:/projects/llmesh/llmesh/mcp/server.py`
の `POST /timeline/ingest`.
"""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def _llove_logs_dir() -> Path:
    base = os.environ.get("LLIVE_DATA_DIR") or "D:/data/llive"
    return Path(base) / "logs" / "llove"


def _default_route_trace_path() -> Path:
    return _llove_logs_dir() / "route_trace.jsonl"


def _default_memory_link_path() -> Path:
    return _llove_logs_dir() / "memory_link.jsonl"


def _default_bwt_path() -> Path:
    return _llove_logs_dir() / "bwt.jsonl"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _gen_task_id() -> str:
    """UUID v4 を生成 (llmesh ingest の検証に通る形式)."""
    return str(uuid.uuid4())


def _is_valid_uuid4(task_id: str) -> bool:
    try:
        return uuid.UUID(task_id).version == 4
    except (ValueError, AttributeError):
        return False


_LOCK = threading.Lock()


def _append_jsonl(path: Path, payload: dict[str, Any]) -> Path:
    """Atomic-ish append. mkdir parents, single lock for cross-thread safety."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, default=str) + "\n")
    return path


def _push_to_ingest(
    event_type: str,
    *,
    task_id: str,
    node_id: str,
    metadata: dict[str, Any],
    url: str | None = None,
    timeout: float = 3.0,
) -> bool:
    """`POST {url}/timeline/ingest` する. 失敗は warn して False を返す.

    URL is taken from ``url`` arg or ``LLIVE_MCP_INGEST_URL`` env var.
    If neither is set, this function is a no-op returning ``False``.
    """
    resolved_url = url or os.environ.get("LLIVE_MCP_INGEST_URL", "").strip()
    if not resolved_url:
        return False
    full_url = resolved_url.rstrip("/") + "/timeline/ingest"
    body = json.dumps(
        {
            "task_id": task_id,
            "node_id": node_id,
            "event_type": event_type,
            "metadata": metadata,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        full_url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Node-Id": node_id,
        },
    )
    try:
        with urllib.request.urlopen(  # nosec B310 — URL is operator-supplied via env
            req, timeout=timeout
        ) as resp:
            return 200 <= int(resp.status) < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        # Best-effort; the JSONL file is the source of truth.
        return False


# ---------------------------------------------------------------------------
# Public bridge
# ---------------------------------------------------------------------------


@dataclass
class LoveBridge:
    """Configurable bridge instance. CLI / pipeline インスタンスから注入.

    Attributes
    ----------
    node_id
        ``llive-<instance>`` 形式の識別子。llmesh ingest で複数ソース
        分離に使われる。
    ingest_url
        ``LLIVE_MCP_INGEST_URL`` の override. ``None`` なら env 変数。
        empty string にすると push を完全に無効化する。
    logs_dir
        JSONL 出力ディレクトリ. ``None`` なら ``_llove_logs_dir()``.
    push_enabled
        ``False`` にすると JSONL 出力のみで push しない (test 用)。
    """

    node_id: str = "llive-default"
    ingest_url: str | None = None
    logs_dir: Path | None = None
    push_enabled: bool = True
    last_push_ok: bool = field(default=False, init=False)

    def _route_trace_path(self) -> Path:
        return (self.logs_dir or _llove_logs_dir()) / "route_trace.jsonl"

    def _memory_link_path(self) -> Path:
        return (self.logs_dir or _llove_logs_dir()) / "memory_link.jsonl"

    def _bwt_path(self) -> Path:
        return (self.logs_dir or _llove_logs_dir()) / "bwt.jsonl"

    # -------- emitters --------

    def emit_route_trace(
        self,
        *,
        container: str,
        subblocks: list[dict[str, Any]],
        memory_accesses: list[dict[str, Any]] | None = None,
        metrics: dict[str, float] | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Emit a route_trace event to JSONL (and optionally MCP ingest).

        Returns the payload that was written (for caller inspection).
        """
        if task_id is None:
            task_id = _gen_task_id()
        elif not _is_valid_uuid4(task_id):
            raise ValueError(f"task_id must be UUID v4, got: {task_id!r}")
        payload: dict[str, Any] = {
            "version": 1,
            "kind": "route_trace",
            "task_id": task_id,
            "node_id": self.node_id,
            "timestamp_utc": _utcnow_iso(),
            "container": container,
            "subblocks": subblocks,
            "memory_accesses": list(memory_accesses or []),
            "metrics": dict(metrics or {}),
        }
        _append_jsonl(self._route_trace_path(), payload)
        if self.push_enabled:
            self.last_push_ok = _push_to_ingest(
                "route_trace",
                task_id=task_id,
                node_id=self.node_id,
                metadata={
                    "version": 1,
                    "container": container,
                    "subblocks": subblocks,
                    "memory_accesses": list(memory_accesses or []),
                    "metrics": dict(metrics or {}),
                },
                url=self.ingest_url,
            )
        return payload

    def emit_concept_update(
        self,
        *,
        concept_id: str,
        title: str = "",
        page_type: str = "",
        linked_entry_ids: list[str] | None = None,
        linked_concept_ids: list[str] | None = None,
        surprise_stats: dict[str, float] | None = None,
        summary: str = "",
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Emit a concept_update event (memory link upsert)."""
        if not concept_id:
            raise ValueError("concept_id is required")
        if task_id is None:
            task_id = _gen_task_id()
        elif not _is_valid_uuid4(task_id):
            raise ValueError(f"task_id must be UUID v4, got: {task_id!r}")
        payload: dict[str, Any] = {
            "version": 1,
            "kind": "concept_update",
            "task_id": task_id,
            "node_id": self.node_id,
            "timestamp_utc": _utcnow_iso(),
            "concept_id": concept_id,
            "title": title or concept_id,
            "page_type": page_type,
            "linked_entry_ids": list(linked_entry_ids or []),
            "linked_concept_ids": list(linked_concept_ids or []),
            "surprise_stats": dict(surprise_stats or {}),
            "summary": summary,
        }
        _append_jsonl(self._memory_link_path(), payload)
        if self.push_enabled:
            self.last_push_ok = _push_to_ingest(
                "concept_update",
                task_id=task_id,
                node_id=self.node_id,
                metadata={
                    "version": 1,
                    "concept_id": concept_id,
                    "title": title or concept_id,
                    "page_type": page_type,
                    "linked_entry_ids": list(linked_entry_ids or []),
                    "linked_concept_ids": list(linked_concept_ids or []),
                    "surprise_stats": dict(surprise_stats or {}),
                    "summary": summary,
                },
                url=self.ingest_url,
            )
        return payload

    def emit_bwt_summary(
        self,
        *,
        bwt: float,
        avg_accuracy: float,
        n_tasks: int,
        per_task_drop: dict[str, float],
        diagonal: dict[str, float] | None = None,
        final: dict[str, float] | None = None,
        task_order: list[str] | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Emit a bwt_summary event.

        既存 ``BWTMeter.dump_jsonl`` (bwt.py) は別 path 命名規約 (kind
        フィールド無し) で書くので、bridge 経由は kind フィールド付きの
        spec-compliant フォーマットになる (`llove_jsonl_v1.md` 準拠)。
        """
        if task_id is None:
            task_id = _gen_task_id()
        elif not _is_valid_uuid4(task_id):
            raise ValueError(f"task_id must be UUID v4, got: {task_id!r}")
        payload: dict[str, Any] = {
            "version": 1,
            "kind": "bwt_summary",
            "task_id": task_id,
            "node_id": self.node_id,
            "timestamp_utc": _utcnow_iso(),
            "task_order": list(task_order or []),
            "n_tasks": int(n_tasks),
            "bwt": float(bwt),
            "avg_accuracy": float(avg_accuracy),
            "per_task_drop": dict(per_task_drop),
            "diagonal": dict(diagonal or {}),
            "final": dict(final or {}),
        }
        _append_jsonl(self._bwt_path(), payload)
        if self.push_enabled:
            self.last_push_ok = _push_to_ingest(
                "bwt_summary",
                task_id=task_id,
                node_id=self.node_id,
                metadata={
                    "version": 1,
                    "task_order": list(task_order or []),
                    "n_tasks": int(n_tasks),
                    "bwt": float(bwt),
                    "avg_accuracy": float(avg_accuracy),
                    "per_task_drop": dict(per_task_drop),
                    "diagonal": dict(diagonal or {}),
                    "final": dict(final or {}),
                },
                url=self.ingest_url,
            )
        return payload


__all__ = [
    "LoveBridge",
]
