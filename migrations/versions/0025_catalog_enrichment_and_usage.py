"""catalog metadata observations and privacy-safe usage counters

Revision ID: 0025_catalog_metrics
Revises: 0024_drop_github_archive_cache
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_catalog_metrics"
down_revision: str | None = "0024_drop_github_archive_cache"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalog_external_observation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("catalog_metadata_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_identifier", sa.String(length=512), nullable=False),
        sa.Column("dedup_key", sa.String(length=1024), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column("attribution", sa.String(length=256), nullable=False),
        sa.Column("terms_url", sa.String(length=2048), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("freshness", sa.String(length=16), nullable=False),
        sa.Column("display_name", sa.String(length=4096), nullable=True),
        sa.Column("summary", sa.String(length=4096), nullable=True),
        sa.Column("homepage_url", sa.String(length=2048), nullable=True),
        sa.Column("repository_url", sa.String(length=2048), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("popularity_count", sa.Integer(), nullable=True),
        sa.Column("external_state", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(
            ["catalog_metadata_id"],
            ["catalog_metadata.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "catalog_metadata_id",
            "provider",
            "external_identifier",
            name="uq_catalog_external_observation_identity",
        ),
        sa.CheckConstraint(
            "provider in ('skills_sh', 'nori', 'modelcontextprotocol')",
            name="ck_catalog_external_observation_provider",
        ),
        sa.CheckConstraint(
            "freshness in ('fresh', 'stale', 'unavailable')",
            name="ck_catalog_external_observation_freshness",
        ),
        sa.CheckConstraint(
            "external_state in ('present', 'archived', 'unavailable')",
            name="ck_catalog_external_observation_external_state",
        ),
        sa.CheckConstraint(
            "popularity_count is null or popularity_count >= 0",
            name="ck_catalog_external_observation_popularity",
        ),
    )
    op.create_index(
        "ix_catalog_external_observation_metadata",
        "catalog_external_observation",
        ["catalog_metadata_id"],
    )
    op.create_table(
        "catalog_usage_aggregate",
        sa.Column("stable_id", sa.String(length=64), nullable=False),
        sa.Column("detail_views_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("artifact_downloads_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("stable_id"),
        sa.CheckConstraint(
            "detail_views_count >= 0 and artifact_downloads_count >= 0",
            name="ck_catalog_usage_aggregate_counts",
        ),
    )
    op.create_table(
        "catalog_usage_dedup",
        sa.Column("dedup_key", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("dedup_key"),
        sa.CheckConstraint(
            "dedup_key ~ '^[0-9a-f]{64}$'",
            name="ck_catalog_usage_dedup_key",
        ),
    )
    op.create_index(
        "ix_catalog_usage_dedup_expires_at",
        "catalog_usage_dedup",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_usage_dedup_expires_at", table_name="catalog_usage_dedup")
    op.drop_table("catalog_usage_dedup")
    op.drop_table("catalog_usage_aggregate")
    op.drop_index(
        "ix_catalog_external_observation_metadata",
        table_name="catalog_external_observation",
    )
    op.drop_table("catalog_external_observation")
