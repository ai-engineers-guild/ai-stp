"""Allow a one-minute organization installation heartbeat interval."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0095_minute_installation_heartbeat"
down_revision: str | None = "0094_heartbeat_policy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_telemetry_policy_heartbeat_interval", "telemetry_policy", type_="check")
    op.create_check_constraint(
        "ck_telemetry_policy_heartbeat_interval",
        "telemetry_policy",
        "heartbeat_interval_seconds between 60 and 2592000",
    )


def downgrade() -> None:
    if (
        op.get_bind()
        .execute(
            sa.text("SELECT 1 FROM telemetry_policy WHERE heartbeat_interval_seconds < 300 LIMIT 1")
        )
        .first()
    ):
        raise RuntimeError("restore heartbeat intervals of at least 300 seconds before downgrade")
    op.drop_constraint("ck_telemetry_policy_heartbeat_interval", "telemetry_policy", type_="check")
    op.create_check_constraint(
        "ck_telemetry_policy_heartbeat_interval",
        "telemetry_policy",
        "heartbeat_interval_seconds between 300 and 2592000",
    )
