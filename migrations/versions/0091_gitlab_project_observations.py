"""Retain provider branch and revision with the canonical project identity."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0091_gitlab_project_observations"
down_revision: str | None = "0090_telemetry_privacy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("project_identity", sa.Column("provider_default_branch", sa.String(128)))
    op.add_column("project_identity", sa.Column("provider_observed_revision", sa.String(128)))


def downgrade() -> None:
    op.drop_column("project_identity", "provider_observed_revision")
    op.drop_column("project_identity", "provider_default_branch")
