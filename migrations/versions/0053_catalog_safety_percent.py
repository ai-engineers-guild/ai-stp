"""Store the public safety-check percentage in the catalog search projection.

Revision ID: 0053_catalog_safety_percent
Revises: 0052_private_artifact_storage
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0053_catalog_safety_percent"
down_revision: str | None = "0052_private_artifact_storage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "catalog_search_projection",
        sa.Column("safety_percent", sa.Integer(), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE catalog_search_projection AS projection "
            "SET safety_percent = NULLIF("
            "metadata.checks_summary ->> 'checks_passed_percent', ''"
            ")::integer "
            "FROM catalog_metadata AS metadata "
            "WHERE metadata.id = projection.catalog_metadata_id"
        )
    )


def downgrade() -> None:
    op.drop_column("catalog_search_projection", "safety_percent")
