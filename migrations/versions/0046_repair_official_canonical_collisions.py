"""Repair legacy catalog slugs before projecting the exact Official manifest.

Revision ID: 0046_repair_official_canonical_collisions
Revises: 0045_retire_removed_official_sources
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy.sql import text as sql_text

revision: str = "0046_repair_official_canonical_collisions"
down_revision: str | None = "0045_retire_removed_official_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Keep legacy non-Official catalog lines while freeing Official names."""
    op.execute(
        sql_text(
            """
            DO $$
            DECLARE
                collision RECORD;
                candidate TEXT;
                suffix TEXT;
                serial INTEGER;
            BEGIN
                FOR collision IN
                    SELECT source.stable_id AS official_stable_id,
                           source.canonical_name,
                           identity.stable_id AS conflicting_stable_id
                    FROM official_upstream_source AS source
                    JOIN catalog_identity AS identity
                      ON identity.canonical_name_normalized = source.canonical_name
                     AND identity.stable_id <> source.stable_id
                    WHERE source.canonical_name IS NOT NULL
                      AND source.inventory_state NOT IN ('removed', 'transferred')
                      AND identity.owner_account_id <> source.owner_account_id
                    ORDER BY source.id, identity.stable_id
                    FOR UPDATE OF identity
                LOOP
                    suffix := right(
                        regexp_replace(collision.conflicting_stable_id, '[^a-zA-Z0-9]', '', 'g'),
                        8
                    );
                    candidate := left(collision.canonical_name || '-' || lower(suffix), 80);
                    serial := 1;
                    WHILE EXISTS (
                        SELECT 1
                        FROM catalog_identity
                        WHERE canonical_name_normalized = candidate
                    )
                    LOOP
                        candidate := left(collision.canonical_name, 70)
                            || '-' || lower(suffix) || '-' || serial::TEXT;
                        serial := serial + 1;
                    END LOOP;
                    UPDATE catalog_identity
                    SET canonical_name = candidate,
                        canonical_name_normalized = candidate
                    WHERE stable_id = collision.conflicting_stable_id;
                END LOOP;
            END $$;
            """
        )
    )


def downgrade() -> None:
    """Do not restore colliding legacy names."""
    pass
