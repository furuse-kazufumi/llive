# SPDX-License-Identifier: Apache-2.0
"""M8.1 HTTP TimelineSink テスト — monkeypatch で urlopen を fake."""

from __future__ import annotations

import io
import urllib.error
from contextlib import contextmanager

import pytest

from llive.cognitive_mesh.http_sink import (
    ENV_TIMELINE_URL,
    HttpTimelineSink,
    http_sink_from_env,
)


def _make_fake_resp(status: int = 200):
    class _Resp:
        def __init__(self) -> None:
            self.status = status

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def read(self) -> bytes:
            return b""

    return _Resp()


def test_http_sink_push_success(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[str, bytes, dict]] = []

    def _fake_urlopen(req, timeout):  # noqa: ANN001, ARG001
        sent.append((req.full_url, req.data, dict(req.header_items())))
        return _make_fake_resp(200)

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    sink = HttpTimelineSink(url="http://localhost:8080", node_id="n1")
    sink.push({"event_id": "e1", "event_type": "cog_risk_alert"})
    assert sink.success_count == 1
    assert sink.failure_count == 0
    assert len(sent) == 1
    url, body, headers = sent[0]
    assert url == "http://localhost:8080/timeline/ingest"
    assert b'"event_id": "e1"' in body
    # ヘッダ name は環境 (urllib) で title-case される
    header_pairs = {k.lower(): v for k, v in headers.items()}
    assert header_pairs.get("content-type") == "application/json"
    assert header_pairs.get("x-node-id") == "n1"


def test_http_sink_url_trailing_slash_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []

    def _fake_urlopen(req, timeout):  # noqa: ANN001, ARG001
        captured.append(req.full_url)
        return _make_fake_resp(200)

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    sink = HttpTimelineSink(url="http://localhost:8080//")
    sink.push({"event_id": "e", "event_type": "cog_risk_alert"})
    assert captured[0] == "http://localhost:8080/timeline/ingest"


def test_http_sink_5xx_marks_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_urlopen(req, timeout):  # noqa: ANN001, ARG001
        return _make_fake_resp(500)

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    sink = HttpTimelineSink(url="http://x")
    sink.push({"event_id": "e", "event_type": "cog_risk_alert"})
    assert sink.success_count == 0
    assert sink.failure_count == 1


def test_http_sink_url_error_is_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_urlopen(req, timeout):  # noqa: ANN001, ARG001
        raise urllib.error.URLError("nope")

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    sink = HttpTimelineSink(url="http://x")
    # 例外で本体を止めない (silent)
    sink.push({"event_id": "e", "event_type": "cog_risk_alert"})
    assert sink.success_count == 0
    assert sink.failure_count == 1


def test_http_sink_timeout_is_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_urlopen(req, timeout):  # noqa: ANN001, ARG001
        raise TimeoutError("slow")

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    sink = HttpTimelineSink(url="http://x")
    sink.push({"event_id": "e", "event_type": "cog_risk_alert"})
    assert sink.failure_count == 1


def test_http_sink_node_id_from_event_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """sink.node_id が空なら event[node_id] を fallback で使う."""
    captured: list[dict] = []

    def _fake_urlopen(req, timeout):  # noqa: ANN001, ARG001
        captured.append(dict(req.header_items()))
        return _make_fake_resp(200)

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    sink = HttpTimelineSink(url="http://x", node_id="")
    sink.push({"event_id": "e", "event_type": "cog_risk_alert", "node_id": "from-ev"})
    h = {k.lower(): v for k, v in captured[0].items()}
    assert h.get("x-node-id") == "from-ev"


def test_http_sink_from_env_returns_none_without_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ENV_TIMELINE_URL, raising=False)
    assert http_sink_from_env() is None


def test_http_sink_from_env_returns_sink_when_url_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_TIMELINE_URL, "http://localhost:9999")
    sink = http_sink_from_env(node_id="node-x", timeout=2.5)
    assert isinstance(sink, HttpTimelineSink)
    assert sink.url == "http://localhost:9999"
    assert sink.node_id == "node-x"
    assert sink.timeout == 2.5


def test_http_sink_from_env_strips_whitespace_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_TIMELINE_URL, "  http://x  ")
    sink = http_sink_from_env()
    assert sink is not None
    assert sink.url == "http://x"
