"""repair catalog passport digests

Revision ID: 0018_catalog_digest
Revises: 0017_web_devices
"""

from typing import Any, cast

import sqlalchemy as sa
from alembic import op

from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_bytes

revision: str = "0018_catalog_digest"
down_revision: str | None = "0017_web_devices"
branch_labels = None
depends_on = None

PASSPORT_DIGEST_DOMAIN = "ai-stp:passport:v1"
PLACEHOLDER_DIGEST = "sha256:" + ("0" * 64)


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id, passport_document, passport_digest "
            "FROM catalog_metadata WHERE passport_document IS NOT NULL"
        )
    ).mappings()
    for row in rows:
        if row["passport_digest"] == PLACEHOLDER_DIGEST:
            continue
        passport = cast(dict[str, Any], row["passport_document"])
        digest = digest_bytes(PASSPORT_DIGEST_DOMAIN, canonize(cast(JsonValue, passport)))
        connection.execute(
            sa.text("UPDATE catalog_metadata SET passport_digest = :digest WHERE id = :id"),
            {"digest": digest, "id": row["id"]},
        )


def downgrade() -> None:
    pass
