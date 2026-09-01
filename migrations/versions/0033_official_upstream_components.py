"""official GitHub upstream source and sync state

Revision ID: 0033_official_upstream
Revises: 0032_legal_onboarding
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033_official_upstream"
down_revision: str | None = "0032_legal_onboarding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "official_upstream_source",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("slot", sa.String(length=16), server_default="official", nullable=False),
        sa.Column("repository_url", sa.String(length=512), nullable=False),
        sa.Column("tracked_ref", sa.String(length=256), nullable=False),
        sa.Column("component_subpath", sa.String(length=512), nullable=False),
        sa.Column("component_type", sa.String(length=32), nullable=False),
        sa.Column(
            "projection_kind",
            sa.String(length=32),
            server_default="native_files",
            nullable=False,
        ),
        sa.Column("harness_id", sa.String(length=32), nullable=False),
        sa.Column("owner_account_id", sa.String(length=64), nullable=False),
        sa.Column("actor_device_id", sa.String(length=64), nullable=False),
        sa.Column("stable_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("upstream_project_name", sa.String(length=200), nullable=False),
        sa.Column("upstream_maintainer", sa.String(length=200), nullable=False),
        sa.Column("reviewed_description", sa.Text(), nullable=False),
        sa.Column("reviewed_license", sa.String(length=64), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("last_github_repo_id", sa.BigInteger(), nullable=True),
        sa.Column("last_commit", sa.String(length=40), nullable=True),
        sa.Column("last_archive_digest", sa.String(length=71), nullable=True),
        sa.Column("last_component_digest", sa.String(length=71), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("slot = 'official'", name="ck_official_upstream_source_slot"),
        sa.CheckConstraint(
            "component_type in ("
            "'instruction', 'skill', 'mcp', 'hook', 'command', 'agent', 'plugin', 'setting')",
            name="ck_official_upstream_source_component_type",
        ),
        sa.CheckConstraint(
            "projection_kind in ('marketplace', 'plugin', 'native_files', 'package')",
            name="ck_official_upstream_source_projection_kind",
        ),
        sa.ForeignKeyConstraint(["owner_account_id"], ["account.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slot", name="uq_official_upstream_source_slot"),
        sa.UniqueConstraint("stable_id"),
    )
    op.create_index(
        "ix_official_upstream_source_owner_account_id",
        "official_upstream_source",
        ["owner_account_id"],
    )
    op.create_table(
        "official_upstream_sync",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("utc_day", sa.Date(), nullable=False),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("commit", sa.String(length=40), nullable=True),
        sa.Column("archive_digest", sa.String(length=71), nullable=True),
        sa.Column("component_digest", sa.String(length=71), nullable=True),
        sa.Column("observed_license", sa.String(length=64), nullable=True),
        sa.Column("github_owner", sa.String(length=256), nullable=True),
        sa.Column("github_name", sa.String(length=256), nullable=True),
        sa.Column("github_repo_id", sa.BigInteger(), nullable=True),
        sa.Column("plan_id", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "result in ('unchanged', 'publication_started', 'failed')",
            name="ck_official_upstream_sync_result",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "utc_day", name="uq_official_upstream_sync_source_day"),
    )
    op.create_index("ix_official_upstream_sync_source_id", "official_upstream_sync", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_official_upstream_sync_source_id", table_name="official_upstream_sync")
    op.drop_table("official_upstream_sync")
    op.drop_index(
        "ix_official_upstream_source_owner_account_id", table_name="official_upstream_source"
    )
    op.drop_table("official_upstream_source")
