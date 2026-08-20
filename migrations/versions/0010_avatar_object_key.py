"""avatar_asset object_key and content_digest for S3-backed media

Revision ID: 0010_avatar_object_key
Revises: 0009_public_profile_documents
Create Date: 2026-08-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_avatar_object_key"
down_revision: str | None = "0009_public_profile_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("avatar_asset", sa.Column("object_key", sa.String(length=512), nullable=True))
    op.add_column("avatar_asset", sa.Column("content_digest", sa.String(length=80), nullable=True))


def downgrade() -> None:
    op.drop_column("avatar_asset", "content_digest")
    op.drop_column("avatar_asset", "object_key")
