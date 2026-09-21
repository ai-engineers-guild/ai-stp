"""Per-target derived records for bulk corporate assignment distribution."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0082_bulk_assignment_distribution"
down_revision: str | None = "0081_effective_catalog_assignments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "corporate_assignment_distribution",
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("source_assignment_id", sa.String(64), nullable=False),
        sa.Column("target_kind", sa.String(16), nullable=False),
        sa.Column("target_id", sa.String(64), nullable=False),
        sa.Column("operation_revision", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(8), nullable=False),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("state", sa.String(16), nullable=True),
        sa.Column("diagnostic", sa.String(200), nullable=True),
        sa.Column("overriding_assignment_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint(
            "organization_id",
            "source_assignment_id",
            "target_kind",
            "target_id",
            "operation_revision",
        ),
        sa.CheckConstraint(
            "target_kind in ('employee','project')", name="ck_distribution_target_kind"
        ),
        sa.CheckConstraint("action in ('assign','revoke')", name="ck_distribution_action"),
        sa.CheckConstraint(
            "result in ('applied','skipped','conflicted','denied','failed')",
            name="ck_distribution_result",
        ),
        sa.CheckConstraint(
            "state in ('pending','installed','outdated','failed','revoked')",
            name="ck_distribution_state",
        ),
        sa.CheckConstraint("operation_revision >= 1", name="ck_distribution_operation_revision"),
        sa.ForeignKeyConstraint(
            ["source_assignment_id"],
            ["corporate_catalog_assignment.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            ondelete="RESTRICT",
        ),
    )


def downgrade() -> None:
    op.drop_table("corporate_assignment_distribution")
