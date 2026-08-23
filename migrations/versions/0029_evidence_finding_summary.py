"""bounded public finding summary on evidence bindings

Revision ID: 0029_finding_summary
Revises: 0028_complaint_intake
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_finding_summary"
down_revision: str | None = "0028_complaint_intake"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("evidence_binding", sa.Column("finding_summary", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("evidence_binding", "finding_summary")
