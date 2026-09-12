"""ORM entity for the job queue (SPEC-018 REQ-1801).

Kept separate from the API DTOs and from any domain entity per ADR-0037: this
class only maps the table and never leaves the storage layer.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from ai_stp_platform.db import Base
from ai_stp_platform.organization_scope import OrganizationScopedMixin
from ai_stp_platform.queue.states import JobState


class Job(OrganizationScopedMixin, Base):
    """A single unit of background work with its own state and retry accounting."""

    __tablename__ = "job"
    __table_args__ = (
        Index(
            "uq_job_tenant_idempotency",
            "organization_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("organization_id IS NOT NULL"),
            sqlite_where=text("organization_id IS NOT NULL"),
        ),
        Index(
            "uq_job_global_idempotency",
            "idempotency_key",
            unique=True,
            postgresql_where=text("organization_id IS NULL"),
            sqlite_where=text("organization_id IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    state: Mapped[str] = mapped_column(String(32), default=JobState.QUEUED, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(255))
    priority: Mapped[int] = mapped_column(Integer, default=0)
    locked_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
