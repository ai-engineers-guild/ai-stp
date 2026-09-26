"""Persist settled installation operations separately from heartbeat and usage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0097_installation_operation_facts"
down_revision: str | None = "0096_heartbeat_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT = (
    "current_setting('ai_stp.organization_id', true) = '*' OR "
    "organization_id = current_setting('ai_stp.organization_id', true)"
)


def upgrade() -> None:
    op.create_table(
        "installation_operation_fact",
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("operation_id", sa.String(80), nullable=False),
        sa.Column("fact_digest", sa.String(80), nullable=False),
        sa.Column("employee_account_id", sa.String(64), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("harness", sa.String(64), nullable=False),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("setup_stable_id", sa.String(128), nullable=True),
        sa.Column("setup_version", sa.String(32), nullable=True),
        sa.Column("components", sa.JSON(), nullable=False),
        sa.Column("components_complete", sa.Boolean(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("organization_id", "operation_id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "action in ('install','update','remove','rollback')", name="ck_install_fact_action"
        ),
        sa.CheckConstraint(
            "result in ('verified','partial','rolled_back','failed','stale')",
            name="ck_install_fact_result",
        ),
        sa.CheckConstraint("scope in ('global','project','unknown')", name="ck_install_fact_scope"),
    )
    op.create_index(
        "ix_install_fact_employee",
        "installation_operation_fact",
        ["organization_id", "employee_account_id", "occurred_at"],
    )
    op.create_index(
        "ix_install_fact_setup",
        "installation_operation_fact",
        ["organization_id", "setup_stable_id", "setup_version"],
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE installation_operation_fact ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE installation_operation_fact FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY installation_operation_fact_tenant_policy "
            "ON installation_operation_fact "
            f"USING ({TENANT}) WITH CHECK ({TENANT})"
        )
        op.execute(
            "CREATE TRIGGER installation_operation_fact_tenant_immutable BEFORE UPDATE OF "
            "organization_id ON installation_operation_fact FOR EACH ROW "
            "EXECUTE FUNCTION ai_stp_reject_tenant_change()"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DROP POLICY installation_operation_fact_tenant_policy ON installation_operation_fact"
        )
        op.execute(
            "DROP TRIGGER installation_operation_fact_tenant_immutable "
            "ON installation_operation_fact"
        )
    op.drop_index("ix_install_fact_setup", table_name="installation_operation_fact")
    op.drop_index("ix_install_fact_employee", table_name="installation_operation_fact")
    op.drop_table("installation_operation_fact")
