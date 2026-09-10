"""Remote organizations and explicit project identity links (B2B-00).

Local project passports never enter these tables. The organization ID is the
tenant boundary for every remote object; the link table is the only place that
connects it to a local project ID.
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
    UniqueConstraint,
    event,
    func,
    inspect,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_stp_platform.db import Base


class Organization(Base):
    """One remote ownership aggregate, either personal or corporate."""

    __tablename__ = "organization"
    __table_args__ = (
        CheckConstraint("kind in ('personal', 'corporate')", name="ck_organization_kind"),
        CheckConstraint("revision >= 1", name="ck_organization_revision"),
        Index(
            "uq_organization_personal_owner",
            "owner_account_id",
            unique=True,
            postgresql_where=text("kind = 'personal'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    owner_account_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


@event.listens_for(Organization, "before_update")
def _reject_organization_identity_change(  # pyright: ignore[reportUnusedFunction]
    _mapper: object,
    _connection: object,
    target: Organization,
) -> None:
    """Keep the product organization identity immutable after creation."""
    state = inspect(target)
    if state.attrs.kind.history.has_changes():
        raise ValueError("organization kind is immutable")
    if target.kind == "personal" and state.attrs.owner_account_id.history.has_changes():
        raise ValueError("personal organization owner is immutable")


class OrganizationMembership(Base):
    """One account's active or suspended membership in one organization."""

    __tablename__ = "organization_membership"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "account_id", name="uq_organization_membership_account"
        ),
        CheckConstraint(
            "role in ('owner', 'admin', 'member')", name="ck_organization_membership_role"
        ),
        CheckConstraint(
            "state in ('active', 'suspended')", name="ck_organization_membership_state"
        ),
        CheckConstraint("revision >= 1", name="ck_organization_membership_revision"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization: Mapped[Organization] = relationship()
    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="member")
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OrganizationResource(Base):
    """Tenant ownership index for legacy account-owned cloud rows."""

    __tablename__ = "organization_resource"
    __table_args__ = (
        UniqueConstraint("table_name", "row_key", name="uq_organization_resource_row"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False, index=True
    )
    table_name: Mapped[str] = mapped_column(String(128), nullable=False)
    row_key: Mapped[str] = mapped_column(String(512), nullable=False)
    attribution_account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    attribution_column: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProjectIdentity(Base):
    """A remote or provider identity, kept separate from human names."""

    __tablename__ = "project_identity"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "namespace", "external_key", name="uq_project_identity_external"
        ),
        CheckConstraint(
            "namespace in ('remote', 'provider')", name="ck_project_identity_namespace"
        ),
        CheckConstraint(
            "state in ('active', 'archived', 'deleted')", name="ck_project_identity_state"
        ),
        CheckConstraint("revision >= 1", name="ck_project_identity_revision"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False, index=True
    )
    namespace: Mapped[str] = mapped_column(String(16), nullable=False)
    external_key: Mapped[str] = mapped_column(String(512), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    provider_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_installation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_namespace_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    immutable_repository_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    current_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    observed_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProjectLink(Base):
    """An explicit, tenant-scoped link between local and remote identities."""

    __tablename__ = "project_link"
    __table_args__ = (
        Index(
            "uq_project_link_local_active",
            "organization_id",
            "local_project_id",
            unique=True,
            postgresql_where=text("state in ('linked', 'conflict')"),
            sqlite_where=text("state in ('linked', 'conflict')"),
        ),
        CheckConstraint(
            "state in ('linked', 'unlinked', 'conflict')", name="ck_project_link_state"
        ),
        CheckConstraint("revision >= 1", name="ck_project_link_revision"),
        Index("ix_project_link_account_local", "organization_id", "local_project_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(64), nullable=False)
    plan_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("device.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    local_project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    remote_project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("project_identity.id", ondelete="RESTRICT"), nullable=False
    )
    provider_project_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("project_identity.id", ondelete="RESTRICT"), nullable=True
    )
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="linked")
    local_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    remote_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_revision: Mapped[str | None] = mapped_column(String(128), nullable=True)
    conflict_server_revision: Mapped[str | None] = mapped_column(String(71), nullable=True)
    conflict_client_revision: Mapped[str | None] = mapped_column(String(71), nullable=True)
    conflict_common_ancestor: Mapped[str | None] = mapped_column(String(71), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    create_idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    unlink_idempotency_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProjectLinkPlan(Base):
    """Server-authored, immutable decision required before creating a link."""

    __tablename__ = "project_link_plan"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_project_link_plan_key"),
        CheckConstraint(
            "state in ('ready', 'applied', 'expired')", name="ck_project_link_plan_state"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("device.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    local_project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    remote_project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("project_identity.id", ondelete="RESTRICT"), nullable=False
    )
    provider_project_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("project_identity.id", ondelete="RESTRICT"), nullable=True
    )
    local_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    remote_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_revision: Mapped[str | None] = mapped_column(String(128), nullable=True)
    authorization_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    plan_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="ready")
    link_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("project_link.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProjectUnlinkPlan(Base):
    """Server-authored, immutable decision required before unlinking a link."""

    __tablename__ = "project_unlink_plan"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_project_unlink_plan_key"),
        CheckConstraint(
            "state in ('ready', 'applied', 'expired')", name="ck_project_unlink_plan_state"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False, index=True
    )
    link_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("project_link.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    actor_account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("device.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    local_project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    remote_project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_project_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expected_link_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    local_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    remote_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_revision: Mapped[str | None] = mapped_column(String(128), nullable=True)
    authorization_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    plan_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="ready")
    confirmation_idempotency_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProjectSyncPlan(Base):
    """A durable no-side-effect sync decision tied to one link revision."""

    __tablename__ = "project_sync_plan"
    __table_args__ = (
        UniqueConstraint("link_id", "idempotency_key", name="uq_project_sync_plan_idempotency"),
        CheckConstraint(
            "state in ('ready', 'conflict', 'applied', 'failed', 'unknown')",
            name="ck_project_sync_plan_state",
        ),
        CheckConstraint(
            "action in ('noop', 'local_to_remote', 'remote_to_local', 'merge_required')",
            name="ck_project_sync_plan_action",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    link_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("project_link.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    actor_account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("device.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    expected_link_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    local_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    remote_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_revision: Mapped[str | None] = mapped_column(String(128), nullable=True)
    remote_identity_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_identity_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conflict_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    common_ancestor_revision: Mapped[str | None] = mapped_column(String(128), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    plan_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    apply_idempotency_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True
    )
    result: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProjectRevision(Base):
    """Append-only organization-scoped DAG node for one remote project."""

    __tablename__ = "project_revision"
    __table_args__ = (
        PrimaryKeyConstraint("organization_id", "remote_project_id", "revision_id"),
        CheckConstraint(
            "operation in ('upsert', 'tombstone')", name="ck_project_revision_operation"
        ),
        CheckConstraint(
            "json_array_length(parent_revision_ids) <= 2", name="ck_project_revision_parents"
        ),
        Index(
            "ix_project_revision_project_created",
            "organization_id",
            "remote_project_id",
            "created_at",
        ),
    )

    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    remote_project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("project_identity.id", ondelete="RESTRICT"), nullable=False
    )
    revision_id: Mapped[str] = mapped_column(String(71), nullable=False)
    parent_revision_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    content_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    projection: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    actor_account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="RESTRICT"), nullable=False
    )
    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("device.id", ondelete="RESTRICT"), nullable=False
    )
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProjectRevisionHead(Base):
    """Current head pointer; revision history is never overwritten."""

    __tablename__ = "project_revision_head"
    __table_args__ = (PrimaryKeyConstraint("organization_id", "remote_project_id"),)

    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    remote_project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("project_identity.id", ondelete="RESTRICT"), nullable=False
    )
    revision_id: Mapped[str] = mapped_column(String(71), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProjectRevisionReceipt(Base):
    """Idempotent receipt for one explicit project push."""

    __tablename__ = "project_revision_receipt"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "remote_project_id",
            "idempotency_key",
            name="uq_project_revision_receipt_idempotency",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    remote_project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(71), nullable=False)
    response_body: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProjectLinkProposal(Base):
    """Non-authoritative observation; it never creates or changes a link."""

    __tablename__ = "project_link_proposal"
    __table_args__ = (CheckConstraint("state = 'proposed'", name="ck_project_link_proposal_state"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    local_project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    remote_project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_project_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
