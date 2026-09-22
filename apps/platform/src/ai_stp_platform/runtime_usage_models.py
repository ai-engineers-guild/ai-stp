"""Corporate runtime component-usage persistence (SPEC-088).

`runtime_usage_event` holds the closed coordinate-only event set the provider
adapter is the only sender of. `runtime_usage_export` holds bounded, digested
export receipts so a privileged read leaves a durable trace. Neither table
carries payloads: prompts, arguments, model output, paths, and secrets have no
column to land in.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ai_stp_platform.db import Base


class RuntimeUsageEvent(Base):
    """One deduplicated component-invocation fact inside one tenant."""

    __tablename__ = "runtime_usage_event"
    __table_args__ = (
        PrimaryKeyConstraint("organization_id", "event_id"),
        CheckConstraint("length(event_id) >= 8", name="ck_runtime_usage_event_id"),
        CheckConstraint(
            "outcome in ('succeeded','failed','cancelled')",
            name="ck_runtime_usage_event_outcome",
        ),
        CheckConstraint(
            "component_kind in "
            "('instruction','skill','mcp','hook','command','agent','plugin','setting','cli')",
            name="ck_runtime_usage_event_component_kind",
        ),
        CheckConstraint("schema_version >= 1", name="ck_runtime_usage_event_schema"),
        Index("ix_runtime_usage_event_invoked", "organization_id", "invoked_at"),
        Index(
            "ix_runtime_usage_event_employee",
            "organization_id",
            "employee_account_id",
            "invoked_at",
        ),
        Index(
            "ix_runtime_usage_event_component",
            "organization_id",
            "component_stable_id",
            "component_version",
        ),
        Index(
            "ix_runtime_usage_event_setup",
            "organization_id",
            "setup_stable_id",
            "setup_version",
        ),
    )

    event_id: Mapped[str] = mapped_column(String(80), nullable=False)
    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    employee_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    harness: Mapped[str] = mapped_column(String(64), nullable=False)
    setup_stable_id: Mapped[str] = mapped_column(String(128), nullable=False)
    setup_version: Mapped[str] = mapped_column(String(32), nullable=False)
    setup_passport_digest: Mapped[str] = mapped_column(String(80), nullable=False)
    component_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    component_stable_id: Mapped[str] = mapped_column(String(128), nullable=False)
    component_version: Mapped[str] = mapped_column(String(32), nullable=False)
    component_passport_digest: Mapped[str] = mapped_column(String(80), nullable=False)
    invoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RuntimeUsageExport(Base):
    """A durable receipt for one bounded, auditable report export."""

    __tablename__ = "runtime_usage_export"
    __table_args__ = (
        PrimaryKeyConstraint("organization_id", "id"),
        CheckConstraint("state in ('completed')", name="ck_runtime_usage_export_state"),
        CheckConstraint("row_count >= 0", name="ck_runtime_usage_export_rows"),
        Index(
            "uq_runtime_usage_export_idempotency",
            "organization_id",
            "idempotency_key",
            unique=True,
        ),
        Index("ix_runtime_usage_export_created", "organization_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), nullable=False)
    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    requested_by: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    filters: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_digest: Mapped[str] = mapped_column(String(80), nullable=False)
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="completed", server_default="completed"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


__all__ = ["RuntimeUsageEvent", "RuntimeUsageExport"]
