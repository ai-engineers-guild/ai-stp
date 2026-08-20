"""add component media and catalog reactions

Revision ID: 0015_component_media_reactions
Revises: 0014_profile_bio_1500
Create Date: 2026-08-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_component_media_reactions"
down_revision: str | None = "0014_profile_bio_1500"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "component_media",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("stable_id", sa.String(64), nullable=False),
        sa.Column(
            "owner_account_id",
            sa.String(64),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("state", sa.String(16), server_default="pending", nullable=False),
        sa.Column("object_key", sa.String(512)),
        sa.Column("public_url", sa.String(2048)),
        sa.Column("github_commit", sa.String(64)),
        sa.Column("youtube_video_id", sa.String(11)),
        sa.Column("content_type", sa.String(64)),
        sa.Column("size_bytes", sa.Integer()),
        sa.Column("alt", sa.String(240), nullable=False),
        sa.Column("caption", sa.String(500)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("stable_id", "position", name="uq_component_media_position"),
        sa.CheckConstraint("position >= 0 and position < 5", name="ck_component_media_position"),
        sa.CheckConstraint("kind in ('image', 'video', 'youtube')", name="ck_component_media_kind"),
        sa.CheckConstraint(
            "source_type in ('upload', 'github', 'youtube')", name="ck_component_media_source_type"
        ),
        sa.CheckConstraint(
            "size_bytes is null or size_bytes <= 26214400", name="ck_component_media_size"
        ),
    )
    op.create_index("ix_component_media_stable_id", "component_media", ["stable_id"])
    op.create_index("ix_component_media_owner_account_id", "component_media", ["owner_account_id"])
    op.create_table(
        "catalog_reaction",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "account_id",
            sa.String(64),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("object_kind", sa.String(16), nullable=False),
        sa.Column("stable_id", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "account_id", "object_kind", "stable_id", name="uq_catalog_reaction_account_object"
        ),
        sa.CheckConstraint(
            "object_kind in ('component', 'setup')", name="ck_catalog_reaction_kind"
        ),
    )
    op.create_index("ix_catalog_reaction_account_id", "catalog_reaction", ["account_id"])
    op.create_index("ix_catalog_reaction_stable_id", "catalog_reaction", ["stable_id"])


def downgrade() -> None:
    op.drop_table("catalog_reaction")
    op.drop_table("component_media")
