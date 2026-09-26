"""Keep corporate inventory discovery independent of heartbeat delivery."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0098_inventory_scan_policy"
down_revision: str | None = "0097_installation_operation_facts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "telemetry_policy",
        sa.Column(
            "inventory_scan_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("telemetry_policy", "inventory_scan_enabled")
