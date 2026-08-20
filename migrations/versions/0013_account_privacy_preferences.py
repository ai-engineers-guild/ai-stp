"""add account privacy preferences

Revision ID: 0013_account_privacy_preferences
Revises: 0012_catalog_likes_count
Create Date: 2026-08-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_account_privacy_preferences"
down_revision: str | None = "0012_catalog_likes_count"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "account",
        sa.Column("show_profile_publicly", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column(
        "account",
        sa.Column(
            "allow_publisher_listing", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("account", "allow_publisher_listing")
    op.drop_column("account", "show_profile_publicly")
