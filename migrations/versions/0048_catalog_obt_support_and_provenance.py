"""Correct the catalog support-tier default for the open-beta line.

Revision ID: 0048_catalog_obt_support_and_provenance
Revises: 0048_canonical_catalog_consumers
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0048_catalog_obt_support_and_provenance"
down_revision: str | None = "0048_canonical_catalog_consumers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "catalog_search_projection",
        "support_tier",
        existing_type=sa.String(32),
        server_default="beta",
        existing_nullable=False,
    )
    op.execute(
        sa.text(
            "UPDATE catalog_search_projection SET support_tier = 'beta' "
            "WHERE support_tier = 'primary'"
        )
    )


def downgrade() -> None:
    op.alter_column(
        "catalog_search_projection",
        "support_tier",
        existing_type=sa.String(32),
        server_default="primary",
        existing_nullable=False,
    )
