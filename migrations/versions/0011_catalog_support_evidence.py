"""safe public provider support evidence projection

Revision ID: 0011_catalog_support_evidence
Revises: 0010_avatar_object_key
Create Date: 2026-08-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_catalog_support_evidence"
down_revision: str | None = "0010_avatar_object_key"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "catalog_metadata",
        sa.Column("support_evidence", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("catalog_metadata", "support_evidence")
