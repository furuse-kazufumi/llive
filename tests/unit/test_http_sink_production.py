# SPDX-License-Identifier: Apache-2.0
"""ProductionHttpTimelineSink テスト — auth / retry / batch."""

from __future__ import annotations

import urllib.error

import pytest

from llive.cognitive_mesh.http_sink import (
    ENV_TIMELINE_BATCH_SIZE,
    ENV_TIMELINE_RETRIES,
    ENV_TIMELINE_TOKEN,
    ENV_TIMELINE_URL,
    ProductionHttpTimelineSink,
    production_http_sink_from_env,
)


def _resp(status: int = 200):
    class _R:
        def __init__(self) -> None:
            self.status = status

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def read(self) -> bytes:
            return b""

    return _R()


def _no_sleep(_seconds: float) -> None:
    pass


# ---------------------------------------------------------------------------
# auth header
# ---------------------------------------------------------------------------


def test_production_sink_bearer_auth_header(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[dict] = []

    def _fake(req, timeout):  # noqa: ANN001, ARG001
        captured.append(dict(req.header_items()))
        return _resp(200)

    monkeypatch.setattr("urllib.request.urlopen", _fake)
    sink = ProductionHttpTimelineSink(
        url="http://x", auth_token="secret-token", _sleep=_no_sleep,
    )
    sink.push({"event_id": "e", "event_type": "cog_risk_alert"})
    headers = {k.lower(): v for k, v in captured[0].items()}
    assert headers.get("authorization") == "Bearer secret-token"


def test_production_sink_no_auth_when_token_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict] = []

    def _fake(req, timeout):  # noqa: ANN001, ARG001
        captured.append(dict(req.header_items()))
        return _resp(200)

    monkeypatch.setattr("urllib.request.urlopen", _fake)
    sink = ProductionHttpTimelineSink(url="http://x", _sleep=_no_sleep)
    sink.push({"event_id": "e", "event_type": "cog_risk_alert"})
    headers = {k.lower(): v for k, v in captured[0].items()}
    assert "authorization" not in headers


# ---------------------------------------------------------------------------
# retry / backoff
# ---------------------------------------------------------------------------


def test_production_sink_retries_on_url_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """3 回 URLError → 4 回目で成功"""
    attempts = {"n": 0}

    def _fake(req, timeout):  # noqa: ANN001, ARG001
        attempts["n"] += 1
        if attempts["n"] < 4:
            raise urllib.error.URLError("flaky")
        return _resp(200)

    monkeypatch.setattr("urllib.request.urlopen", _fake)
    sleep_calls: list[float] = []
    sink = ProductionHttpTimelineSink(
        url="http://x", retries=3, _sleep=lambda s: sleep_calls.append(s),
    )
    sink.push({"event_id": "e", "event_type": "cog_risk_alert"})
    assert attempts["n"] == 4
    assert sink.success_count == 1
    assert sink.failure_count == 0
    assert sink.retry_count == 3
    # backoff 0.1, 0.2, 0.4 秒
    assert sleep_calls == [0.1, 0.2, 0.4]


def test_production_sink_gives_up_after_max_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """全 attempt 失敗で failure_count++."""

    def _fake(req, timeout):  # noqa: ANN001, ARG001
        raise urllib.error.URLError("dead")

    monkeypatch.setattr("urllib.request.urlopen", _fake)
    sink = ProductionHttpTimelineSink(
        url="http://x", retries=2, _sleep=_no_sleep,
    )
    sink.push({"event_id": "e", "event_type": "cog_risk_alert"})
    assert sink.success_count == 0
    assert sink.failure_count == 1
    assert sink.retry_count == 2  # 2 回 backoff した後諦め


def test_production_sink_retries_on_5xx(monkeypatch: pytest.MonkeyPatch) -> None:
    """5xx も retry 対象."""
    seq = [500, 502, 200]
    idx = {"i": 0}

    def _fake(req, timeout):  # noqa: ANN001, ARG001
        s = seq[idx["i"]]
        idx["i"] += 1
        return _resp(s)

    monkeypatch.setattr("urllib.request.urlopen", _fake)
    sink = ProductionHttpTimelineSink(
        url="http://x", retries=3, _sleep=_no_sleep,
    )
    sink.push({"event_id": "e", "event_type": "cog_risk_alert"})
    assert sink.success_count == 1
    assert sink.retry_count == 2


# ---------------------------------------------------------------------------
# batch
# ---------------------------------------------------------------------------


def test_production_sink_batch_buffers_until_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"n": 0}

    def _fake(req, timeout):  # noqa: ANN001, ARG001
        calls["n"] += 1
        return _resp(200)

    monkeypatch.setattr("urllib.request.urlopen", _fake)
    sink = ProductionHttpTimelineSink(
        url="http://x", batch_size=3, _sleep=_no_sleep,
    )
    sink.push({"event_id": "1", "event_type": "cog_risk_alert"})
    sink.push({"event_id": "2", "event_type": "cog_risk_alert"})
    assert calls["n"] == 0  # まだ flush されない
    sink.push({"event_id": "3", "event_type": "cog_risk_alert"})
    # batch_size=3 で auto flush
    assert calls["n"] == 3
    assert sink.success_count == 3


def test_production_sink_manual_flush_drains_buffer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"n": 0}

    def _fake(req, timeout):  # noqa: ANN001, ARG001
        calls["n"] += 1
        return _resp(200)

    monkeypatch.setattr("urllib.request.urlopen", _fake)
    sink = ProductionHttpTimelineSink(
        url="http://x", batch_size=10, _sleep=_no_sleep,
    )
    for i in range(3):
        sink.push({"event_id": str(i), "event_type": "cog_risk_alert"})
    assert calls["n"] == 0  # batch=10 でまだ未 flush
    sink.flush()
    assert calls["n"] == 3
    assert sink.success_count == 3


def test_production_sink_batch_zero_means_immediate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"n": 0}

    def _fake(req, timeout):  # noqa: ANN001, ARG001
        calls["n"] += 1
        return _resp(200)

    monkeypatch.setattr("urllib.request.urlopen", _fake)
    sink = ProductionHttpTimelineSink(
        url="http://x", batch_size=0, _sleep=_no_sleep,
    )
    sink.push({"event_id": "1", "event_type": "cog_risk_alert"})
    assert calls["n"] == 1


# ---------------------------------------------------------------------------
# production_http_sink_from_env
# ---------------------------------------------------------------------------


def test_production_factory_returns_none_without_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ENV_TIMELINE_URL, raising=False)
    assert production_http_sink_from_env() is None


def test_production_factory_reads_all_envs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_TIMELINE_URL, "http://x:8080")
    monkeypatch.setenv(ENV_TIMELINE_TOKEN, "tok-abc")
    monkeypatch.setenv(ENV_TIMELINE_RETRIES, "5")
    monkeypatch.setenv(ENV_TIMELINE_BATCH_SIZE, "7")
    sink = production_http_sink_from_env(node_id="n1")
    assert sink is not None
    assert sink.url == "http://x:8080"
    assert sink.auth_token == "tok-abc"
    assert sink.retries == 5
    assert sink.batch_size == 7
    assert sink.node_id == "n1"


def test_production_factory_falls_back_to_defaults_on_bad_int(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_TIMELINE_URL, "http://x")
    monkeypatch.setenv(ENV_TIMELINE_RETRIES, "not-int")
    monkeypatch.setenv(ENV_TIMELINE_BATCH_SIZE, "?")
    sink = production_http_sink_from_env()
    assert sink is not None
    assert sink.retries == 3  # default
    assert sink.batch_size == 0  # default


def test_production_factory_negative_clamps_to_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_TIMELINE_URL, "http://x")
    monkeypatch.setenv(ENV_TIMELINE_RETRIES, "-5")
    monkeypatch.setenv(ENV_TIMELINE_BATCH_SIZE, "-1")
    sink = production_http_sink_from_env()
    assert sink is not None
    assert sink.retries == 0
    assert sink.batch_size == 0
