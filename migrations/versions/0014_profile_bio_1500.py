"""expand public profile bio to 1500 characters

Revision ID: 0014_profile_bio_1500
Revises: 0013_account_privacy_preferences
Create Date: 2026-08-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_profile_bio_1500"
down_revision: str | None = "0013_account_privacy_preferences"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "profile_revision",
        "bio",
        existing_type=sa.String(length=500),
        type_=sa.String(length=1500),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "profile_revision",
        "bio",
        existing_type=sa.String(length=1500),
        type_=sa.String(length=500),
        existing_nullable=True,
    )
