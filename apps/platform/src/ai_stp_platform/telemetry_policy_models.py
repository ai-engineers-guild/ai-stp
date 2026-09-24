"""Tenant-scoped telemetry governance tables (SPEC-089, ADR-0203).

Every column is enumerable: no column can hold a prompt, payload, credential,
local path, or repository byte. The pinned seam names are `telemetry_event`,
`telemetry_policy`, `telemetry_revocation`, and `telemetry_audit`; heartbeat
(`installation_heartbeat`) and usage (`runtime_usage_event`) streams own their
own raw tables and reuse the same governance helpers at integration.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from ai_stp_contracts.heartbeat import (
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_HEARTBEAT_RETRY_BASE_SECONDS,
    DEFAULT_HEARTBEAT_RETRY_MAX_SECONDS,
    DEFAULT_HEARTBEAT_STALE_AFTER_SECONDS,
)
from ai_stp_platform.db import Base

TELEMETRY_GOVERNED_TABLES: tuple[str, ...] = (
    "telemetry_event",
    "telemetry_policy",
    "telemetry_revocation",
    "telemetry_audit",
)


class TelemetryEvent(Base):
    """One retained corporate telemetry event with bounded columns."""

    __tablename__ = "telemetry_event"
    __table_args__ = (
        CheckConstraint("kind in ('heartbeat','invocation')", name="ck_telemetry_event_kind"),
        CheckConstraint(
            "health is null or health in ('active','stale','failing','disabled','unknown')",
            name="ck_telemetry_event_health",
        ),
        CheckConstraint(
            "outcome is null or outcome in ('succeeded','failed','denied','unknown')",
            name="ck_telemetry_event_outcome",
        ),
        CheckConstraint(
            "subject_state in ('active','anonymized')",
            name="ck_telemetry_event_subject_state",
        ),
    )

    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="RESTRICT"), primary_key=True
    )
    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    account_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    harness: Mapped[str] = mapped_column(String(64))
    harness_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    capabilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    health: Mapped[str | None] = mapped_column(String(16), nullable=True)
    setup_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    component_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    component_stable_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    component_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)
    subject_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TelemetryPolicy(Base):
    """Per-tenant retention, notice, and legal-basis telemetry policy."""

    __tablename__ = "telemetry_policy"
    __table_args__ = (
        CheckConstraint(
            "raw_retention_days between 1 and 3650", name="ck_telemetry_policy_raw_retention"
        ),
        CheckConstraint(
            "aggregate_retention_days between 1 and 3650",
            name="ck_telemetry_policy_aggregate_retention",
        ),
        CheckConstraint(
            "legal_basis in ('consent','contract','legitimate_interest')",
            name="ck_telemetry_policy_basis",
        ),
        CheckConstraint("notice_revision >= 0", name="ck_telemetry_policy_notice"),
        CheckConstraint("policy_version >= 1", name="ck_telemetry_policy_version"),
        CheckConstraint(
            "heartbeat_interval_seconds between 300 and 2592000",
            name="ck_telemetry_policy_heartbeat_interval",
        ),
        CheckConstraint(
            "heartbeat_retry_base_seconds between 30 and 86400",
            name="ck_telemetry_policy_heartbeat_retry_base",
        ),
        CheckConstraint(
            "heartbeat_retry_max_seconds between 60 and 604800",
            name="ck_telemetry_policy_heartbeat_retry_max",
        ),
        CheckConstraint(
            "heartbeat_retry_max_seconds >= heartbeat_retry_base_seconds",
            name="ck_telemetry_policy_heartbeat_retry_order",
        ),
        CheckConstraint(
            "heartbeat_stale_after_seconds between 60 and 31536000",
            name="ck_telemetry_policy_heartbeat_stale_after",
        ),
    )

    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="RESTRICT"), primary_key=True
    )
    raw_retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    aggregate_retention_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=365, server_default="365"
    )
    legal_basis: Mapped[str] = mapped_column(String(32), nullable=False)
    notice_text: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    notice_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    heartbeat_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    heartbeat_interval_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        server_default=str(DEFAULT_HEARTBEAT_INTERVAL_SECONDS),
    )
    heartbeat_retry_base_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=DEFAULT_HEARTBEAT_RETRY_BASE_SECONDS,
        server_default=str(DEFAULT_HEARTBEAT_RETRY_BASE_SECONDS),
    )
    heartbeat_retry_max_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=DEFAULT_HEARTBEAT_RETRY_MAX_SECONDS,
        server_default=str(DEFAULT_HEARTBEAT_RETRY_MAX_SECONDS),
    )
    heartbeat_stale_after_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=DEFAULT_HEARTBEAT_STALE_AFTER_SECONDS,
        server_default=str(DEFAULT_HEARTBEAT_STALE_AFTER_SECONDS),
    )
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TelemetryRevocation(Base):
    """Per-subject telemetry rights: notice, legal basis, revocation, erasure."""

    __tablename__ = "telemetry_revocation"
    __table_args__ = (
        CheckConstraint(
            "subject_kind in ('account','device')", name="ck_telemetry_revocation_subject_kind"
        ),
        CheckConstraint(
            "state in ('active','revoked','deleted')", name="ck_telemetry_revocation_state"
        ),
        CheckConstraint(
            "legal_basis is null or legal_basis in ('consent','contract','legitimate_interest')",
            name="ck_telemetry_revocation_basis",
        ),
        CheckConstraint("notice_revision >= 0", name="ck_telemetry_revocation_notice"),
    )

    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="RESTRICT"), primary_key=True
    )
    subject_kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )
    legal_basis: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notice_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notice_acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deletion_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TelemetryAudit(Base):
    """Append-only record of privileged telemetry access; carries no payloads."""

    __tablename__ = "telemetry_audit"
    __table_args__ = (
        CheckConstraint(
            "action in ("
            "'telemetry.ingest','telemetry.ingest.batch','telemetry.list',"
            "'telemetry.aggregate','telemetry.export','telemetry.policy.write',"
            "'telemetry.rights.write','telemetry.rights.revoke',"
            "'telemetry.delete','telemetry.retention','telemetry.audit.list'"
            ")",
            name="ck_telemetry_audit_action",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="RESTRICT"), index=True
    )
    actor_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    target_table: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[str] = mapped_column(String(128))
    detail: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


__all__ = [
    "TELEMETRY_GOVERNED_TABLES",
    "TelemetryAudit",
    "TelemetryEvent",
    "TelemetryPolicy",
    "TelemetryRevocation",
]
