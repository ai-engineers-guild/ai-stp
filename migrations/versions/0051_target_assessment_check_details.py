"""Persist per-projection safety check details for the public target matrix.

Revision ID: 0051_target_assessment_check_details
Revises: 0050_exact_public_targets_and_cli_taxonomy
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0051_target_assessment_check_details"
down_revision: str | None = "0050_exact_public_targets_and_cli_taxonomy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("target_assessment", sa.Column("checks_summary", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("target_assessment", "checks_summary")
