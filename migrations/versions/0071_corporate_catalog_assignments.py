"""Persist exact catalog assignments independently from access grants."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0071_corporate_catalog_assignments"
down_revision: str | None = "0070_project_source_availability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "corporate_catalog_assignment",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(64),
            sa.ForeignKey("organization.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("account_id", sa.String(64)),
        sa.Column("team_id", sa.String(64)),
        sa.Column("project_id", sa.String(64)),
        sa.Column("object_kind", sa.String(32), nullable=False),
        sa.Column("stable_id", sa.String(64), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="current"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "object_kind in ('setup','component')", name="ck_corporate_assignment_kind"
        ),
        sa.CheckConstraint("state in ('current','retired')", name="ck_corporate_assignment_state"),
        sa.CheckConstraint("revision >= 1", name="ck_corporate_assignment_revision"),
        sa.CheckConstraint(
            "(CASE WHEN account_id IS NULL THEN 0 ELSE 1 END + "
            "CASE WHEN team_id IS NULL THEN 0 ELSE 1 END + "
            "CASE WHEN project_id IS NULL THEN 0 ELSE 1 END) = 1",
            name="ck_corporate_assignment_subject",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "account_id"],
            ["organization_membership.organization_id", "organization_membership.account_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "team_id"],
            ["corporate_team.organization_id", "corporate_team.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["corporate_project.organization_id", "corporate_project.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["object_kind", "stable_id", "version"],
            [
                "catalog_metadata.object_kind",
                "catalog_metadata.stable_id",
                "catalog_metadata.version",
            ],
            ondelete="RESTRICT",
        ),
        *[
            sa.UniqueConstraint(
                "organization_id",
                subject,
                "object_kind",
                "stable_id",
                "version",
                name=f"uq_corporate_assignment_{subject.removesuffix('_id')}",
            )
            for subject in ("account_id", "team_id", "project_id")
        ],
    )
    op.create_index(
        "ix_corporate_catalog_assignment_organization_id",
        "corporate_catalog_assignment",
        ["organization_id"],
    )


def downgrade() -> None:
    """Explicit schema downgrade removes assignments; application rollback retains them."""
    op.drop_table("corporate_catalog_assignment")
