"""Persist content-free discovery snapshots without treating failures as removals."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0099_installation_inventory"
down_revision: str | None = "0098_inventory_scan_policy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT = (
    "current_setting('ai_stp.organization_id', true) = '*' OR "
    "organization_id = current_setting('ai_stp.organization_id', true)"
)


def upgrade() -> None:
    op.create_table(
        "installation_inventory_snapshot",
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("scan_id", sa.String(80), nullable=False),
        sa.Column("snapshot_digest", sa.String(80), nullable=False),
        sa.Column("employee_account_id", sa.String(64), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.String(64), nullable=True),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("complete", sa.Boolean(), nullable=False),
        sa.Column("components", sa.JSON(), nullable=False),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("organization_id", "scan_id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.CheckConstraint("scope in ('global','project')", name="ck_install_inventory_scope"),
        sa.CheckConstraint(
            "(scope = 'global' AND project_id IS NULL) OR "
            "(scope = 'project' AND project_id IS NOT NULL)",
            name="ck_install_inventory_project_scope",
        ),
    )
    op.create_index(
        "ix_install_inventory_scope",
        "installation_inventory_snapshot",
        [
            "organization_id",
            "employee_account_id",
            "device_id",
            "scope",
            "project_id",
            "scanned_at",
        ],
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE installation_inventory_snapshot ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE installation_inventory_snapshot FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY installation_inventory_snapshot_tenant_policy "
            "ON installation_inventory_snapshot "
            f"USING ({TENANT}) WITH CHECK ({TENANT})"
        )
        op.execute(
            "CREATE TRIGGER installation_inventory_snapshot_tenant_immutable BEFORE UPDATE OF "
            "organization_id ON installation_inventory_snapshot FOR EACH ROW "
            "EXECUTE FUNCTION ai_stp_reject_tenant_change()"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DROP POLICY installation_inventory_snapshot_tenant_policy "
            "ON installation_inventory_snapshot"
        )
        op.execute(
            "DROP TRIGGER installation_inventory_snapshot_tenant_immutable "
            "ON installation_inventory_snapshot"
        )
    op.drop_index("ix_install_inventory_scope", table_name="installation_inventory_snapshot")
    op.drop_table("installation_inventory_snapshot")
