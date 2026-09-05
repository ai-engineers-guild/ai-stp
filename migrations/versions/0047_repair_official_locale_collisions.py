"""Repair legacy localized names that block the exact Official display name.

Revision ID: 0047_repair_official_locale_collisions
Revises: 0046_repair_official_canonical_collisions
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy.sql import text as sql_text

revision: str = "0047_repair_official_locale_collisions"
down_revision: str | None = "0046_repair_official_canonical_collisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Keep legacy lines addressable without reserving Official display names."""
    op.execute(
        sql_text(
            """
            UPDATE catalog_identity_locale AS locale
            SET display_name = identity.canonical_name,
                display_name_normalized = identity.canonical_name
            FROM catalog_identity AS identity
            WHERE identity.stable_id = locale.stable_id
              AND EXISTS (
                  SELECT 1
                  FROM official_upstream_source AS source
                  WHERE source.canonical_name = 'ai-repo-safety'
                    AND source.stable_id <> identity.stable_id
                    AND source.inventory_state NOT IN ('removed', 'transferred')
                    AND identity.owner_account_id <> source.owner_account_id
              )
            """
        )
    )


def downgrade() -> None:
    """Do not restore names that would block the Official manifest."""
    pass
