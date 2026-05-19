# SPDX-License-Identifier: Apache-2.0
"""COG-MESH M8.1 — HTTP TimelineSink skeleton.

`TimelineSink` Protocol の HTTP 実装。stdlib `urllib.request` ベースで
依存ゼロ。`llive.observability.llove_bridge._post_to_llmesh` と同じ
endpoint 仕様 (`POST {url}/timeline/ingest` JSON body) に揃える.

設計:
- best-effort: HTTP 失敗時は silent (sink Protocol 上 push は戻り値なし).
- URL は constructor 引数 or env `LLIVE_LLMESH_TIMELINE_URL` から解決.
- Phase 6 で実 production wire 込み。本 skeleton は contract verification
  と shape 確認まで.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

_logger = logging.getLogger("llive.cognitive_mesh.http_sink")

# llive.observability.llove_bridge と同じ endpoint
_INGEST_PATH = "/timeline/ingest"

# env 変数 (llove_bridge と命名揃え)
ENV_TIMELINE_URL = "LLIVE_LLMESH_TIMELINE_URL"


@dataclass
class HttpTimelineSink:
    """HTTP POST で llmesh Timeline server に event を流す sink.

    Attributes:
        url: llmesh のベース URL (例 ``http://localhost:8080``).
            末尾の ``/timeline/ingest`` は自動付与.
        timeout: POST タイムアウト秒数 (既定 5.0).
        node_id: ``X-Node-Id`` ヘッダに乗せる識別子.
        success_count: 成功 push 回数 (テスト / 監査用).
        failure_count: 失敗 push 回数.
    """

    url: str
    timeout: float = 5.0
    node_id: str = ""
    success_count: int = 0
    failure_count: int = 0

    def push(self, event: dict[str, Any]) -> None:
        full_url = self.url.rstrip("/") + _INGEST_PATH
        body = json.dumps(event).encode("utf-8")
        req = urllib.request.Request(
            full_url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Node-Id": self.node_id or event.get("node_id", ""),
            },
        )
        try:
            with urllib.request.urlopen(  # nosec B310 — URL is operator-supplied via env
                req, timeout=self.timeout
            ) as resp:
                if 200 <= int(resp.status) < 300:
                    self.success_count += 1
                else:
                    self.failure_count += 1
                    _logger.debug(
                        "HttpTimelineSink: non-2xx response: %s", resp.status
                    )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            self.failure_count += 1
            _logger.debug("HttpTimelineSink: POST failed: %s", exc)


def http_sink_from_env(
    *,
    timeout: float = 5.0,
    node_id: str = "",
) -> HttpTimelineSink | None:
    """env から URL を解決して HttpTimelineSink を生成 (factory).

    Returns:
        ``LLIVE_LLMESH_TIMELINE_URL`` 設定済なら ``HttpTimelineSink``,
        未設定なら ``None`` (caller は InMemoryTimelineSink で代替推奨).
    """
    url = os.environ.get(ENV_TIMELINE_URL, "").strip()
    if not url:
        return None
    return HttpTimelineSink(url=url, timeout=timeout, node_id=node_id)


__all__ = [
    "ENV_TIMELINE_URL",
    "HttpTimelineSink",
    "http_sink_from_env",
]
