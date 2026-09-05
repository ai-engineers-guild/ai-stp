"""Retire catalog identities for legacy Official source variants.

Revision ID: 0043_retire_duplicate_official_identities
Revises: 0042_retire_duplicate_official_sources
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import bindparam
from sqlalchemy.sql import text as sql_text

revision: str = "0043_retire_duplicate_official_identities"
down_revision: str | None = "0042_retire_duplicate_official_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LEGACY_SOURCE_IDS = ("official-chrome-devtools", "context-mode-mcp-npm", "ponytail-skill")


def upgrade() -> None:
    """Free the exact names while retaining every old catalog version."""
    op.execute(
        sql_text(
            """
            UPDATE catalog_identity AS identity
            SET canonical_name = identity.canonical_name || '-legacy',
                canonical_name_normalized = identity.canonical_name_normalized || '-legacy'
            FROM official_upstream_source AS source
            WHERE source.id IN :source_ids
              AND identity.stable_id = source.stable_id
              AND identity.canonical_name_normalized NOT LIKE '%-legacy'
            """
        ).bindparams(bindparam("source_ids", expanding=True, value=_LEGACY_SOURCE_IDS))
    )
    op.execute(
        sql_text(
            """
            UPDATE catalog_identity_locale AS locale
            SET display_name = locale.display_name || ' (legacy)',
                display_name_normalized = lower(locale.display_name || ' (legacy)')
            FROM official_upstream_source AS source
            WHERE source.id IN :source_ids
              AND locale.stable_id = source.stable_id
              AND locale.display_name_normalized NOT LIKE '%(legacy)'
            """
        ).bindparams(bindparam("source_ids", expanding=True, value=_LEGACY_SOURCE_IDS))
    )


def downgrade() -> None:
    """Keep retired identities fenced; immutable history remains addressable."""
    pass
