"""Persistent tenant presentation and independent technology owners."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0074_corporate_entity_profiles"
down_revision: str | None = "0073_employee_technology_competences"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("organization_membership", "corporate_team", "corporate_project", "technology")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column("profile", sa.JSON(), nullable=False, server_default="{}"))
        op.add_column(
            table, sa.Column("profile_revision", sa.Integer(), nullable=False, server_default="0")
        )
        op.create_check_constraint(f"ck_{table}_profile_revision", table, "profile_revision >= 0")
    op.add_column("technology", sa.Column("owner_account_id", sa.String(64), nullable=True))
    op.create_foreign_key(
        "fk_technology_owner_membership",
        "technology",
        "organization_membership",
        ["organization_id", "owner_account_id"],
        ["organization_id", "account_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_technology_owner_membership", "technology", type_="foreignkey")
    op.drop_column("technology", "owner_account_id")
    for table in reversed(TABLES):
        op.drop_constraint(f"ck_{table}_profile_revision", table, type_="check")
        op.drop_column(table, "profile_revision")
        op.drop_column(table, "profile")
