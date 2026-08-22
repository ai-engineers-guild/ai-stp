"""a check that did not pass says why, all the way to the row

Revision ID: 0026_evidence_reason
Revises: 0025_catalog_metrics
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_evidence_reason"
down_revision: str | None = "0025_catalog_metrics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `CheckOutcome.reason()` was computed, put on the binding and then dropped:
    # the row was built field by field and this one was not among them. The
    # wire model carried the field, so every refusal answered `null` and said
    # nothing about itself — which is exactly the case the field exists for.
    #
    # Bounded and rule-shaped by construction: identifiers and counts, never the
    # scanned content, because this reaches a client.
    op.add_column("evidence_binding", sa.Column("reason", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("evidence_binding", "reason")
