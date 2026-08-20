"""add GitHub username recipient resolution for direct grants

Revision ID: 0016_github_username_grants
Revises: 0015_component_media_reactions
Create Date: 2026-08-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_github_username_grants"
down_revision: str | None = "0015_component_media_reactions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oauth_identity_alias",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "oauth_identity_id",
            sa.Integer(),
            sa.ForeignKey("oauth_identity.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("normalized_value", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("oauth_identity_id", name="uq_oauth_identity_alias_identity"),
        sa.UniqueConstraint("provider", "normalized_value", name="uq_oauth_identity_alias_value"),
    )
    op.create_index(
        "ix_oauth_identity_alias_oauth_identity_id",
        "oauth_identity_alias",
        ["oauth_identity_id"],
    )
    op.create_table(
        "grant_recipient_reference",
        sa.Column(
            "grant_id",
            sa.String(64),
            sa.ForeignKey("access_grant.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("identifier_kind", sa.String(32), nullable=False),
        sa.Column("identifier_value", sa.String(320), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("grant_recipient_reference")
    op.drop_table("oauth_identity_alias")
