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
    FetchedValue,
    ForeignKey,
    ForeignKeyConstraint,
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
        CheckConstraint(
            "substr(id, 1, 13) = 'organization_' AND length(id) = 39",
            name="ck_organization_id",
        ),
        CheckConstraint("kind in ('personal', 'corporate')", name="ck_organization_kind"),
        CheckConstraint(
            "(kind = 'personal' AND owner_account_id IS NOT NULL) OR "
            "(kind = 'corporate' AND owner_account_id IS NULL)",
            name="ck_organization_owner_shape",
        ),
        CheckConstraint("revision >= 1", name="ck_organization_revision"),
        CheckConstraint("policy_revision >= 1", name="ck_organization_policy_revision"),
        CheckConstraint("state in ('active', 'suspended')", name="ck_organization_state"),
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
    policy_revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )
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


class EntityProfileColumns:
    """Tenant presentation content has its own optimistic revision."""

    profile: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    profile_revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )


class CorporateJobTitle(Base):
    """Organization-governed employee classification, independent of RBAC."""

    __tablename__ = "corporate_job_title"
    __table_args__ = (
        PrimaryKeyConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "normalized_name", name="uq_corporate_job_title_name"),
        CheckConstraint("state in ('current', 'retired')", name="ck_corporate_job_title_state"),
        CheckConstraint("revision >= 1", name="ck_corporate_job_title_revision"),
    )

    id: Mapped[str] = mapped_column(String(64))
    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(
        String(2000), nullable=False, default="", server_default=""
    )
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="current", server_default="current"
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OrganizationMembership(EntityProfileColumns, Base):
    """One account's active or suspended membership in one organization."""

    __tablename__ = "organization_membership"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "account_id", name="uq_organization_membership_account"
        ),
        CheckConstraint("length(role) between 1 and 64", name="ck_organization_membership_role"),
        CheckConstraint(
            "state in ('active', 'suspended')", name="ck_organization_membership_state"
        ),
        CheckConstraint("revision >= 1", name="ck_organization_membership_revision"),
        CheckConstraint(
            "profile_revision >= 0", name="ck_organization_membership_profile_revision"
        ),
        ForeignKeyConstraint(
            ["organization_id", "job_title_id"],
            ["corporate_job_title.organization_id", "corporate_job_title.id"],
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization: Mapped[Organization] = relationship()
    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(64), nullable=False, default="member")
    display_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    job_title_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CorporateRolePermission(Base):
    """One persisted permission in a corporate role's closed matrix."""

    __tablename__ = "corporate_role_permission"
    __table_args__ = (
        PrimaryKeyConstraint("organization_id", "role", "permission"),
        ForeignKeyConstraint(
            ["organization_id", "role"],
            ["corporate_role.organization_id", "corporate_role.name"],
            ondelete="CASCADE",
        ),
    )

    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    permission: Mapped[str] = mapped_column(String(64), nullable=False)


class CorporateRole(Base):
    """One named corporate role and its persisted hierarchy edge."""

    __tablename__ = "corporate_role"
    __table_args__ = (PrimaryKeyConstraint("organization_id", "name"),)

    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


class CorporateServicePrincipal(Base):
    """One non-human corporate actor governed by the same scoped role policy."""

    __tablename__ = "corporate_service_principal"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_corporate_service_principal_tenant_id"),
        UniqueConstraint("organization_id", "name", name="uq_corporate_service_principal_name"),
        CheckConstraint(
            "state in ('active', 'suspended')", name="ck_corporate_service_principal_state"
        ),
        CheckConstraint("revision >= 1", name="ck_corporate_service_principal_revision"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CorporateRoleBinding(Base):
    """One tenant-scoped role assignment for an organization member."""

    __tablename__ = "corporate_role_binding"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "service_principal_id"],
            [
                "corporate_service_principal.organization_id",
                "corporate_service_principal.id",
            ],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "account_id"],
            ["organization_membership.organization_id", "organization_membership.account_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "role"],
            ["corporate_role.organization_id", "corporate_role.name"],
            ondelete="RESTRICT",
        ),
        Index(
            "uq_corporate_role_binding_active_user_scope",
            "organization_id",
            "account_id",
            "role",
            "scope_kind",
            "scope_id",
            unique=True,
            postgresql_where=text("state = 'active' AND principal_type = 'user'"),
        ),
        Index(
            "uq_corporate_role_binding_active_service_scope",
            "organization_id",
            "service_principal_id",
            "role",
            "scope_kind",
            "scope_id",
            unique=True,
            postgresql_where=text("state = 'active' AND principal_type = 'service_principal'"),
        ),
        CheckConstraint(
            "scope_kind in ('system', 'organization', 'team', 'project', 'technology', "
            "'catalog_object', 'telemetry')",
            name="ck_role_binding_scope_kind",
        ),
        CheckConstraint("state in ('active', 'revoked')", name="ck_role_binding_state"),
        CheckConstraint(
            "(principal_type = 'user' AND account_id IS NOT NULL "
            "AND service_principal_id IS NULL) OR "
            "(principal_type = 'service_principal' AND account_id IS NULL "
            "AND service_principal_id IS NOT NULL)",
            name="ck_role_binding_principal",
        ),
        CheckConstraint("revision >= 1", name="ck_role_binding_revision"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False, index=True
    )
    principal_type: Mapped[str] = mapped_column(String(24), nullable=False, default="user")
    account_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="CASCADE"), nullable=True, index=True
    )
    service_principal_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(64), nullable=False, default="*")
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CorporateProject(EntityProfileColumns, Base):
    """A corporate project whose identity and ownership share one tenant key."""

    __tablename__ = "corporate_project"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "id", "identity_namespace"],
            [
                "project_identity.organization_id",
                "project_identity.id",
                "project_identity.namespace",
            ],
            ondelete="RESTRICT",
            name="fk_corporate_project_identity",
        ),
        CheckConstraint("identity_namespace = 'remote'", name="ck_corporate_project_identity"),
        CheckConstraint(
            "activity_override IS NULL OR activity_override IN ('active','inactive')",
            name="ck_corporate_project_activity_override",
        ),
        UniqueConstraint("organization_id", "id", name="uq_corporate_project_tenant_id"),
        UniqueConstraint("organization_id", "name", name="uq_corporate_project_name"),
        CheckConstraint("state in ('active', 'archived')", name="ck_corporate_project_state"),
        CheckConstraint(
            "lifecycle IN ('active','deprecated','archived','deleted')",
            name="ck_corporate_project_lifecycle",
        ),
        CheckConstraint(
            "restore_lifecycle IN ('active','deprecated')",
            name="ck_corporate_project_restore",
        ),
        CheckConstraint(
            "state = CASE WHEN lifecycle = 'active' THEN 'active' ELSE 'archived' END",
            name="ck_corporate_project_projection",
        ),
        CheckConstraint("revision >= 1", name="ck_corporate_project_revision"),
        CheckConstraint("profile_revision >= 0", name="ck_corporate_project_profile_revision"),
        CheckConstraint(
            "source_availability IN ('unknown','available','unavailable')",
            name="ck_corporate_project_source_availability",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    identity_namespace: Mapped[str] = mapped_column(
        String(16), nullable=False, default="remote", server_default="remote"
    )
    repository_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_availability: Mapped[str] = mapped_column(
        String(16), nullable=False, default="unknown", server_default="unknown"
    )
    activity_override: Mapped[str | None] = mapped_column(String(16))
    lifecycle: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=FetchedValue()
    )
    restore_lifecycle: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CorporateTeam(EntityProfileColumns, Base):
    """A minimal organization-owned team used by corporate bootstrap administration."""

    __tablename__ = "corporate_team"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_corporate_team_tenant_id"),
        UniqueConstraint("organization_id", "name", name="uq_corporate_team_name"),
        CheckConstraint("state in ('active', 'archived')", name="ck_corporate_team_state"),
        CheckConstraint("profile_revision >= 0", name="ck_corporate_team_profile_revision"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(
        String(2000), nullable=False, default="", server_default=""
    )
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CorporateTeamMember(Base):
    """A tenant-compatible member assignment to one team."""

    __tablename__ = "corporate_team_member"
    __table_args__ = (
        PrimaryKeyConstraint("organization_id", "team_id", "account_id"),
        ForeignKeyConstraint(
            ["organization_id", "team_id"],
            ["corporate_team.organization_id", "corporate_team.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "account_id"],
            ["organization_membership.organization_id", "organization_membership.account_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("role in ('lead', 'staff')", name="ck_corporate_team_member_role"),
    )

    organization_id: Mapped[str] = mapped_column(String(64), nullable=False)
    team_id: Mapped[str] = mapped_column(String(64), nullable=False)
    account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="staff")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CorporateProjectMember(Base):
    """A tenant-compatible member assignment to one corporate project."""

    __tablename__ = "corporate_project_member"
    __table_args__ = (
        PrimaryKeyConstraint("organization_id", "project_id", "account_id"),
        ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["corporate_project.organization_id", "corporate_project.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "account_id"],
            ["organization_membership.organization_id", "organization_membership.account_id"],
            ondelete="CASCADE",
        ),
    )

    organization_id: Mapped[str] = mapped_column(String(64), nullable=False)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CorporateBootstrapReceipt(Base):
    """The durable idempotency fence for the one corporate bootstrap."""

    __tablename__ = "corporate_bootstrap_receipt"

    idempotency_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_fingerprint: Mapped[str] = mapped_column(String(71), nullable=False)
    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CorporateProvisionedIdentity(Base):
    """Verified-email handoff from corporate provisioning to later OAuth login."""

    __tablename__ = "corporate_provisioned_identity"
    __table_args__ = (
        PrimaryKeyConstraint("organization_id", "normalized_email"),
        UniqueConstraint("normalized_email", name="uq_corporate_provisioned_identity_email"),
    )

    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    normalized_email: Mapped[str] = mapped_column(String(320), nullable=False)
    account_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CorporateMutationReceipt(Base):
    """Idempotent response for one corporate create operation."""

    __tablename__ = "corporate_mutation_receipt"
    __table_args__ = (PrimaryKeyConstraint("organization_id", "idempotency_key"),)

    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(71), nullable=False)
    response_body: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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
            "organization_id", "id", "namespace", name="uq_project_identity_tenant_namespace"
        ),
        UniqueConstraint("organization_id", "id", name="uq_project_identity_tenant_id"),
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
    provider_default_branch: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_observed_revision: Mapped[str | None] = mapped_column(String(128), nullable=True)
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


class CorporateCatalogAssignment(Base):
    """An exact catalog version assigned to one tenant-local operational subject."""

    __tablename__ = "corporate_catalog_assignment"
    __table_args__ = (
        CheckConstraint(
            "object_kind in ('setup','component')", name="ck_corporate_assignment_kind"
        ),
        CheckConstraint("state in ('current','retired')", name="ck_corporate_assignment_state"),
        CheckConstraint("revision >= 1", name="ck_corporate_assignment_revision"),
        CheckConstraint(
            "(CASE WHEN account_id IS NULL THEN 0 ELSE 1 END + "
            "CASE WHEN team_id IS NULL THEN 0 ELSE 1 END + "
            "CASE WHEN project_id IS NULL THEN 0 ELSE 1 END + "
            "CASE WHEN technology_id IS NULL THEN 0 ELSE 1 END) <= 1",
            name="ck_corporate_assignment_subject",
        ),
        CheckConstraint("selector in ('exact','latest')", name="ck_corporate_assignment_selector"),
        CheckConstraint(
            "selector = 'latest' OR version IS NOT NULL",
            name="ck_corporate_assignment_selector_version",
        ),
        ForeignKeyConstraint(
            ["organization_id", "account_id"],
            ["organization_membership.organization_id", "organization_membership.account_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "team_id"],
            ["corporate_team.organization_id", "corporate_team.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["corporate_project.organization_id", "corporate_project.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "technology_id"],
            ["technology.organization_id", "technology.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["object_kind", "stable_id", "version"],
            [
                "catalog_metadata.object_kind",
                "catalog_metadata.stable_id",
                "catalog_metadata.version",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "organization_id",
            "account_id",
            "object_kind",
            "stable_id",
            "version",
            "harness",
            name="uq_corporate_assignment_account",
        ),
        UniqueConstraint(
            "organization_id",
            "team_id",
            "object_kind",
            "stable_id",
            "version",
            "harness",
            name="uq_corporate_assignment_team",
        ),
        UniqueConstraint(
            "organization_id",
            "project_id",
            "object_kind",
            "stable_id",
            "version",
            "harness",
            name="uq_corporate_assignment_project",
        ),
        UniqueConstraint(
            "organization_id",
            "technology_id",
            "object_kind",
            "stable_id",
            "version",
            "harness",
            name="uq_corporate_assignment_technology",
        ),
        Index(
            "uq_corporate_assignment_organization",
            "organization_id",
            "object_kind",
            "stable_id",
            "version",
            "harness",
            unique=True,
            postgresql_where=text(
                "account_id IS NULL AND team_id IS NULL "
                "AND project_id IS NULL AND technology_id IS NULL"
            ),
            sqlite_where=text(
                "account_id IS NULL AND team_id IS NULL "
                "AND project_id IS NULL AND technology_id IS NULL"
            ),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    team_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    technology_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    object_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    stable_id: Mapped[str] = mapped_column(String(64), nullable=False)
    selector: Mapped[str] = mapped_column(
        String(8), nullable=False, default="exact", server_default="exact"
    )
    version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    passport_digest: Mapped[str | None] = mapped_column(String(80), nullable=True)
    harness: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="current", server_default="current"
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CorporateAssignmentDistribution(Base):
    """Derived per-target result of one bulk assign/revoke operation (ADR-0196).

    Keyed by source assignment, target, and the source assignment's operation
    revision at distribution time. The row records the outcome and a safe
    diagnostic only; the source assignment remains the policy, so no selector,
    version, or harness field is duplicated here.
    """

    __tablename__ = "corporate_assignment_distribution"
    __table_args__ = (
        PrimaryKeyConstraint(
            "organization_id",
            "source_assignment_id",
            "target_kind",
            "target_id",
            "operation_revision",
        ),
        CheckConstraint(
            "target_kind in ('employee','project')", name="ck_distribution_target_kind"
        ),
        CheckConstraint("action in ('assign','revoke')", name="ck_distribution_action"),
        CheckConstraint(
            "result in ('applied','skipped','conflicted','denied','failed')",
            name="ck_distribution_result",
        ),
        CheckConstraint(
            "state in ('pending','installed','outdated','failed','revoked')",
            name="ck_distribution_state",
        ),
        CheckConstraint("operation_revision >= 1", name="ck_distribution_operation_revision"),
        ForeignKeyConstraint(
            ["source_assignment_id"],
            ["corporate_catalog_assignment.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            ondelete="RESTRICT",
        ),
    )

    organization_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_assignment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    operation_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(8), nullable=False)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    #: NULL when the target has no distribution lifecycle (skipped/conflicted/denied).
    state: Mapped[str | None] = mapped_column(String(16), nullable=True)
    diagnostic: Mapped[str | None] = mapped_column(String(200), nullable=True)
    overriding_assignment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CorporateCatalogMaintainer(Base):
    """Retained employee/team maintainer relation for a stable catalog object."""

    __tablename__ = "corporate_catalog_maintainer"
    __table_args__ = (
        PrimaryKeyConstraint(
            "organization_id",
            "object_kind",
            "stable_id",
            "version",
            "subject_kind",
            "subject_id",
        ),
        CheckConstraint("object_kind in ('setup','component')", name="ck_catalog_maintainer_kind"),
        CheckConstraint(
            "subject_kind in ('employee','team')", name="ck_catalog_maintainer_subject"
        ),
        CheckConstraint("state in ('current','retired')", name="ck_catalog_maintainer_state"),
        CheckConstraint("revision >= 1", name="ck_catalog_maintainer_revision"),
    )

    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="RESTRICT"), primary_key=True
    )
    object_kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    stable_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[str] = mapped_column(String(32), primary_key=True)
    subject_kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="current")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    actor_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CorporateCatalogVerification(Base):
    """Tenant verification, independent from global catalog verification flags."""

    __tablename__ = "corporate_catalog_verification"
    __table_args__ = (
        PrimaryKeyConstraint("organization_id", "object_kind", "stable_id", "version"),
        CheckConstraint(
            "object_kind in ('setup','component')", name="ck_corporate_verification_kind"
        ),
        CheckConstraint("state in ('verified','revoked')", name="ck_corporate_verification_state"),
        CheckConstraint("revision >= 1", name="ck_corporate_verification_revision"),
    )

    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="RESTRICT"), primary_key=True
    )
    object_kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    stable_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[str] = mapped_column(String(32), primary_key=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="verified")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    verified_by_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CorporateCatalogLifecycle(Base):
    """Tenant moderation state without changing immutable public lifecycle."""

    __tablename__ = "corporate_catalog_lifecycle"
    __table_args__ = (
        PrimaryKeyConstraint("organization_id", "object_kind", "stable_id", "version"),
        CheckConstraint("object_kind in ('setup','component')", name="ck_corporate_lifecycle_kind"),
        CheckConstraint(
            "state in ('visible','hidden','deprecated','retired')",
            name="ck_corporate_lifecycle_state",
        ),
        CheckConstraint("revision >= 1", name="ck_corporate_lifecycle_revision"),
    )

    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organization.id", ondelete="RESTRICT"), primary_key=True
    )
    object_kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    stable_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[str] = mapped_column(String(32), primary_key=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="visible")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    actor_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


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
