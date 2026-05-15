# SPDX-License-Identifier: Apache-2.0
"""structlog-based JSON logging with context binding (Phase 1)."""

from __future__ import annotations

import logging
import os
import sys

import structlog

_CONFIGURED = False


def configure_logging(level: str | None = None, json_stream=None) -> None:
    """Configure structlog once. Subsequent calls are no-ops."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_level_name = (level or os.environ.get("LLIVE_LOG_LEVEL") or "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    stream = json_stream if json_stream is not None else sys.stderr
    logging.basicConfig(
        level=log_level,
        stream=stream,
        format="%(message)s",
    )

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=stream),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    configure_logging()
    return structlog.get_logger(name)
