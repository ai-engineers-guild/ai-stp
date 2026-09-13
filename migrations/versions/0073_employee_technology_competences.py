"""Retain tenant-scoped employee technology competence links."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0073_employee_technology_competences"
down_revision: str | None = "0072_tenant_member_display_names"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "employee_technology",
        sa.Column(
            "organization_id",
            sa.String(64),
            sa.ForeignKey("organization.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("technology_id", sa.String(64), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="current"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint(
            "organization_id", "account_id", "technology_id", name="uq_employee_technology"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "account_id"],
            ["organization_membership.organization_id", "organization_membership.account_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "technology_id"],
            ["technology.organization_id", "technology.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("state IN ('current','retired')", name="ck_employee_technology_state"),
        sa.CheckConstraint("revision >= 1", name="ck_employee_technology_revision"),
    )
    op.create_index(
        "ix_employee_technology_account", "employee_technology", ["organization_id", "account_id"]
    )
    op.create_index(
        "ix_employee_technology_technology",
        "employee_technology",
        ["organization_id", "technology_id"],
    )


def downgrade() -> None:
    """Explicit schema downgrade is destructive; application rollback retains links."""
    op.drop_table("employee_technology")
