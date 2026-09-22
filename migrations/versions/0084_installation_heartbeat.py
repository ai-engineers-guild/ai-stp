"""Corporate installation heartbeat table (t-heartbeat, GitHub #215)."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0084_installation_heartbeat"
down_revision: str | None = "0083_scoped_lead_permissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "installation_heartbeat"
TENANT = (
    "current_setting('ai_stp.organization_id', true) = '*' OR "
    "organization_id = current_setting('ai_stp.organization_id', true)"
)


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("cli_version", sa.String(64), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reported_state", sa.String(16), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("organization_id", "device_id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "reported_state in ('active', 'failing', 'disabled')",
            name="ck_installation_heartbeat_reported_state",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_installation_heartbeat_revision"),
    )
    op.create_index(
        "ix_installation_heartbeat_account",
        TABLE,
        ["organization_id", "account_id"],
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {TABLE}_tenant_policy ON {TABLE} USING ({TENANT}) WITH CHECK ({TENANT})"
        )
        op.execute(
            f"CREATE TRIGGER {TABLE}_tenant_immutable "
            f"BEFORE UPDATE OF organization_id ON {TABLE} "
            "FOR EACH ROW EXECUTE FUNCTION ai_stp_reject_tenant_change()"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"DROP POLICY {TABLE}_tenant_policy ON {TABLE}")
        op.execute(f"DROP TRIGGER {TABLE}_tenant_immutable ON {TABLE}")
        op.execute(f"ALTER TABLE {TABLE} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {TABLE} DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_installation_heartbeat_account", table_name=TABLE)
    op.drop_table(TABLE)
