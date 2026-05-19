# SPDX-License-Identifier: Apache-2.0
"""COG-MESH M8.1 — HTTP TimelineSink (skeleton + production).

`TimelineSink` Protocol の HTTP 実装。stdlib `urllib.request` ベースで
依存ゼロ。`llive.observability.llove_bridge._post_to_llmesh` と同じ
endpoint 仕様 (`POST {url}/timeline/ingest` JSON body) に揃える.

2 段提供:
- ``HttpTimelineSink`` — 1 event 1 POST、retry / auth なしの skeleton.
- ``ProductionHttpTimelineSink`` — bearer auth + exponential backoff
  retry + batch (1 event 1 POST だが内部 batch buffer で逐次 push).

設計:
- best-effort: HTTP 失敗時は silent (sink Protocol 上 push は戻り値なし).
- URL は constructor 引数 or env から解決.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

_logger = logging.getLogger("llive.cognitive_mesh.http_sink")

# llive.observability.llove_bridge と同じ endpoint
_INGEST_PATH = "/timeline/ingest"

# env 変数 (llove_bridge と命名揃え)
ENV_TIMELINE_URL = "LLIVE_LLMESH_TIMELINE_URL"
ENV_TIMELINE_TOKEN = "LLIVE_LLMESH_TIMELINE_TOKEN"
ENV_TIMELINE_RETRIES = "LLIVE_LLMESH_TIMELINE_RETRIES"
ENV_TIMELINE_BATCH_SIZE = "LLIVE_LLMESH_TIMELINE_BATCH_SIZE"


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


# ---------------------------------------------------------------------------
# ProductionHttpTimelineSink — auth / retry / batch (Phase 6 wire 用)
# ---------------------------------------------------------------------------


def _exp_backoff_seconds(attempt: int, base: float = 0.1, cap: float = 5.0) -> float:
    """attempt=0..N で 0.1s, 0.2s, 0.4s, ... と倍々 (cap で 5s 上限)."""
    return min(cap, base * (2 ** attempt))


@dataclass
class ProductionHttpTimelineSink:
    """auth header + exponential backoff retry + batch buffer 付き HTTP sink.

    Attributes:
        url: llmesh ベース URL.
        timeout: 1 POST タイムアウト秒.
        node_id: ``X-Node-Id`` ヘッダ既定値.
        auth_token: Bearer auth 用 (None なら header を付けない).
        retries: 失敗時の最大リトライ回数 (1 回失敗で +1, 既定 3).
        batch_size: flush() で 1 度に push する event 数の上限. 0 なら
            push() の度に即時 POST (batch 無効).
        success_count: 成功 push 累計.
        failure_count: 失敗 push 累計 (リトライ全て failed のときカウント).
        retry_count: 実際に backoff を挟んでリトライした回数.
        _buffer: batch_size > 0 のときの未送信 buffer.
        _sleep: time.sleep を差し替え可能にする (テスト用).
    """

    url: str
    timeout: float = 5.0
    node_id: str = ""
    auth_token: str | None = None
    retries: int = 3
    batch_size: int = 0
    success_count: int = 0
    failure_count: int = 0
    retry_count: int = 0
    _buffer: list[dict[str, Any]] = field(default_factory=list)
    _sleep: Any = field(default=time.sleep, repr=False)

    def push(self, event: dict[str, Any]) -> None:
        if self.batch_size > 0:
            self._buffer.append(event)
            if len(self._buffer) >= self.batch_size:
                self.flush()
            return
        # batch 無効: 即時送信
        self._post_with_retry(event)

    def flush(self) -> None:
        """buffer に貯まった event を順次 POST. 例外で残りを止めない."""
        pending = list(self._buffer)
        self._buffer.clear()
        for event in pending:
            self._post_with_retry(event)

    def _build_request(self, event: dict[str, Any]) -> urllib.request.Request:
        full_url = self.url.rstrip("/") + _INGEST_PATH
        body = json.dumps(event).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-Node-Id": self.node_id or event.get("node_id", ""),
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return urllib.request.Request(full_url, data=body, method="POST", headers=headers)

    def _post_with_retry(self, event: dict[str, Any]) -> None:
        for attempt in range(self.retries + 1):
            req = self._build_request(event)
            try:
                with urllib.request.urlopen(  # nosec B310 — operator URL
                    req, timeout=self.timeout
                ) as resp:
                    if 200 <= int(resp.status) < 300:
                        self.success_count += 1
                        return
                    # non-2xx — retry 対象 (5xx だけにしたいが API spec 未確定)
                    _logger.debug(
                        "ProductionHttpTimelineSink: non-2xx (%s), attempt=%d",
                        resp.status, attempt,
                    )
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                _logger.debug(
                    "ProductionHttpTimelineSink: POST failed: %s, attempt=%d",
                    exc, attempt,
                )
            # backoff (最終 attempt の後は sleep しない)
            if attempt < self.retries:
                self.retry_count += 1
                self._sleep(_exp_backoff_seconds(attempt))
        # 全 attempt 失敗
        self.failure_count += 1


def production_http_sink_from_env(
    *,
    timeout: float = 5.0,
    node_id: str = "",
    sleep_fn: Any = None,
) -> ProductionHttpTimelineSink | None:
    """env から URL / token / retries / batch_size を解決して生成.

    Returns:
        URL 未設定なら ``None``. それ以外は ProductionHttpTimelineSink.

    env:
        - ``LLIVE_LLMESH_TIMELINE_URL`` — base URL (必須)
        - ``LLIVE_LLMESH_TIMELINE_TOKEN`` — Bearer auth (任意)
        - ``LLIVE_LLMESH_TIMELINE_RETRIES`` — 既定 3
        - ``LLIVE_LLMESH_TIMELINE_BATCH_SIZE`` — 既定 0 (batch 無効)
    """
    url = os.environ.get(ENV_TIMELINE_URL, "").strip()
    if not url:
        return None
    token = os.environ.get(ENV_TIMELINE_TOKEN, "").strip() or None
    retries_raw = os.environ.get(ENV_TIMELINE_RETRIES, "3").strip()
    batch_raw = os.environ.get(ENV_TIMELINE_BATCH_SIZE, "0").strip()
    try:
        retries = max(0, int(retries_raw))
    except ValueError:
        retries = 3
    try:
        batch_size = max(0, int(batch_raw))
    except ValueError:
        batch_size = 0
    kwargs: dict[str, Any] = {}
    if sleep_fn is not None:
        kwargs["_sleep"] = sleep_fn
    return ProductionHttpTimelineSink(
        url=url,
        timeout=timeout,
        node_id=node_id,
        auth_token=token,
        retries=retries,
        batch_size=batch_size,
        **kwargs,
    )


__all__ = [
    "ENV_TIMELINE_BATCH_SIZE",
    "ENV_TIMELINE_RETRIES",
    "ENV_TIMELINE_TOKEN",
    "ENV_TIMELINE_URL",
    "HttpTimelineSink",
    "ProductionHttpTimelineSink",
    "http_sink_from_env",
    "production_http_sink_from_env",
]
