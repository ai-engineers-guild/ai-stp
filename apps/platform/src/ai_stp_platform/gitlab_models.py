"""Server-only GitLab authority and immutable read-only source bindings."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ai_stp_platform.db import Base
from ai_stp_platform.organization_scope import OrganizationScopedMixin


class GitLabConnector(OrganizationScopedMixin, Base):
    """An account's expiring user grant on one GitLab instance; never a login
    token, and scoped to reads — the connector issues no mutation calls."""

    __tablename__ = "gitlab_connector"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "gitlab_base_url", "purpose", name="uq_gitlab_connector_owner"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("account.id", ondelete="CASCADE"))
    gitlab_base_url: Mapped[str] = mapped_column(String(512))
    # The organization whose GitLabConnection configured the OAuth application
    # this grant was issued through; the grant itself stays account-owned.
    connection_organization_id: Mapped[str] = mapped_column(String(64))
    purpose: Mapped[str] = mapped_column(String(16))
    gitlab_subject: Mapped[str] = mapped_column(String(255))
    authorization_revision: Mapped[str] = mapped_column(String(64))
    token_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    state: Mapped[str] = mapped_column(String(32))
    projects: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GitLabAuthorizationFlow(OrganizationScopedMixin, Base):
    """One-use OAuth state bound to the same authenticated platform session."""

    __tablename__ = "gitlab_authorization_flow"

    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("account.id", ondelete="CASCADE"))
    session_id: Mapped[str] = mapped_column(String(128))
    connection_organization_id: Mapped[str] = mapped_column(String(64))
    purpose: Mapped[str] = mapped_column(String(16))
    locale: Mapped[str] = mapped_column(String(2))
    callback_uri: Mapped[str] = mapped_column(String(512))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GitLabSourceBinding(OrganizationScopedMixin, Base):
    """Immutable private coordinates associated with exact canonical bytes."""

    __tablename__ = "gitlab_source_binding"
    __table_args__ = (
        UniqueConstraint("account_id", "idempotency_key", name="uq_gitlab_source_request"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("account.id", ondelete="RESTRICT"))
    connector_id: Mapped[str] = mapped_column(
        ForeignKey("gitlab_connector.id", ondelete="RESTRICT")
    )
    gitlab_base_url: Mapped[str] = mapped_column(String(512))
    project_id: Mapped[int] = mapped_column(BigInteger)
    namespace_id: Mapped[int] = mapped_column(BigInteger)
    path_with_namespace: Mapped[str] = mapped_column(String(256))
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
