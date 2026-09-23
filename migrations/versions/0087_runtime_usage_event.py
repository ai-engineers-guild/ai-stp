"""Create the coordinate-only runtime usage event table."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0087_runtime_usage_event"
down_revision: str | None = "0085_heartbeat_permissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runtime_usage_event",
        sa.Column("event_id", sa.String(length=80), nullable=False),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("employee_account_id", sa.String(length=64), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("harness", sa.String(length=64), nullable=False),
        sa.Column("setup_stable_id", sa.String(length=128), nullable=False),
        sa.Column("setup_version", sa.String(length=32), nullable=False),
        sa.Column("setup_passport_digest", sa.String(length=80), nullable=False),
        sa.Column("component_kind", sa.String(length=16), nullable=False),
        sa.Column("component_stable_id", sa.String(length=128), nullable=False),
        sa.Column("component_version", sa.String(length=32), nullable=False),
        sa.Column("component_passport_digest", sa.String(length=80), nullable=False),
        sa.Column("invoked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("schema_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("organization_id", "event_id"),
        sa.CheckConstraint("length(event_id) >= 8", name="ck_runtime_usage_event_id"),
        sa.CheckConstraint(
            "outcome in ('succeeded','failed','cancelled')",
            name="ck_runtime_usage_event_outcome",
        ),
        sa.CheckConstraint(
            "component_kind in "
            "('instruction','skill','mcp','hook','command','agent','plugin','setting','cli')",
            name="ck_runtime_usage_event_component_kind",
        ),
        sa.CheckConstraint("schema_version >= 1", name="ck_runtime_usage_event_schema"),
    )
    op.create_index(
        "ix_runtime_usage_event_invoked",
        "runtime_usage_event",
        ["organization_id", "invoked_at"],
    )
    op.create_index(
        "ix_runtime_usage_event_employee",
        "runtime_usage_event",
        ["organization_id", "employee_account_id", "invoked_at"],
    )
    op.create_index(
        "ix_runtime_usage_event_component",
        "runtime_usage_event",
        ["organization_id", "component_stable_id", "component_version"],
    )
    op.create_index(
        "ix_runtime_usage_event_setup",
        "runtime_usage_event",
        ["organization_id", "setup_stable_id", "setup_version"],
    )


def downgrade() -> None:
    op.drop_index("ix_runtime_usage_event_setup", table_name="runtime_usage_event")
    op.drop_index("ix_runtime_usage_event_component", table_name="runtime_usage_event")
    op.drop_index("ix_runtime_usage_event_employee", table_name="runtime_usage_event")
    op.drop_index("ix_runtime_usage_event_invoked", table_name="runtime_usage_event")
    op.drop_table("runtime_usage_event")
