"""Durable corporate installation heartbeat state (t-heartbeat, GitHub #215).

One row per (organization, device): the latest accepted heartbeat. Repeated
writes coalesce onto this row and a stale write never overwrites a newer one,
so the table stays small and monotonic without a cleanup job.
"""

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ai_stp_platform.db import Base


class InstallationHeartbeat(Base):
    """The latest accepted heartbeat for one (organization, device) pair."""

    __tablename__ = "installation_heartbeat"
    __table_args__ = (
        CheckConstraint(
            "reported_state in ('active', 'partial', 'failing', 'disabled')",
            name="ck_installation_heartbeat_reported_state",
        ),
        CheckConstraint("revision >= 1", name="ck_installation_heartbeat_revision"),
        Index("ix_installation_heartbeat_account", "organization_id", "account_id"),
    )

    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="CASCADE"), primary_key=True
    )
    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("device.id", ondelete="CASCADE"), primary_key=True
    )
    account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    cli_version: Mapped[str] = mapped_column(String(64))
    capabilities: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reported_state: Mapped[str] = mapped_column(String(16))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InstallationHeartbeatEvent(Base):
    """One accepted, distinct signal; retained for the corporate history report."""

    __tablename__ = "installation_heartbeat_event"
    __table_args__ = (
        CheckConstraint(
            "reported_state in ('active', 'partial', 'failing', 'disabled')",
            name="ck_heartbeat_event_reported_state",
        ),
        CheckConstraint("interval_seconds > 0", name="ck_heartbeat_event_interval"),
        Index("ix_installation_heartbeat_event_account", "organization_id", "account_id"),
        Index("ix_installation_heartbeat_event_period", "organization_id", "received_at"),
        Index(
            "ix_installation_heartbeat_event_device_period",
            "organization_id",
            "device_id",
            "received_at",
        ),
    )

    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="CASCADE"), primary_key=True
    )
    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("device.id", ondelete="CASCADE"), primary_key=True
    )
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reported_state: Mapped[str] = mapped_column(String(16), nullable=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)


class InstallationHeartbeatPolicyEvent(Base):
    """Effective heartbeat cadence at each organization policy revision."""

    __tablename__ = "installation_heartbeat_policy_event"

    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    enabled: Mapped[bool] = mapped_column(nullable=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    stale_after_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
