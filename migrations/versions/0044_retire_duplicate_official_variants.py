"""Retire duplicate Official git variants superseded by exact packages.

Revision ID: 0044_retire_duplicate_official_variants
Revises: 0043_retire_duplicate_official_identities
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import bindparam
from sqlalchemy.sql import text as sql_text

revision: str = "0044_retire_duplicate_official_variants"
down_revision: str | None = "0043_retire_duplicate_official_identities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DUPLICATE_SOURCE_IDS = ("context7", "context-mode", "serena")


def upgrade() -> None:
    """Stop scheduling duplicate git variants without deleting history."""
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
                   'official_upstream.duplicate_source_retired',
                   'official_upstream_source',
                   id,
                   'duplicate component variant was superseded by the exact package source',
                   json_build_object('inventory_state', 'removed', 'update_policy', 'disabled')
            FROM retired
            """
        ).bindparams(bindparam("source_ids", expanding=True, value=_DUPLICATE_SOURCE_IDS))
    )


def downgrade() -> None:
    """Keep retired variants fenced; published history is never reopened."""
    pass
