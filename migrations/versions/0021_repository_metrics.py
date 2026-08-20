"""repository metrics cache

Revision ID: 0021_repository_metrics
Revises: 0020_safety_scan
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_repository_metrics"
down_revision: str | None = "0020_safety_scan"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "repository_metric",
        sa.Column("repository", sa.String(length=512), nullable=False),
        sa.Column("github_stars", sa.Integer(), nullable=True),
        sa.Column("etag", sa.String(length=256), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_count", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint(
            "github_stars is null or github_stars >= 0", name="ck_repository_metric_stars"
        ),
        sa.PrimaryKeyConstraint("repository"),
    )


def downgrade() -> None:
    op.drop_table("repository_metric")
