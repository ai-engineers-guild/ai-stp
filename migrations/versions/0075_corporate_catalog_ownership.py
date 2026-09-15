"""Retained tenant operational owners do not transfer catalog authorship."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0075_corporate_catalog_ownership"
down_revision: str | None = "0074_corporate_entity_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "corporate_catalog_ownership",
        sa.Column(
            "organization_id",
            sa.String(64),
            sa.ForeignKey("organization.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("object_kind", sa.String(32), primary_key=True),
        sa.Column("stable_id", sa.String(64), primary_key=True),
        sa.Column("owner_account_id", sa.String(64), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["organization_id", "owner_account_id"],
            ["organization_membership.organization_id", "organization_membership.account_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "object_kind IN ('setup','component')", name="ck_catalog_ownership_kind"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_catalog_ownership_revision"),
    )


def downgrade() -> None:
    """Explicit schema downgrade is destructive; application rollback retains owners."""
    op.drop_table("corporate_catalog_ownership")
