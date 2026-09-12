"""Allow tenant-local roles to be managed without weakening the RBAC boundary.

Built-in roles remain seeded by corporate bootstrap. Custom roles use the same
persisted permission table and evaluator, so role names never become a bypass.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0065_dynamic_corporate_roles"
down_revision: str | None = "0064_corporate_relationship_tenant_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_organization_membership_role", "organization_membership", type_="check")
    op.create_check_constraint(
        "ck_organization_membership_role",
        "organization_membership",
        "length(role) between 1 and 64",
    )
    for table_name, constraint_name in (
        ("corporate_role_binding", "ck_role_binding_role"),
        ("corporate_role_permission", "ck_role_permission_role"),
        ("corporate_role", "ck_corporate_role_name"),
        ("corporate_role", "ck_corporate_role_parent"),
    ):
        op.drop_constraint(constraint_name, table_name, type_="check")
    for table_name, column_name in (
        ("organization_membership", "role"),
        ("corporate_role_binding", "role"),
        ("corporate_role_permission", "role"),
        ("corporate_role", "name"),
        ("corporate_role", "parent_role"),
    ):
        op.alter_column(table_name, column_name, type_=sa.String(64))
    op.add_column(
        "corporate_role",
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_foreign_key(
        "fk_corporate_role_permission_role",
        "corporate_role_permission",
        "corporate_role",
        ["organization_id", "role"],
        ["organization_id", "name"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_corporate_role_binding_role",
        "corporate_role_binding",
        "corporate_role",
        ["organization_id", "role"],
        ["organization_id", "name"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint("ck_corporate_role_revision", "corporate_role", "revision >= 1")


def downgrade() -> None:
    op.drop_constraint("ck_corporate_role_revision", "corporate_role", type_="check")
    op.drop_constraint(
        "fk_corporate_role_binding_role", "corporate_role_binding", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_corporate_role_permission_role", "corporate_role_permission", type_="foreignkey"
    )
    op.drop_column("corporate_role", "revision")
    for table_name, column_name in (
        ("organization_membership", "role"),
        ("corporate_role_binding", "role"),
        ("corporate_role_permission", "role"),
        ("corporate_role", "name"),
        ("corporate_role", "parent_role"),
    ):
        op.alter_column(table_name, column_name, type_=sa.String(16))
    op.create_check_constraint(
        "ck_corporate_role_parent",
        "corporate_role",
        "parent_role is null or parent_role in ('superadmin', 'lead')",
    )
    op.create_check_constraint(
        "ck_corporate_role_name",
        "corporate_role",
        "name in ('superadmin', 'lead', 'staff')",
    )
    op.create_check_constraint(
        "ck_role_permission_role",
        "corporate_role_permission",
        "role in ('superadmin', 'lead', 'staff')",
    )
    op.create_check_constraint(
        "ck_role_binding_role",
        "corporate_role_binding",
        "role in ('superadmin', 'lead', 'staff')",
    )
    op.drop_constraint("ck_organization_membership_role", "organization_membership", type_="check")
    op.create_check_constraint(
        "ck_organization_membership_role",
        "organization_membership",
        "role in ('owner', 'admin', 'member', 'superadmin', 'lead', 'staff')",
    )
