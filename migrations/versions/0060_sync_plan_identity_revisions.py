"""Pin identity observations in sync plans."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0060_sync_plan_identity_revisions"
down_revision: str | None = "0059_project_ledger_and_ownership_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "project_sync_plan",
        sa.Column("remote_identity_revision", sa.Integer(), nullable=True),
    )
    op.add_column(
        "project_sync_plan",
        sa.Column("provider_identity_revision", sa.Integer(), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE project_sync_plan SET remote_identity_revision = 1 "
            "WHERE remote_identity_revision IS NULL"
        )
    )
    op.alter_column("project_sync_plan", "remote_identity_revision", nullable=False)


def downgrade() -> None:
    op.drop_column("project_sync_plan", "provider_identity_revision")
    op.drop_column("project_sync_plan", "remote_identity_revision")
