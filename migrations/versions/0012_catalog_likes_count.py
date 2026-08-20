"""add public catalog likes aggregate

Revision ID: 0012_catalog_likes_count
Revises: 0011_catalog_support_evidence
Create Date: 2026-08-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_catalog_likes_count"
down_revision: str | None = "0011_catalog_support_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "catalog_metadata",
        sa.Column("likes_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_check_constraint(
        "ck_catalog_metadata_likes_count_non_negative",
        "catalog_metadata",
        "likes_count >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_catalog_metadata_likes_count_non_negative",
        "catalog_metadata",
        type_="check",
    )
    op.drop_column("catalog_metadata", "likes_count")
