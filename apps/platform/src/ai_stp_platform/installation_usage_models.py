"""Settled provider operation facts for corporate installation history."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ai_stp_platform.db import Base


class InstallationOperationFact(Base):
    __tablename__ = "installation_operation_fact"
    __table_args__ = (
        CheckConstraint(
            "action in ('install','update','remove','rollback')", name="ck_install_fact_action"
        ),
        CheckConstraint(
            "result in ('verified','partial','rolled_back','failed','stale')",
            name="ck_install_fact_result",
        ),
        CheckConstraint("scope in ('global','project','unknown')", name="ck_install_fact_scope"),
        Index("ix_install_fact_employee", "organization_id", "employee_account_id", "occurred_at"),
        Index("ix_install_fact_setup", "organization_id", "setup_stable_id", "setup_version"),
    )

    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="CASCADE"), primary_key=True
    )
    operation_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    fact_digest: Mapped[str] = mapped_column(String(80), nullable=False)
    employee_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    harness: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    setup_stable_id: Mapped[str | None] = mapped_column(String(128))
    setup_version: Mapped[str | None] = mapped_column(String(32))
    components: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False, default=list)
    components_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
