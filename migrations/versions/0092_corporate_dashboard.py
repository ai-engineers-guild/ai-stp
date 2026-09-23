"""Store the latest CI verdict and bounded saved dashboard queries."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0092_corporate_dashboard"
down_revision: str | None = "0091_gitlab_project_observations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("corporate_ci_check", "corporate_dashboard_view")


def upgrade() -> None:
    op.create_table(
        "corporate_ci_check",
        sa.Column(
            "organization_id",
            sa.String(64),
            sa.ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column(
            "device_id",
            sa.String(64),
            sa.ForeignKey("device.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("harness", sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint("organization_id", "project_id", "device_id", "harness"),
        sa.Column(
            "account_id",
            sa.String(64),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("setup_id", sa.String(64)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status in ('pass','fail','outdated','revoked','unsupported',"
            "'not_enrolled','unverifiable')",
            name="ck_corporate_ci_check_status",
        ),
        sa.CheckConstraint(
            "reason in ('none','check_failed','target_drift','source_unavailable',"
            "'permission_denied','unsupported','unknown')",
            name="ck_corporate_ci_check_reason",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_corporate_ci_check_revision"),
    )
    op.create_table(
        "corporate_dashboard_view",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(64),
            sa.ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("scope_id", sa.String(64), nullable=False),
        sa.Column(
            "owner_account_id",
            sa.String(64),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("query", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "scope in ('user','team','organization')", name="ck_dashboard_view_scope"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_dashboard_view_revision"),
    )
    op.create_index(
        "ix_corporate_dashboard_view_organization_id",
        "corporate_dashboard_view",
        ["organization_id"],
    )
    if op.get_bind().dialect.name == "postgresql":
        tenant_expression = (
            "current_setting('ai_stp.organization_id', true) = '*' OR "
            "organization_id = current_setting('ai_stp.organization_id', true)"
        )
        for table in TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(
                f"CREATE POLICY {table}_tenant_policy ON {table} "
                f"USING ({tenant_expression}) WITH CHECK ({tenant_expression})"
            )
            op.execute(
                f"CREATE TRIGGER {table}_tenant_immutable BEFORE UPDATE OF organization_id "
                f"ON {table} FOR EACH ROW EXECUTE FUNCTION ai_stp_reject_tenant_change()"
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in TABLES:
            op.execute(f"DROP TRIGGER {table}_tenant_immutable ON {table}")
            op.execute(f"DROP POLICY {table}_tenant_policy ON {table}")
            op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_index(
        "ix_corporate_dashboard_view_organization_id", table_name="corporate_dashboard_view"
    )
    op.drop_table("corporate_dashboard_view")
    op.drop_table("corporate_ci_check")
