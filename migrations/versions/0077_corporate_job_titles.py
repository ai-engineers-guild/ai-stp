"""Add organization-governed job titles and the nullable membership reference."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0077_corporate_job_titles"
down_revision: str | None = "0076_milestone5_corporate_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "corporate_job_title",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("normalized_name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(2000), nullable=False, server_default=""),
        sa.Column("state", sa.String(16), nullable=False, server_default="current"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("organization_id", "id"),
        sa.UniqueConstraint(
            "organization_id", "normalized_name", name="uq_corporate_job_title_name"
        ),
        sa.CheckConstraint("state in ('current', 'retired')", name="ck_corporate_job_title_state"),
        sa.CheckConstraint("revision >= 1", name="ck_corporate_job_title_revision"),
    )
    op.create_index(
        "ix_corporate_job_title_organization_id", "corporate_job_title", ["organization_id"]
    )
    op.add_column(
        "organization_membership", sa.Column("job_title_id", sa.String(64), nullable=True)
    )
    op.create_index(
        "ix_organization_membership_job_title_id", "organization_membership", ["job_title_id"]
    )
    op.create_foreign_key(
        "fk_organization_membership_job_title",
        "organization_membership",
        "corporate_job_title",
        ["organization_id", "job_title_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    # The optional projection cannot survive removal of this additive feature.
    op.execute(sa.text("UPDATE organization_membership SET job_title_id = NULL"))
    op.drop_constraint(
        "fk_organization_membership_job_title", "organization_membership", type_="foreignkey"
    )
    op.drop_index("ix_organization_membership_job_title_id", table_name="organization_membership")
    op.drop_column("organization_membership", "job_title_id")
    op.drop_index("ix_corporate_job_title_organization_id", table_name="corporate_job_title")
    op.drop_table("corporate_job_title")
