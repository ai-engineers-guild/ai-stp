"""Enforce tenant-compatible corporate account relationships.

Revision ID: 0064_corporate_relationship_tenant_keys
Revises: 0063_corporate_core
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0064_corporate_relationship_tenant_keys"
down_revision: str | None = "0063_corporate_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table_name in (
        "corporate_role_binding",
        "corporate_team_member",
        "corporate_project_member",
    ):
        op.create_foreign_key(
            f"fk_{table_name}_tenant_account",
            table_name,
            "organization_membership",
            ["organization_id", "account_id"],
            ["organization_id", "account_id"],
            ondelete="CASCADE",
        )
    op.create_check_constraint("ck_corporate_team_revision", "corporate_team", "revision >= 1")


def downgrade() -> None:
    op.drop_constraint("ck_corporate_team_revision", "corporate_team", type_="check")
    for table_name in (
        "corporate_project_member",
        "corporate_team_member",
        "corporate_role_binding",
    ):
        op.drop_constraint(f"fk_{table_name}_tenant_account", table_name, type_="foreignkey")
