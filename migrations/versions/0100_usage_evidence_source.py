"""Separate native invocations from agent reports and passive loads."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0100_usage_evidence_source"
down_revision: str | None = "0099_installation_inventory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "runtime_usage_event",
        sa.Column(
            "source",
            sa.String(16),
            nullable=False,
            server_default="agent_reported",
        ),
    )
    op.add_column(
        "runtime_usage_event",
        sa.Column(
            "activity_kind",
            sa.String(16),
            nullable=False,
            server_default="invocation",
        ),
    )
    op.create_check_constraint(
        "ck_runtime_usage_event_source",
        "runtime_usage_event",
        "source in ('native_hook','agent_reported')",
    )
    op.create_check_constraint(
        "ck_runtime_usage_event_activity_kind",
        "runtime_usage_event",
        "activity_kind in ('invocation','load')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_runtime_usage_event_activity_kind", "runtime_usage_event", type_="check")
    op.drop_constraint("ck_runtime_usage_event_source", "runtime_usage_event", type_="check")
    op.drop_column("runtime_usage_event", "activity_kind")
    op.drop_column("runtime_usage_event", "source")
