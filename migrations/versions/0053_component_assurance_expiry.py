"""Keep the derived assurance expiry available to SQL catalog filters.

Revision ID: 0053_component_assurance_expiry
Revises: 0052_restore_canonical_support_tiers
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0053_component_assurance_expiry"
down_revision: str | None = "0052_restore_canonical_support_tiers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "catalog_search_projection",
        sa.Column("component_verified_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Old derived badges have no complete identity/freshness proof. Reindex computes it.
    op.execute(
        "UPDATE catalog_search_projection SET component_verified = false "
        "WHERE object_kind = 'component'"
    )


def downgrade() -> None:
    op.drop_column("catalog_search_projection", "component_verified_expires_at")
