"""public complaint intake table

Revision ID: 0028_complaint_intake
Revises: 0027_safety_identity
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_complaint_intake"
down_revision: str | None = "0027_safety_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "complaint_intake",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("submitter_account_id", sa.String(length=64), nullable=True),
        sa.Column("submitter_key", sa.String(length=330), nullable=False),
        sa.Column("target_kind", sa.String(length=32), nullable=False),
        sa.Column("target", sa.String(length=256), nullable=False),
        sa.Column("sender_name", sa.String(length=120), nullable=False),
        sa.Column("reply_email", sa.String(length=254), nullable=False),
        sa.Column("subject", sa.String(length=160), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["submitter_account_id"],
            ["account.id"],
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "target_kind in ('author', 'component', 'setup', 'other')",
            name="ck_complaint_intake_target_kind",
        ),
    )
    op.create_index(
        "ix_complaint_intake_submitter_created",
        "complaint_intake",
        ["submitter_key", "created_at"],
    )
    op.create_index(
        "ix_complaint_intake_target_created",
        "complaint_intake",
        ["target_kind", "target", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_complaint_intake_target_created", table_name="complaint_intake")
    op.drop_index("ix_complaint_intake_submitter_created", table_name="complaint_intake")
    op.drop_table("complaint_intake")
