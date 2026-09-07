"""Closed structured events shared by API and worker (ADR-0039, SPEC-017)."""

from __future__ import annotations

import logging
import re
import sys
from datetime import UTC, datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

import structlog
from structlog.types import EventDict

_LOG_FILE = "ai_stp.log"
_ROTATION_BACKUP_DAYS = 14
_ALLOWED_FIELDS = frozenset(
    {
        "event",
        "level",
        "timestamp",
        "logger",
        "request_id",
        "trace_id",
        "artifacts_written",
        "attempt",
        "batch_size",
        "cache_hit",
        "catalog_checked",
        "catalog_indexed",
        "catalog_unreadable",
        "claimed_count",
        "code",
        "created_accounts",
        "created_versions",
        "duration_ms",
        "environment",
        "error_type",
        "first_party_seeded",
        "fixtures_seeded",
        "job_id",
        "job_type",
        "locale",
        "metric",
        "object_kind",
        "official_manifest_entries",
        "outcome_count",
        "profile",
        "provider",
        "reason",
        "requeued",
        "reused_versions",
        "sandbox_mode",
        "stable_id",
        "subject_id",
        "subject_kind",
        "version",
        "wall_ms",
        "worker_id",
    }
)
_SENSITIVE_TEXT = re.compile(
    r"https?://|[\w.+-]+@[\w.-]+|(?:bearer|token|password|secret|cookie|authorization)\s*[:= ]",
    re.I,
)
_EVENT_NAME = re.compile(r"[a-z][a-z0-9_]{0,95}\Z")


def _safe_event(_logger: object, _method: str, event: EventDict) -> EventDict:
    """Unknown fields, free-form exception messages and nested payloads never reach a sink."""
    if not event.get("_from_structlog", True):
        record = event.get("_record")
        event["event"] = "external_log"
        if isinstance(record, logging.LogRecord) and record.exc_info:
            event["error_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
    raw_error = event.get("error")
    if isinstance(raw_error, str):
        candidate = raw_error.split(":", 1)[0]
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:Error|Exception)", candidate):
            event["error_type"] = candidate
    clean: dict[str, Any] = {}
    for key, value in event.items():
        if key not in _ALLOWED_FIELDS or not isinstance(value, (str, int, float, bool, type(None))):
            continue
        if isinstance(value, str):
            if key == "event" and not _EVENT_NAME.fullmatch(value):
                value = "invalid_log_event"
            elif _SENSITIVE_TEXT.search(value):
                value = "[redacted]"
            else:
                value = value[:256]
        clean[key] = value
    return clean


def _record_timestamp(_logger: object, _method: str, event: EventDict) -> EventDict:
    record = event.get("_record")
    if isinstance(record, logging.LogRecord):
        event["timestamp"] = datetime.fromtimestamp(record.created, UTC).isoformat()
    return event


def configure_logging(log_dir: Path) -> None:
    """Route the same sanitized JSON through the daily file and stdout handlers."""
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[
            structlog.stdlib.add_logger_name,
            structlog.processors.add_log_level,
            _record_timestamp,
        ],
        processors=[_safe_event, structlog.processors.JSONRenderer()],
    )
    file_handler = TimedRotatingFileHandler(
        log_dir / _LOG_FILE,
        when="midnight",
        backupCount=_ROTATION_BACKUP_DAYS,
        encoding="utf-8",
        utc=True,
    )
    stream_handler = logging.StreamHandler(sys.stdout)
    root = logging.getLogger()
    for handler in tuple(root.handlers):
        if handler.get_name() == "ai_stp":
            root.removeHandler(handler)
            handler.close()
    for handler in (file_handler, stream_handler):
        handler.set_name("ai_stp")
        handler.setFormatter(formatter)
        root.addHandler(handler)
    root.setLevel(logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound structured logger."""
    return structlog.get_logger(name)
