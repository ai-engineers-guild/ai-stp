"""Remove the derived support default reintroduced by revision 0048_catalog_obt.

Revision ID: 0052_restore_canonical_support_tiers
Revises: 0051_target_assessment_check_details
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0052_restore_canonical_support_tiers"
down_revision: str | None = "0051_target_assessment_check_details"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("catalog_search_projection", "support_tier", server_default=None)


def downgrade() -> None:
    op.alter_column("catalog_search_projection", "support_tier", server_default="beta")
