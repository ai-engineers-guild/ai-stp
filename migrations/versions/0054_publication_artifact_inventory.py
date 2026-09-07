"""Bind the exact component path inventory to publication plans.

Revision ID: 0054_publication_artifact_inventory
Revises: 0053_catalog_safety_percent
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0054_publication_artifact_inventory"
down_revision: str | None = "0053_catalog_safety_percent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "publication_plan",
        sa.Column(
            "artifact_inventory",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.alter_column("publication_plan", "artifact_inventory", server_default=None)


def downgrade() -> None:
    op.drop_column("publication_plan", "artifact_inventory")
