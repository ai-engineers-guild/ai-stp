"""Retire Official sources removed from the checked-in manifest.

Revision ID: 0045_retire_removed_official_sources
Revises: 0044_retire_duplicate_official_variants
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import bindparam
from sqlalchemy.sql import text as sql_text

revision: str = "0045_retire_removed_official_sources"
down_revision: str | None = "0044_retire_duplicate_official_variants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REMOVED_SOURCE_IDS = ("ctxt-mcp", "linear-mcp", "vercel-mcp")


def upgrade() -> None:
    """Fence removed sources without deleting their published history."""
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
                   'official_upstream.source_removed_from_manifest',
                   'official_upstream_source',
                   id,
                   'source is no longer an approved Official upstream component',
                   json_build_object('inventory_state', 'removed', 'update_policy', 'disabled')
            FROM retired
            """
        ).bindparams(bindparam("source_ids", expanding=True, value=_REMOVED_SOURCE_IDS))
    )


def downgrade() -> None:
    """Keep removed sources fenced; published history is never reopened."""
    pass
