"""Canonical latest CI checks and saved Corporate Hub dashboard queries."""

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ai_stp_platform.db import Base


class CorporateCiCheck(Base):
    __tablename__ = "corporate_ci_check"
    __table_args__ = (
        CheckConstraint(
            "status in ('pass','fail','outdated','revoked',"
            "'unsupported','not_enrolled','unverifiable')",
            name="ck_corporate_ci_check_status",
        ),
        CheckConstraint(
            "reason in ('none','check_failed','target_drift','source_unavailable',"
            "'permission_denied','unsupported','unknown')",
            name="ck_corporate_ci_check_reason",
        ),
        CheckConstraint("revision >= 1", name="ck_corporate_ci_check_revision"),
    )

    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("device.id", ondelete="CASCADE"), primary_key=True
    )
    harness: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    setup_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(32))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class CorporateDashboardView(Base):
    __tablename__ = "corporate_dashboard_view"
    __table_args__ = (
        CheckConstraint("scope in ('user','team','organization')", name="ck_dashboard_view_scope"),
        CheckConstraint("revision >= 1", name="ck_dashboard_view_revision"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scope: Mapped[str] = mapped_column(String(16))
    scope_id: Mapped[str] = mapped_column(String(64))
    owner_account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120))
    query: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
