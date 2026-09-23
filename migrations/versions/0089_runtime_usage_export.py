"""Create the bounded runtime usage export receipt table."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0089_runtime_usage_export"
down_revision: str | None = "0088_runtime_usage_permissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runtime_usage_export",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("requested_by", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("filters", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("content_digest", sa.String(length=80), nullable=False),
        sa.Column("state", sa.String(length=16), server_default="completed", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("organization_id", "id"),
        sa.CheckConstraint("state in ('completed')", name="ck_runtime_usage_export_state"),
        sa.CheckConstraint("row_count >= 0", name="ck_runtime_usage_export_rows"),
    )
    op.create_index(
        "uq_runtime_usage_export_idempotency",
        "runtime_usage_export",
        ["organization_id", "idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_runtime_usage_export_created",
        "runtime_usage_export",
        ["organization_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_runtime_usage_export_created", table_name="runtime_usage_export")
    op.drop_index("uq_runtime_usage_export_idempotency", table_name="runtime_usage_export")
    op.drop_table("runtime_usage_export")
