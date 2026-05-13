"""observability/logging.py - structlog setup helpers."""

from __future__ import annotations

import io

from llive.observability import logging as _llog


def _reset():
    _llog._CONFIGURED = False


def test_configure_logging_runs(monkeypatch):
    monkeypatch.setenv("LLIVE_LOG_LEVEL", "DEBUG")
    _reset()
    buf = io.StringIO()
    _llog.configure_logging(json_stream=buf)
    assert _llog._CONFIGURED is True


def test_configure_logging_idempotent():
    _reset()
    _llog.configure_logging()
    # second call returns immediately
    _llog.configure_logging()
    assert _llog._CONFIGURED is True


def test_configure_logging_with_explicit_level():
    _reset()
    _llog.configure_logging(level="WARNING")
    assert _llog._CONFIGURED is True


def test_configure_logging_unknown_level_falls_back_to_info():
    _reset()
    _llog.configure_logging(level="NOT_A_LEVEL")
    assert _llog._CONFIGURED is True


def test_get_logger_returns_bound_logger():
    _reset()
    log = _llog.get_logger("test-module")
    assert log is not None
    log.info("hello")  # should not raise
