"""Organization-owned heartbeat cadence, retries, staleness and enablement."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0094_heartbeat_policy"
down_revision: str | None = "0093_partial_installation_heartbeat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "telemetry_policy",
        sa.Column("heartbeat_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "telemetry_policy",
        sa.Column(
            "heartbeat_interval_seconds", sa.Integer(), nullable=False, server_default="21600"
        ),
    )
    op.add_column(
        "telemetry_policy",
        sa.Column(
            "heartbeat_retry_base_seconds", sa.Integer(), nullable=False, server_default="60"
        ),
    )
    op.add_column(
        "telemetry_policy",
        sa.Column(
            "heartbeat_retry_max_seconds", sa.Integer(), nullable=False, server_default="3600"
        ),
    )
    op.add_column(
        "telemetry_policy",
        sa.Column(
            "heartbeat_stale_after_seconds", sa.Integer(), nullable=False, server_default="86400"
        ),
    )
    op.create_check_constraint(
        "ck_telemetry_policy_heartbeat_interval",
        "telemetry_policy",
        "heartbeat_interval_seconds between 300 and 2592000",
    )
    op.create_check_constraint(
        "ck_telemetry_policy_heartbeat_retry_base",
        "telemetry_policy",
        "heartbeat_retry_base_seconds between 30 and 86400",
    )
    op.create_check_constraint(
        "ck_telemetry_policy_heartbeat_retry_max",
        "telemetry_policy",
        "heartbeat_retry_max_seconds between 60 and 604800",
    )
    op.create_check_constraint(
        "ck_telemetry_policy_heartbeat_retry_order",
        "telemetry_policy",
        "heartbeat_retry_max_seconds >= heartbeat_retry_base_seconds",
    )
    op.create_check_constraint(
        "ck_telemetry_policy_heartbeat_stale_after",
        "telemetry_policy",
        "heartbeat_stale_after_seconds between 60 and 31536000",
    )


def downgrade() -> None:
    changed = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM telemetry_policy WHERE heartbeat_enabled IS NOT TRUE "
                "OR heartbeat_interval_seconds != 21600 "
                "OR heartbeat_retry_base_seconds != 60 "
                "OR heartbeat_retry_max_seconds != 3600 "
                "OR heartbeat_stale_after_seconds != 86400 LIMIT 1"
            )
        )
        .first()
    )
    if changed is not None:
        raise RuntimeError("preserve customized heartbeat policy before downgrade")
    for name in (
        "ck_telemetry_policy_heartbeat_stale_after",
        "ck_telemetry_policy_heartbeat_retry_order",
        "ck_telemetry_policy_heartbeat_retry_max",
        "ck_telemetry_policy_heartbeat_retry_base",
        "ck_telemetry_policy_heartbeat_interval",
    ):
        op.drop_constraint(name, "telemetry_policy", type_="check")
    for name in (
        "heartbeat_stale_after_seconds",
        "heartbeat_retry_max_seconds",
        "heartbeat_retry_base_seconds",
        "heartbeat_interval_seconds",
        "heartbeat_enabled",
    ):
        op.drop_column("telemetry_policy", name)
