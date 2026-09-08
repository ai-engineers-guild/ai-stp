"""Repair assurance expiry on partially applied catalog schemas.

Revision ID: 0057_catalog_assurance_expiry_compat
Revises: 0056_github_connector
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0057_catalog_assurance_expiry_compat"
down_revision: str | None = "0056_github_connector"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("catalog_search_projection")
    }
    if "component_verified_expires_at" not in columns:
        op.add_column(
            "catalog_search_projection",
            sa.Column(
                "component_verified_expires_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )


def downgrade() -> None:
    # Migration 0053 owns this column; this repair cannot know whether it added it.
    pass
