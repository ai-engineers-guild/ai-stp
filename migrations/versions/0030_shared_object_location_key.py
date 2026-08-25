"""allow catalog versions to share a content-addressed object key

Revision ID: 0030_shared_object_key
Revises: 0029_finding_summary
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0030_shared_object_key"
down_revision: str | None = "0029_finding_summary"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_object_location_object_key", "object_location", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint("uq_object_location_object_key", "object_location", ["object_key"])
