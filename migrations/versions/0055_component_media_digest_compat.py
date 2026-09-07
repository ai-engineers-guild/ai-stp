"""Repair the component media digest column on partially applied 0052 schemas."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0055_component_media_digest_compat"
down_revision: str | None = "0054_publication_artifact_inventory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("component_media")
    }
    if "content_digest" not in columns:
        op.add_column(
            "component_media",
            sa.Column("content_digest", sa.String(length=80), nullable=True),
        )


def downgrade() -> None:
    columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("component_media")
    }
    if "content_digest" in columns:
        op.drop_column("component_media", "content_digest")
