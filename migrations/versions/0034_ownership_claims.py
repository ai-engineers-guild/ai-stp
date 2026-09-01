"""verified-maintainer ownership claims and immutable revisions

Revision ID: 0034_ownership_claims
Revises: 0033_official_upstream
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034_ownership_claims"
down_revision: str | None = "0033_official_upstream"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ownership_claim",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("object_kind", sa.String(length=32), server_default="component", nullable=False),
        sa.Column("stable_id", sa.String(length=64), nullable=False),
        sa.Column("requester_account_id", sa.String(length=64), nullable=False),
        sa.Column("from_account_id", sa.String(length=64), nullable=False),
        sa.Column("to_account_id", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=32), server_default="requested", nullable=False),
        sa.Column("preview", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("staff_account_id", sa.String(length=64), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "state in ('requested', 'approved', 'denied')",
            name="ck_ownership_claim_state",
        ),
        sa.CheckConstraint("object_kind = 'component'", name="ck_ownership_claim_object_kind"),
        sa.ForeignKeyConstraint(
            ["requester_account_id"],
            ["account.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_ownership_claim_idempotency_key"),
    )
    op.create_index("ix_ownership_claim_stable_id", "ownership_claim", ["stable_id"])
    op.create_index(
        "ix_ownership_claim_requester_account_id",
        "ownership_claim",
        ["requester_account_id"],
    )
    op.create_table(
        "ownership_revision",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("claim_id", sa.String(length=64), nullable=False),
        sa.Column("stable_id", sa.String(length=64), nullable=False),
        sa.Column("from_account_id", sa.String(length=64), nullable=False),
        sa.Column("to_account_id", sa.String(length=64), nullable=False),
        sa.Column("major_lines", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("staff_account_id", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["ownership_claim.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ownership_revision_claim_id", "ownership_revision", ["claim_id"])
    op.create_index("ix_ownership_revision_stable_id", "ownership_revision", ["stable_id"])


def downgrade() -> None:
    op.drop_index("ix_ownership_revision_stable_id", table_name="ownership_revision")
    op.drop_index("ix_ownership_revision_claim_id", table_name="ownership_revision")
    op.drop_table("ownership_revision")
    op.drop_index("ix_ownership_claim_requester_account_id", table_name="ownership_claim")
    op.drop_index("ix_ownership_claim_stable_id", table_name="ownership_claim")
    op.drop_table("ownership_claim")
