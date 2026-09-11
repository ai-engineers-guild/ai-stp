"""Add corporate bootstrap, scoped RBAC, projects, and auditable outcomes.

Revision ID: 0063_corporate_core
Revises: 0062_organization_shape_invariants
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0063_corporate_core"
down_revision: str | None = "0062_organization_shape_invariants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CORPORATE_TENANT_TABLES = (
    "corporate_role",
    "corporate_role_permission",
    "corporate_service_principal",
    "corporate_role_binding",
    "corporate_project",
    "corporate_team",
    "corporate_team_member",
    "corporate_project_member",
    "corporate_bootstrap_receipt",
    "corporate_mutation_receipt",
    "corporate_provisioned_identity",
)
SHARED_TENANT_TABLES = ("organization_membership", "audit_event", "job")


def upgrade() -> None:
    op.drop_constraint("uq_job_idempotency_key", "job", type_="unique")
    op.create_index(
        "uq_job_tenant_idempotency",
        "job",
        ["organization_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NOT NULL"),
    )
    op.create_index(
        "uq_job_global_idempotency",
        "job",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NULL"),
    )
    op.add_column(
        "organization",
        sa.Column("policy_revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "organization",
        sa.Column("state", sa.String(16), nullable=False, server_default="active"),
    )
    op.create_check_constraint(
        "ck_organization_policy_revision", "organization", "policy_revision >= 1"
    )
    op.create_check_constraint(
        "ck_organization_state", "organization", "state in ('active', 'suspended')"
    )
    op.drop_constraint("ck_organization_membership_role", "organization_membership", type_="check")
    op.create_check_constraint(
        "ck_organization_membership_role",
        "organization_membership",
        "role in ('owner', 'admin', 'member', 'superadmin', 'lead', 'staff')",
    )

    op.create_table(
        "corporate_role",
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(16), nullable=False),
        sa.Column("parent_role", sa.String(16), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("organization_id", "name"),
        sa.CheckConstraint(
            "name in ('superadmin', 'lead', 'staff')", name="ck_corporate_role_name"
        ),
        sa.CheckConstraint(
            "parent_role is null or parent_role in ('superadmin', 'lead')",
            name="ck_corporate_role_parent",
        ),
    )
    op.create_table(
        "corporate_role_permission",
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("permission", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("organization_id", "role", "permission"),
        sa.CheckConstraint(
            "role in ('superadmin', 'lead', 'staff')", name="ck_role_permission_role"
        ),
    )
    op.create_table(
        "corporate_service_principal",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="active"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_corporate_service_principal_tenant_id"
        ),
        sa.UniqueConstraint("organization_id", "name", name="uq_corporate_service_principal_name"),
        sa.CheckConstraint(
            "state in ('active', 'suspended')", name="ck_corporate_service_principal_state"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_corporate_service_principal_revision"),
    )
    op.create_index(
        "ix_corporate_service_principal_organization_id",
        "corporate_service_principal",
        ["organization_id"],
    )
    op.create_table(
        "corporate_role_binding",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("principal_type", sa.String(24), nullable=False, server_default="user"),
        sa.Column("account_id", sa.String(64), nullable=True),
        sa.Column("service_principal_id", sa.String(64), nullable=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("scope_kind", sa.String(32), nullable=False),
        sa.Column("scope_id", sa.String(64), nullable=False, server_default="*"),
        sa.Column("state", sa.String(16), nullable=False, server_default="active"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "service_principal_id"],
            [
                "corporate_service_principal.organization_id",
                "corporate_service_principal.id",
            ],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("role in ('superadmin', 'lead', 'staff')", name="ck_role_binding_role"),
        sa.CheckConstraint(
            "scope_kind in ('system', 'organization', 'team', 'project', 'technology', "
            "'catalog_object', 'telemetry')",
            name="ck_role_binding_scope_kind",
        ),
        sa.CheckConstraint("state in ('active', 'revoked')", name="ck_role_binding_state"),
        sa.CheckConstraint(
            "(principal_type = 'user' AND account_id IS NOT NULL "
            "AND service_principal_id IS NULL) OR "
            "(principal_type = 'service_principal' AND account_id IS NULL "
            "AND service_principal_id IS NOT NULL)",
            name="ck_role_binding_principal",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_role_binding_revision"),
    )
    op.create_index(
        "ix_corporate_role_binding_organization_id",
        "corporate_role_binding",
        ["organization_id"],
    )
    op.create_index(
        "ix_corporate_role_binding_account_id", "corporate_role_binding", ["account_id"]
    )
    op.create_index(
        "ix_corporate_role_binding_service_principal_id",
        "corporate_role_binding",
        ["service_principal_id"],
    )
    op.create_index(
        "uq_corporate_role_binding_active_user_scope",
        "corporate_role_binding",
        ["organization_id", "account_id", "role", "scope_kind", "scope_id"],
        unique=True,
        postgresql_where=sa.text("state = 'active' AND principal_type = 'user'"),
    )
    op.create_index(
        "uq_corporate_role_binding_active_service_scope",
        "corporate_role_binding",
        ["organization_id", "service_principal_id", "role", "scope_kind", "scope_id"],
        unique=True,
        postgresql_where=sa.text("state = 'active' AND principal_type = 'service_principal'"),
    )
    op.create_table(
        "corporate_project",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="active"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("organization_id", "id", name="uq_corporate_project_tenant_id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_corporate_project_name"),
        sa.CheckConstraint("state in ('active', 'archived')", name="ck_corporate_project_state"),
        sa.CheckConstraint("revision >= 1", name="ck_corporate_project_revision"),
    )
    op.create_index(
        "ix_corporate_project_organization_id", "corporate_project", ["organization_id"]
    )
    op.create_table(
        "corporate_team",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="active"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("organization_id", "id", name="uq_corporate_team_tenant_id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_corporate_team_name"),
        sa.CheckConstraint("state in ('active', 'archived')", name="ck_corporate_team_state"),
    )
    op.create_index("ix_corporate_team_organization_id", "corporate_team", ["organization_id"])
    op.create_table(
        "corporate_team_member",
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("team_id", sa.String(64), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="staff"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["organization_id", "team_id"],
            ["corporate_team.organization_id", "corporate_team.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("organization_id", "team_id", "account_id"),
        sa.CheckConstraint("role in ('lead', 'staff')", name="ck_corporate_team_member_role"),
    )
    op.create_table(
        "corporate_project_member",
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["corporate_project.organization_id", "corporate_project.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("organization_id", "project_id", "account_id"),
    )
    op.create_table(
        "corporate_bootstrap_receipt",
        sa.Column("idempotency_key", sa.String(128), primary_key=True),
        sa.Column("request_fingerprint", sa.String(71), nullable=False),
        sa.Column("organization_id", sa.String(64), nullable=False, unique=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="RESTRICT"),
    )
    op.create_table(
        "corporate_mutation_receipt",
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("request_fingerprint", sa.String(71), nullable=False),
        sa.Column("response_body", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("organization_id", "idempotency_key"),
    )
    op.create_table(
        "corporate_provisioned_identity",
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("normalized_email", sa.String(320), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("organization_id", "normalized_email"),
        sa.UniqueConstraint("normalized_email", name="uq_corporate_provisioned_identity_email"),
    )
    op.add_column(
        "audit_event",
        sa.Column("outcome", sa.String(16), nullable=False, server_default="succeeded"),
    )
    op.add_column("audit_event", sa.Column("request_id", sa.String(128), nullable=True))
    op.add_column(
        "audit_event",
        sa.Column("actor_type", sa.String(24), nullable=False, server_default="user"),
    )
    op.add_column("audit_event", sa.Column("actor_id", sa.String(128), nullable=True))
    op.execute("UPDATE audit_event SET actor_id = actor_account_id")
    op.add_column(
        "audit_event",
        sa.Column("effective_role_bindings", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.create_index("ix_audit_event_request_id", "audit_event", ["request_id"])
    op.create_index("ix_audit_event_actor_id", "audit_event", ["actor_id"])
    op.create_check_constraint(
        "ck_audit_event_outcome",
        "audit_event",
        "outcome in ('succeeded', 'denied', 'failed')",
    )
    op.create_check_constraint(
        "ck_audit_event_actor_type",
        "audit_event",
        "actor_type in ('user', 'service_principal', 'system')",
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION ai_stp_reject_tenant_change()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.organization_id IS DISTINCT FROM OLD.organization_id THEN
                    RAISE EXCEPTION 'organization_id is immutable';
                END IF;
                RETURN NEW;
            END;
            $$;
            """
        )
        for table_name in (*CORPORATE_TENANT_TABLES, *SHARED_TENANT_TABLES):
            op.execute(
                f"CREATE TRIGGER {table_name}_tenant_immutable "
                f"BEFORE UPDATE OF organization_id ON {table_name} "
                "FOR EACH ROW EXECUTE FUNCTION ai_stp_reject_tenant_change()"
            )
        tenant_expression = (
            "current_setting('ai_stp.organization_id', true) = '*' OR "
            "organization_id = current_setting('ai_stp.organization_id', true)"
        )
        for table_name in CORPORATE_TENANT_TABLES:
            op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
            op.execute(
                f"CREATE POLICY {table_name}_tenant_policy ON {table_name} "
                f"USING ({tenant_expression}) WITH CHECK ({tenant_expression})"
            )
        shared_expression = (
            "organization_id IS NULL OR NOT EXISTS ("
            "SELECT 1 FROM organization WHERE organization.id = organization_id "
            "AND organization.kind = 'corporate') OR "
            f"{tenant_expression}"
        )
        for table_name in SHARED_TENANT_TABLES:
            op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
            op.execute(
                f"CREATE POLICY {table_name}_tenant_policy ON {table_name} "
                f"USING ({shared_expression}) WITH CHECK ({shared_expression})"
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table_name in (*CORPORATE_TENANT_TABLES, *SHARED_TENANT_TABLES):
            op.execute(f"DROP POLICY {table_name}_tenant_policy ON {table_name}")
            op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")
            op.execute(f"DROP TRIGGER {table_name}_tenant_immutable ON {table_name}")
        op.execute("DROP FUNCTION ai_stp_reject_tenant_change()")
    op.drop_constraint("ck_audit_event_actor_type", "audit_event", type_="check")
    op.drop_constraint("ck_audit_event_outcome", "audit_event", type_="check")
    op.drop_index("ix_audit_event_actor_id", table_name="audit_event")
    op.drop_index("ix_audit_event_request_id", table_name="audit_event")
    op.drop_column("audit_event", "effective_role_bindings")
    op.drop_column("audit_event", "actor_id")
    op.drop_column("audit_event", "actor_type")
    op.drop_column("audit_event", "request_id")
    op.drop_column("audit_event", "outcome")
    op.drop_table("corporate_provisioned_identity")
    op.drop_table("corporate_mutation_receipt")
    op.drop_table("corporate_bootstrap_receipt")
    op.drop_table("corporate_project_member")
    op.drop_table("corporate_team_member")
    op.drop_index("ix_corporate_team_organization_id", table_name="corporate_team")
    op.drop_table("corporate_team")
    op.drop_index("ix_corporate_project_organization_id", table_name="corporate_project")
    op.drop_table("corporate_project")
    op.drop_index(
        "uq_corporate_role_binding_active_service_scope", table_name="corporate_role_binding"
    )
    op.drop_index(
        "uq_corporate_role_binding_active_user_scope", table_name="corporate_role_binding"
    )
    op.drop_index(
        "ix_corporate_role_binding_service_principal_id", table_name="corporate_role_binding"
    )
    op.drop_index("ix_corporate_role_binding_account_id", table_name="corporate_role_binding")
    op.drop_index("ix_corporate_role_binding_organization_id", table_name="corporate_role_binding")
    op.drop_table("corporate_role_binding")
    op.drop_index(
        "ix_corporate_service_principal_organization_id",
        table_name="corporate_service_principal",
    )
    op.drop_table("corporate_service_principal")
    op.drop_table("corporate_role_permission")
    op.drop_table("corporate_role")
    op.drop_constraint("ck_organization_membership_role", "organization_membership", type_="check")
    op.create_check_constraint(
        "ck_organization_membership_role",
        "organization_membership",
        "role in ('owner', 'admin', 'member')",
    )
    op.drop_constraint("ck_organization_state", "organization", type_="check")
    op.drop_constraint("ck_organization_policy_revision", "organization", type_="check")
    op.drop_column("organization", "state")
    op.drop_column("organization", "policy_revision")
    op.drop_index("uq_job_global_idempotency", table_name="job")
    op.drop_index("uq_job_tenant_idempotency", table_name="job")
    op.create_unique_constraint("uq_job_idempotency_key", "job", ["idempotency_key"])
