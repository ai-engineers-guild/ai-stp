"""Shared server runtime: async database, the custom job queue and readiness.

Owns the queue schema and reusable persistence primitives for both apps/api and
apps/worker. Normative sources: SPEC-017, SPEC-018, ADR-0037, ADR-0038.
"""

from ai_stp_platform.db import Base, make_engine, make_sessionmaker
from ai_stp_platform.readiness import not_ready, readiness_report
from ai_stp_platform.settings import DatabaseSettings, StorageSettings

__all__ = [
    "Base",
    "DatabaseSettings",
    "StorageSettings",
    "make_engine",
    "make_sessionmaker",
    "not_ready",
    "readiness_report",
]
