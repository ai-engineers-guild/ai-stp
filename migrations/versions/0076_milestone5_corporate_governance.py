"""Add retained corporate governance relations and technology assignments."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0076_milestone5_corporate_governance"
down_revision: str | None = "0075_corporate_catalog_ownership"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "corporate_catalog_ownership",
        sa.Column("owner_kind", sa.String(16), nullable=False, server_default="employee"),
    )
    op.add_column(
        "corporate_catalog_ownership",
        sa.Column("owner_id", sa.String(64), nullable=True),
    )
    op.execute(
        "UPDATE corporate_catalog_ownership SET owner_id = owner_account_id WHERE owner_id IS NULL"
    )
    op.create_check_constraint(
        "ck_catalog_ownership_owner_kind",
        "corporate_catalog_ownership",
        "owner_kind IN ('organization','team','project','technology','employee')",
    )
    op.drop_constraint(
        "ck_corporate_assignment_subject", "corporate_catalog_assignment", type_="check"
    )
    op.drop_constraint(
        "uq_corporate_assignment_project", "corporate_catalog_assignment", type_="unique"
    )
    op.add_column(
        "corporate_catalog_assignment",
        sa.Column("technology_id", sa.String(64), nullable=True),
    )
    op.create_foreign_key(
        "fk_corporate_assignment_technology",
        "corporate_catalog_assignment",
        "technology",
        ["organization_id", "technology_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_corporate_assignment_subject",
        "corporate_catalog_assignment",
        "(CASE WHEN account_id IS NULL THEN 0 ELSE 1 END + "
        "CASE WHEN team_id IS NULL THEN 0 ELSE 1 END + "
        "CASE WHEN project_id IS NULL THEN 0 ELSE 1 END + "
        "CASE WHEN technology_id IS NULL THEN 0 ELSE 1 END) = 1",
    )
    op.create_unique_constraint(
        "uq_corporate_assignment_project",
        "corporate_catalog_assignment",
        ["organization_id", "project_id", "object_kind", "stable_id", "version"],
    )
    op.create_unique_constraint(
        "uq_corporate_assignment_technology",
        "corporate_catalog_assignment",
        ["organization_id", "technology_id", "object_kind", "stable_id", "version"],
    )

    op.create_table(
        "corporate_catalog_maintainer",
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("object_kind", sa.String(32), nullable=False),
        sa.Column("stable_id", sa.String(64), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("subject_kind", sa.String(16), nullable=False),
        sa.Column("subject_id", sa.String(64), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="current"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("actor_account_id", sa.String(64), nullable=True),
        sa.Column("reason", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint(
            "organization_id", "object_kind", "stable_id", "version", "subject_kind", "subject_id"
        ),
        sa.CheckConstraint(
            "object_kind in ('setup','component')", name="ck_catalog_maintainer_kind"
        ),
        sa.CheckConstraint(
            "subject_kind in ('employee','team')", name="ck_catalog_maintainer_subject"
        ),
        sa.CheckConstraint("state in ('current','retired')", name="ck_catalog_maintainer_state"),
        sa.CheckConstraint("revision >= 1", name="ck_catalog_maintainer_revision"),
    )
    for table, state_name, state_values in (
        (
            "corporate_catalog_verification",
            "ck_corporate_verification_state",
            "('verified','revoked')",
        ),
        (
            "corporate_catalog_lifecycle",
            "ck_corporate_lifecycle_state",
            "('visible','hidden','deprecated','retired')",
        ),
    ):
        columns = [
            sa.Column("organization_id", sa.String(64), nullable=False),
            sa.Column("object_kind", sa.String(32), nullable=False),
            sa.Column("stable_id", sa.String(64), nullable=False),
            sa.Column("version", sa.String(32), nullable=False),
            sa.Column("state", sa.String(16), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("reason", sa.String(200), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        ]
        if table.endswith("verification"):
            columns.append(sa.Column("verified_by_account_id", sa.String(64), nullable=True))
        else:
            columns.append(sa.Column("actor_account_id", sa.String(64), nullable=True))
        op.create_table(
            table,
            *columns,
            sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("organization_id", "object_kind", "stable_id", "version"),
            sa.CheckConstraint(
                "object_kind in ('setup','component')", name=state_name.replace("state", "kind")
            ),
            sa.CheckConstraint(f"state in {state_values}", name=state_name),
            sa.CheckConstraint("revision >= 1", name=state_name.replace("state", "revision")),
        )


def downgrade() -> None:
    op.drop_constraint(
        "ck_catalog_ownership_owner_kind", "corporate_catalog_ownership", type_="check"
    )
    op.drop_column("corporate_catalog_ownership", "owner_id")
    op.drop_column("corporate_catalog_ownership", "owner_kind")
    op.drop_table("corporate_catalog_lifecycle")
    op.drop_table("corporate_catalog_verification")
    op.drop_table("corporate_catalog_maintainer")
    op.drop_constraint(
        "uq_corporate_assignment_technology", "corporate_catalog_assignment", type_="unique"
    )
    op.drop_constraint(
        "uq_corporate_assignment_project", "corporate_catalog_assignment", type_="unique"
    )
    op.drop_constraint(
        "ck_corporate_assignment_subject", "corporate_catalog_assignment", type_="check"
    )
    op.drop_constraint(
        "fk_corporate_assignment_technology", "corporate_catalog_assignment", type_="foreignkey"
    )
    op.drop_column("corporate_catalog_assignment", "technology_id")
    op.create_check_constraint(
        "ck_corporate_assignment_subject",
        "corporate_catalog_assignment",
        "(CASE WHEN account_id IS NULL THEN 0 ELSE 1 END + "
        "CASE WHEN team_id IS NULL THEN 0 ELSE 1 END + "
        "CASE WHEN project_id IS NULL THEN 0 ELSE 1 END) = 1",
    )
    op.create_unique_constraint(
        "uq_corporate_assignment_project",
        "corporate_catalog_assignment",
        ["organization_id", "project_id", "object_kind", "stable_id", "version"],
    )
