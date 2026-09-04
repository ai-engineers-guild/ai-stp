"""Retire legacy Official source variants hidden by unique manifest names.

Revision ID: 0042_retire_duplicate_official_sources
Revises: 0041_catalog_search_projection
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import bindparam
from sqlalchemy.sql import text as sql_text

revision: str = "0042_retire_duplicate_official_sources"
down_revision: str | None = "0041_catalog_search_projection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LEGACY_SOURCE_IDS = ("official-chrome-devtools", "context-mode-mcp-npm", "ponytail-skill")


def upgrade() -> None:
    """Fence only the three known duplicate-name source variants."""
    op.execute(
        sql_text(
            """
            WITH retired AS (
                UPDATE official_upstream_source
                SET enabled = FALSE,
                    inventory_state = 'removed',
                    update_policy = 'disabled'
                WHERE id IN :source_ids
                  AND inventory_state NOT IN ('removed', 'transferred')
                RETURNING id, owner_account_id
            )
            INSERT INTO audit_event (
                actor_account_id, action, target_table, target_id, reason, payload
            )
            SELECT owner_account_id,
                   'official_upstream.legacy_source_retired',
                   'official_upstream_source',
                   id,
                   'duplicate component identity was superseded by the Git manifest',
                   json_build_object('inventory_state', 'removed', 'update_policy', 'disabled')
            FROM retired
            """
        ).bindparams(bindparam("source_ids", expanding=True, value=_LEGACY_SOURCE_IDS))
    )


def downgrade() -> None:
    """Keep retired source rows fenced; published history is never reopened."""
    pass
