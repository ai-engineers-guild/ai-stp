"""Server-only GitHub authority, source bindings and exact operation plans."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ai_stp_platform.db import Base
from ai_stp_platform.organization_scope import OrganizationScopedMixin


class GitHubConnector(OrganizationScopedMixin, Base):
    """An account's expiring user authorization; never an ordinary login token."""

    __tablename__ = "github_connector"
    __table_args__ = (UniqueConstraint("account_id", "purpose", name="uq_github_connector_owner"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("account.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(String(16))
    github_subject: Mapped[str] = mapped_column(String(64))
    authorization_revision: Mapped[str] = mapped_column(String(64))
    token_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    state: Mapped[str] = mapped_column(String(32))
    installations: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GitHubAuthorizationFlow(OrganizationScopedMixin, Base):
    """One-use OAuth state bound to the same authenticated platform session."""

    __tablename__ = "github_authorization_flow"

    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("account.id", ondelete="CASCADE"))
    session_id: Mapped[str] = mapped_column(String(128))
    purpose: Mapped[str] = mapped_column(String(16))
    locale: Mapped[str] = mapped_column(String(2))
    callback_uri: Mapped[str] = mapped_column(String(512))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GitHubSourceBinding(OrganizationScopedMixin, Base):
    """Immutable private coordinates associated with exact canonical bytes."""

    __tablename__ = "github_source_binding"
    __table_args__ = (
        UniqueConstraint("account_id", "idempotency_key", name="uq_github_source_request"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("account.id", ondelete="RESTRICT"))
    connector_id: Mapped[str] = mapped_column(
        ForeignKey("github_connector.id", ondelete="RESTRICT")
    )
    installation_id: Mapped[int] = mapped_column(BigInteger)
    repository_id: Mapped[int] = mapped_column(BigInteger)
    repository_owner_id: Mapped[int] = mapped_column(BigInteger)
    repository_full_name: Mapped[str] = mapped_column(String(256))
    commit: Mapped[str] = mapped_column(String(40))
    subpath: Mapped[str] = mapped_column(String(512))
    source_visibility: Mapped[str] = mapped_column(String(16))
    content_digest: Mapped[str] = mapped_column(String(71))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    inventory: Mapped[list[str]] = mapped_column(JSON)
    request_hash: Mapped[str] = mapped_column(String(71))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    passport_digest: Mapped[str | None] = mapped_column(String(71), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GitHubActionPlan(OrganizationScopedMixin, Base):
    """Durable exact intent and reconciliation state for one external effect."""

    __tablename__ = "github_action_plan"
    __table_args__ = (
        UniqueConstraint("account_id", "idempotency_key", name="uq_github_action_request"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("account.id", ondelete="RESTRICT"))
    device_id: Mapped[str] = mapped_column(ForeignKey("device.id", ondelete="RESTRICT"))
    connector_id: Mapped[str] = mapped_column(
        ForeignKey("github_connector.id", ondelete="RESTRICT")
    )
    authorization_revision: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(32))
    installation_id: Mapped[int] = mapped_column(BigInteger)
    repository_id: Mapped[int] = mapped_column(BigInteger)
    repository_owner_id: Mapped[int] = mapped_column(BigInteger)
    repository_owner_type: Mapped[str] = mapped_column(String(16))
    repository_full_name: Mapped[str] = mapped_column(String(256))
    previous_visibility: Mapped[str] = mapped_column(String(16))
    recipient: Mapped[str | None] = mapped_column(String(39), nullable=True)
    permission: Mapped[str | None] = mapped_column(String(16), nullable=True)
    plan_hash: Mapped[str] = mapped_column(String(71))
    request_hash: Mapped[str] = mapped_column(String(71))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    state: Mapped[str] = mapped_column(String(16), default="planned")
    result: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DistributionVisibilityPlan(OrganizationScopedMixin, Base):
    """Owner exposure intent without rewriting a version or artifact."""

    __tablename__ = "distribution_visibility_plan"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "idempotency_key", name="uq_distribution_visibility_request"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("account.id", ondelete="RESTRICT"))
    device_id: Mapped[str] = mapped_column(ForeignKey("device.id", ondelete="RESTRICT"))
    metadata_id: Mapped[int] = mapped_column(ForeignKey("catalog_metadata.id", ondelete="RESTRICT"))
    passport_digest: Mapped[str] = mapped_column(String(71))
    ownership_revision_id: Mapped[str | None] = mapped_column(String(73), nullable=True)
    previous_visibility: Mapped[str] = mapped_column(String(16))
    visibility: Mapped[str] = mapped_column(String(16))
    plan_hash: Mapped[str] = mapped_column(String(71))
    request_hash: Mapped[str] = mapped_column(String(71))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    state: Mapped[str] = mapped_column(String(16), default="planned")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
