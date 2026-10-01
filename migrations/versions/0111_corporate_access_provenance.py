"""Binding provenance/coverage and direct permission grants (ADR-0220).

`origin` records which write path owns a binding so membership
synchronization can no longer consume independently granted rows. `coverage`
makes the organization-scope descendant reach explicit data instead of a
role-name check in the evaluator; only rows named `superadmin` propagated
before, so only those are backfilled to 'descendants'. Unclassifiable rows
keep 'direct'/'self', which preserves their prior effective behavior.

`corporate_permission_grant` is the tenant-scoped, action-scoped, revocable
direct allow: one permission, no role, no descendant propagation.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0111_corporate_access_provenance"
down_revision: str | Sequence[str] | None = "0110_invitation_email_confirmation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "corporate_role_binding",
        sa.Column("origin", sa.String(24), nullable=False, server_default="direct"),
    )
    op.add_column(
        "corporate_role_binding",
        sa.Column("coverage", sa.String(16), nullable=False, server_default="self"),
    )
    op.execute(
        sa.text(
            "UPDATE corporate_role_binding SET coverage = 'descendants' "
            "WHERE scope_kind = 'organization' AND role = 'superadmin'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE corporate_role_binding SET origin = 'service_principal' "
            "WHERE principal_type = 'service_principal'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE corporate_role_binding b SET origin = 'membership' "
            "FROM organization_membership m "
            "WHERE b.principal_type = 'user' "
            "AND b.organization_id = m.organization_id "
            "AND b.account_id = m.account_id "
            "AND b.scope_kind = 'organization' AND b.role = m.role"
        )
    )
    op.execute(
        sa.text(
            "UPDATE corporate_role_binding b SET origin = 'assignment' "
            "FROM corporate_team_member t "
            "WHERE b.principal_type = 'user' AND b.origin = 'direct' "
            "AND b.organization_id = t.organization_id "
            "AND b.account_id = t.account_id "
            "AND b.scope_kind = 'team' AND b.scope_id = t.team_id "
            "AND b.role = t.role"
        )
    )
    op.execute(
        sa.text(
            "UPDATE corporate_role_binding b SET origin = 'assignment' "
            "FROM corporate_project_member p "
            "WHERE b.principal_type = 'user' AND b.origin = 'direct' "
            "AND b.organization_id = p.organization_id "
            "AND b.account_id = p.account_id "
            "AND b.scope_kind = 'project' AND b.scope_id = p.project_id"
        )
    )
    op.create_check_constraint(
        "ck_role_binding_origin",
        "corporate_role_binding",
        "origin in ('membership', 'assignment', 'direct', 'service_principal')",
    )
    op.create_check_constraint(
        "ck_role_binding_coverage",
        "corporate_role_binding",
        "coverage in ('self', 'descendants')",
    )
    op.create_table(
        "corporate_permission_grant",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(64),
            sa.ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("principal_type", sa.String(24), nullable=False),
        sa.Column(
            "account_id",
            sa.String(64),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("service_principal_id", sa.String(64), nullable=True),
        sa.Column("permission", sa.String(64), nullable=False),
        sa.Column("scope_kind", sa.String(32), nullable=False),
        sa.Column("scope_id", sa.String(64), nullable=False),
        sa.Column(
            "issuer_account_id",
            sa.String(64),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "service_principal_id"],
            [
                "corporate_service_principal.organization_id",
                "corporate_service_principal.id",
            ],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "account_id"],
            [
                "organization_membership.organization_id",
                "organization_membership.account_id",
            ],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "scope_kind in ('system', 'organization', 'team', 'project', 'technology', "
            "'catalog_object', 'telemetry')",
            name="ck_permission_grant_scope_kind",
        ),
        sa.CheckConstraint("state in ('active', 'revoked')", name="ck_permission_grant_state"),
        sa.CheckConstraint(
            "(principal_type = 'user' AND account_id IS NOT NULL "
            "AND service_principal_id IS NULL) OR "
            "(principal_type = 'service_principal' AND account_id IS NULL "
            "AND service_principal_id IS NOT NULL)",
            name="ck_permission_grant_principal",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_permission_grant_revision"),
    )
    op.create_index(
        "ix_corporate_permission_grant_organization_id",
        "corporate_permission_grant",
        ["organization_id"],
    )
    op.create_index(
        "ix_corporate_permission_grant_account_id",
        "corporate_permission_grant",
        ["account_id"],
    )
    op.create_index(
        "ix_corporate_permission_grant_service_principal_id",
        "corporate_permission_grant",
        ["service_principal_id"],
    )
    op.create_index(
        "uq_corporate_permission_grant_active_user_scope",
        "corporate_permission_grant",
        ["organization_id", "account_id", "permission", "scope_kind", "scope_id"],
        unique=True,
        postgresql_where=sa.text("state = 'active' AND principal_type = 'user'"),
    )
    op.create_index(
        "uq_corporate_permission_grant_active_service_scope",
        "corporate_permission_grant",
        ["organization_id", "service_principal_id", "permission", "scope_kind", "scope_id"],
        unique=True,
        postgresql_where=sa.text("state = 'active' AND principal_type = 'service_principal'"),
    )


def downgrade() -> None:
    op.drop_table("corporate_permission_grant")
    op.drop_constraint("ck_role_binding_coverage", "corporate_role_binding", type_="check")
    op.drop_constraint("ck_role_binding_origin", "corporate_role_binding", type_="check")
    op.drop_column("corporate_role_binding", "coverage")
    op.drop_column("corporate_role_binding", "origin")
