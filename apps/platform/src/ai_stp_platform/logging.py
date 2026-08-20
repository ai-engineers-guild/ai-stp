"""Structured logging shared by api and worker (ADR-0039).

Emits JSON to a daily-rotated file and to stdout. Fields are limited to a closed
set and tokens/PII are never logged (SPEC-013). The file rotates at midnight.
"""

from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import structlog

_LOG_FILE = "ai_stp.log"
_ROTATION_BACKUP_DAYS = 14


def configure_logging(log_dir: Path) -> None:
    """Configure structlog to emit JSON to a daily file and to stdout."""
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = TimedRotatingFileHandler(
        log_dir / _LOG_FILE,
        when="midnight",
        backupCount=_ROTATION_BACKUP_DAYS,
        encoding="utf-8",
        utc=True,
    )
    stream_handler = logging.StreamHandler()

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(stream_handler)
    root.setLevel(logging.INFO)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound structured logger."""
    return structlog.get_logger(name)
