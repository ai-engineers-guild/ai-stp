"""Repair legacy localized names that block the exact Official display name.

Revision ID: 0047_repair_official_locale_collisions
Revises: 0046_repair_official_canonical_collisions
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy.sql import text as sql_text

from ai_stp_foundation.identity import normalize_display_key

revision: str = "0047_repair_official_locale_collisions"
down_revision: str | None = "0046_repair_official_canonical_collisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Keep legacy lines addressable without reserving Official display names."""
    bind = op.get_bind()
    sources = bind.execute(
        sql_text(
            """
            SELECT stable_id, owner_account_id, display_name_en, display_name_ru
            FROM official_upstream_source
            WHERE canonical_name = 'ai-repo-safety'
              AND inventory_state NOT IN ('removed', 'transferred')
            """
        )
    ).mappings()
    for source in sources:
        for locale in ("en", "ru"):
            display_name = source[f"display_name_{locale}"]
            if not display_name:
                continue
            # A source's existence is not a collision. Only its exact locale
            # and normalized name may select a legacy row for this repair.
            bind.execute(
                sql_text(
                    """
                    UPDATE catalog_identity_locale AS locale
                    SET display_name = identity.canonical_name,
                        display_name_normalized = identity.canonical_name
                    FROM catalog_identity AS identity
                    WHERE identity.stable_id = locale.stable_id
                      AND identity.stable_id <> :official_stable_id
                      AND identity.owner_account_id <> :official_owner_id
                      AND locale.locale = :locale
                      AND locale.display_name_normalized = :display_key
                    """
                ),
                {
                    "official_stable_id": source["stable_id"],
                    "official_owner_id": source["owner_account_id"],
                    "locale": locale,
                    "display_key": normalize_display_key(display_name),
                },
            )


def downgrade() -> None:
    """Do not restore names that would block the Official manifest."""
    pass
