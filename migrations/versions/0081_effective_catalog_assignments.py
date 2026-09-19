"""Extend catalog assignments with selectors, harness conditions, and org scope."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0081_effective_catalog_assignments"
down_revision: str | None = "0080_corporate_audit_export_permission"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SUBJECT_SUM = (
    "(CASE WHEN account_id IS NULL THEN 0 ELSE 1 END + "
    "CASE WHEN team_id IS NULL THEN 0 ELSE 1 END + "
    "CASE WHEN project_id IS NULL THEN 0 ELSE 1 END + "
    "CASE WHEN technology_id IS NULL THEN 0 ELSE 1 END)"
)
_ORGANIZATION_SCOPE = (
    "account_id IS NULL AND team_id IS NULL AND project_id IS NULL AND technology_id IS NULL"
)


def upgrade() -> None:
    op.add_column(
        "corporate_catalog_assignment",
        sa.Column("selector", sa.String(8), server_default="exact", nullable=False),
    )
    op.add_column(
        "corporate_catalog_assignment",
        sa.Column("passport_digest", sa.String(80), nullable=True),
    )
    op.add_column(
        "corporate_catalog_assignment",
        sa.Column("harness", sa.String(64), nullable=True),
    )
    op.alter_column(
        "corporate_catalog_assignment",
        "version",
        existing_type=sa.String(32),
        nullable=True,
    )
    op.drop_constraint(
        "ck_corporate_assignment_subject", "corporate_catalog_assignment", type_="check"
    )
    op.create_check_constraint(
        "ck_corporate_assignment_subject",
        "corporate_catalog_assignment",
        f"{_SUBJECT_SUM} <= 1",
    )
    op.create_check_constraint(
        "ck_corporate_assignment_selector",
        "corporate_catalog_assignment",
        "selector in ('exact','latest')",
    )
    op.create_check_constraint(
        "ck_corporate_assignment_selector_version",
        "corporate_catalog_assignment",
        "selector = 'latest' OR version IS NOT NULL",
    )
    for subject in ("account", "team", "project", "technology"):
        op.drop_constraint(
            f"uq_corporate_assignment_{subject}",
            "corporate_catalog_assignment",
            type_="unique",
        )
        op.create_unique_constraint(
            f"uq_corporate_assignment_{subject}",
            "corporate_catalog_assignment",
            [
                "organization_id",
                f"{subject}_id",
                "object_kind",
                "stable_id",
                "version",
                "harness",
            ],
        )
    op.create_index(
        "uq_corporate_assignment_organization",
        "corporate_catalog_assignment",
        ["organization_id", "object_kind", "stable_id", "version", "harness"],
        unique=True,
        postgresql_where=sa.text(_ORGANIZATION_SCOPE),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_corporate_assignment_organization",
        table_name="corporate_catalog_assignment",
        postgresql_where=sa.text(_ORGANIZATION_SCOPE),
    )
    for subject in ("account", "team", "project", "technology"):
        op.drop_constraint(
            f"uq_corporate_assignment_{subject}",
            "corporate_catalog_assignment",
            type_="unique",
        )
        op.create_unique_constraint(
            f"uq_corporate_assignment_{subject}",
            "corporate_catalog_assignment",
            [
                "organization_id",
                f"{subject}_id",
                "object_kind",
                "stable_id",
                "version",
            ],
        )
    op.drop_constraint(
        "ck_corporate_assignment_selector_version",
        "corporate_catalog_assignment",
        type_="check",
    )
    op.drop_constraint(
        "ck_corporate_assignment_selector", "corporate_catalog_assignment", type_="check"
    )
    op.drop_constraint(
        "ck_corporate_assignment_subject", "corporate_catalog_assignment", type_="check"
    )
    op.create_check_constraint(
        "ck_corporate_assignment_subject",
        "corporate_catalog_assignment",
        f"{_SUBJECT_SUM} = 1",
    )
    op.execute("DELETE FROM corporate_catalog_assignment WHERE version IS NULL")
    op.alter_column(
        "corporate_catalog_assignment",
        "version",
        existing_type=sa.String(32),
        nullable=False,
    )
    op.drop_column("corporate_catalog_assignment", "harness")
    op.drop_column("corporate_catalog_assignment", "passport_digest")
    op.drop_column("corporate_catalog_assignment", "selector")
