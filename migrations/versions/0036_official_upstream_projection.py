"""explicit official-upstream projection target

Revision ID: 0036_official_projection
Revises: 0035_official_upstream_multi
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036_official_projection"
down_revision: str | None = "0035_official_upstream_multi"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("official_upstream_source", sa.Column("target_scope", sa.String(16)))
    op.add_column("official_upstream_source", sa.Column("projection_root", sa.String(1024)))
    op.add_column("official_upstream_source", sa.Column("projection_shape", sa.String(16)))


def downgrade() -> None:
    op.drop_column("official_upstream_source", "projection_shape")
    op.drop_column("official_upstream_source", "projection_root")
    op.drop_column("official_upstream_source", "target_scope")
