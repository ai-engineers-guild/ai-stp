"""Bounded corporate discovery snapshots for current installation evidence."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ai_stp_platform.db import Base


class InstallationInventorySnapshot(Base):
    __tablename__ = "installation_inventory_snapshot"
    __table_args__ = (
        Index(
            "ix_install_inventory_scope",
            "organization_id",
            "employee_account_id",
            "device_id",
            "scope",
            "project_id",
            "scanned_at",
        ),
        CheckConstraint("scope in ('global','project')", name="ck_install_inventory_scope"),
        CheckConstraint(
            "(scope = 'global' AND project_id IS NULL) OR "
            "(scope = 'project' AND project_id IS NOT NULL)",
            name="ck_install_inventory_project_scope",
        ),
    )

    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="CASCADE"), primary_key=True
    )
    scan_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    snapshot_digest: Mapped[str] = mapped_column(String(80), nullable=False)
    employee_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False)
    project_id: Mapped[str | None] = mapped_column(String(64))
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    complete: Mapped[bool] = mapped_column(Boolean, nullable=False)
    components: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
