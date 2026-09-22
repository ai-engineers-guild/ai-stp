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
            "reported_state in ('active', 'failing', 'disabled')",
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
