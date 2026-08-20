"""drop derived github archive cache tables

Revision ID: 0024_drop_github_archive_cache
Revises: 0023_github_archive_observation
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_drop_github_archive_cache"
down_revision: str | None = "0023_github_archive_observation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_github_archive_history_source_fetched", table_name="github_archive_history")
    op.drop_table("github_archive_history")
    op.drop_table("github_archive_latest")


def downgrade() -> None:
    op.create_table(
        "github_archive_latest",
        sa.Column("source_repository", sa.String(length=512), nullable=False),
        sa.Column("repository_id", sa.BigInteger(), nullable=True),
        sa.Column("repository_full_name", sa.String(length=256), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=True),
        sa.Column("etag", sa.String(length=256), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_kind", sa.String(length=32), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("source_repository"),
        sa.CheckConstraint(
            "repository_id is null or repository_id > 0",
            name="ck_github_archive_latest_repository_id",
        ),
    )
    op.create_table(
        "github_archive_history",
        sa.Column("observation_id", sa.Integer(), nullable=False),
        sa.Column("source_repository", sa.String(length=512), nullable=False),
        sa.Column("repository_id", sa.BigInteger(), nullable=False),
        sa.Column("repository_full_name", sa.String(length=256), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("etag", sa.String(length=256), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("response_kind", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("observation_id"),
        sa.CheckConstraint(
            "repository_id > 0",
            name="ck_github_archive_history_repository_id",
        ),
        sa.CheckConstraint(
            "response_kind in ('modified', 'not_modified')",
            name="ck_github_archive_history_response_kind",
        ),
    )
    op.create_index(
        "ix_github_archive_history_source_fetched",
        "github_archive_history",
        ["source_repository", "fetched_at"],
    )
