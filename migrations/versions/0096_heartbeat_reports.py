"""Persist device labels and bounded heartbeat history for corporate reports."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0096_heartbeat_reports"
down_revision: str | None = "0095_minute_installation_heartbeat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT = (
    "current_setting('ai_stp.organization_id', true) = '*' OR "
    "organization_id = current_setting('ai_stp.organization_id', true)"
)


def upgrade() -> None:
    op.add_column("device", sa.Column("display_name", sa.String(120), nullable=True))
    op.create_table(
        "installation_heartbeat_event",
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reported_state", sa.String(16), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("organization_id", "device_id", "checked_at"),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.CheckConstraint("interval_seconds > 0", name="ck_heartbeat_event_interval"),
        sa.CheckConstraint(
            "reported_state in ('active', 'partial', 'failing', 'disabled')",
            name="ck_heartbeat_event_reported_state",
        ),
    )
    op.create_index(
        "ix_installation_heartbeat_event_account",
        "installation_heartbeat_event",
        ["organization_id", "account_id"],
    )
    op.create_index(
        "ix_installation_heartbeat_event_period",
        "installation_heartbeat_event",
        ["organization_id", "received_at"],
    )
    op.create_index(
        "ix_installation_heartbeat_event_device_period",
        "installation_heartbeat_event",
        ["organization_id", "device_id", "received_at"],
    )
    op.create_table(
        "installation_heartbeat_policy_event",
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("stale_after_seconds", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("organization_id", "version"),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
    )
    op.execute(
        "INSERT INTO installation_heartbeat_policy_event "
        "(organization_id, version, effective_from, enabled, "
        "interval_seconds, stale_after_seconds) "
        "SELECT organization_id, policy_version, CURRENT_TIMESTAMP, heartbeat_enabled, "
        "heartbeat_interval_seconds, heartbeat_stale_after_seconds FROM telemetry_policy"
    )
    if op.get_bind().dialect.name == "postgresql":
        for table in ("installation_heartbeat_event", "installation_heartbeat_policy_event"):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(
                f"CREATE POLICY {table}_tenant_policy ON {table} "
                f"USING ({TENANT}) WITH CHECK ({TENANT})"
            )
            op.execute(
                f"CREATE TRIGGER {table}_tenant_immutable BEFORE UPDATE OF organization_id "
                f"ON {table} FOR EACH ROW EXECUTE FUNCTION ai_stp_reject_tenant_change()"
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in ("installation_heartbeat_policy_event", "installation_heartbeat_event"):
            op.execute(f"DROP POLICY {table}_tenant_policy ON {table}")
            op.execute(f"DROP TRIGGER {table}_tenant_immutable ON {table}")
    op.drop_table("installation_heartbeat_policy_event")
    op.drop_index(
        "ix_installation_heartbeat_event_device_period",
        table_name="installation_heartbeat_event",
    )
    op.drop_index(
        "ix_installation_heartbeat_event_period", table_name="installation_heartbeat_event"
    )
    op.drop_index(
        "ix_installation_heartbeat_event_account", table_name="installation_heartbeat_event"
    )
    op.drop_table("installation_heartbeat_event")
    op.drop_column("device", "display_name")
