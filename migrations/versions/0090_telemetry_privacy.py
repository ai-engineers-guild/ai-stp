"""Telemetry privacy: bounded events, retention policy, rights, audit."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0090_telemetry_privacy"
down_revision: str | None = "0089_runtime_usage_export"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TELEMETRY_TABLES = (
    "telemetry_event",
    "telemetry_policy",
    "telemetry_revocation",
    "telemetry_audit",
)

TELEMETRY_PERMISSIONS = (
    "telemetry.write",
    "telemetry.read",
    "telemetry.list",
    "telemetry.export",
    "telemetry.manage",
    "telemetry.delete",
)


def upgrade() -> None:
    op.create_table(
        "telemetry_event",
        sa.Column(
            "organization_id",
            sa.String(64),
            sa.ForeignKey("organization.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.PrimaryKeyConstraint("organization_id", "event_id", name="pk_telemetry_event"),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=True),
        sa.Column("device_id", sa.String(64), nullable=True),
        sa.Column("project_id", sa.String(64), nullable=True),
        sa.Column("harness", sa.String(64), nullable=False),
        sa.Column("harness_version", sa.String(128), nullable=True),
        sa.Column("provider_name", sa.String(64), nullable=True),
        sa.Column("provider_version", sa.String(128), nullable=True),
        sa.Column("capabilities", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("health", sa.String(16), nullable=True),
        sa.Column("setup_id", sa.String(64), nullable=True),
        sa.Column("component_kind", sa.String(32), nullable=True),
        sa.Column("component_stable_id", sa.String(64), nullable=True),
        sa.Column("component_version", sa.String(32), nullable=True),
        sa.Column("outcome", sa.String(16), nullable=True),
        sa.Column("subject_state", sa.String(16), nullable=False, server_default="active"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "kind in ('heartbeat','invocation')",
            name="ck_telemetry_event_kind",
        ),
        sa.CheckConstraint(
            "health is null or health in ('active','stale','failing','disabled','unknown')",
            name="ck_telemetry_event_health",
        ),
        sa.CheckConstraint(
            "outcome is null or outcome in ('succeeded','failed','denied','unknown')",
            name="ck_telemetry_event_outcome",
        ),
        sa.CheckConstraint(
            "subject_state in ('active','anonymized')",
            name="ck_telemetry_event_subject_state",
        ),
    )
    op.create_index(
        "ix_telemetry_event_account_id",
        "telemetry_event",
        ["account_id"],
    )
    op.create_table(
        "telemetry_policy",
        sa.Column(
            "organization_id",
            sa.String(64),
            sa.ForeignKey("organization.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("raw_retention_days", sa.Integer(), nullable=False),
        sa.Column("aggregate_retention_days", sa.Integer(), nullable=False, server_default="365"),
        sa.Column("legal_basis", sa.String(32), nullable=False),
        sa.Column("notice_text", sa.String(4000), nullable=True),
        sa.Column("notice_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("policy_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "raw_retention_days between 1 and 3650",
            name="ck_telemetry_policy_raw_retention",
        ),
        sa.CheckConstraint(
            "aggregate_retention_days between 1 and 3650",
            name="ck_telemetry_policy_aggregate_retention",
        ),
        sa.CheckConstraint(
            "legal_basis in ('consent','contract','legitimate_interest')",
            name="ck_telemetry_policy_basis",
        ),
        sa.CheckConstraint("notice_revision >= 0", name="ck_telemetry_policy_notice"),
        sa.CheckConstraint("policy_version >= 1", name="ck_telemetry_policy_version"),
    )
    op.create_table(
        "telemetry_revocation",
        sa.Column(
            "organization_id",
            sa.String(64),
            sa.ForeignKey("organization.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("subject_kind", sa.String(16), primary_key=True),
        sa.Column("subject_id", sa.String(64), primary_key=True),
        sa.Column("state", sa.String(16), nullable=False, server_default="active"),
        sa.Column("legal_basis", sa.String(32), nullable=True),
        sa.Column("notice_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notice_acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deletion_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("anonymized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "subject_kind in ('account','device')",
            name="ck_telemetry_revocation_subject_kind",
        ),
        sa.CheckConstraint(
            "state in ('active','revoked','deleted')",
            name="ck_telemetry_revocation_state",
        ),
        sa.CheckConstraint(
            "legal_basis is null or legal_basis in ('consent','contract','legitimate_interest')",
            name="ck_telemetry_revocation_basis",
        ),
        sa.CheckConstraint("notice_revision >= 0", name="ck_telemetry_revocation_notice"),
    )
    op.create_table(
        "telemetry_audit",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_telemetry_audit"),
        sa.Column(
            "organization_id",
            sa.String(64),
            sa.ForeignKey("organization.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("actor_account_id", sa.String(64), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_table", sa.String(64), nullable=False),
        sa.Column("target_id", sa.String(128), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("request_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "action in ("
            "'telemetry.ingest','telemetry.ingest.batch','telemetry.list',"
            "'telemetry.aggregate','telemetry.export','telemetry.policy.write',"
            "'telemetry.rights.write','telemetry.rights.revoke',"
            "'telemetry.delete','telemetry.retention','telemetry.audit.list'"
            ")",
            name="ck_telemetry_audit_action",
        ),
    )
    op.create_index(
        "ix_telemetry_audit_organization_id",
        "telemetry_audit",
        ["organization_id"],
    )
    op.execute(
        """
        INSERT INTO corporate_role_permission (organization_id, role, permission)
        SELECT role_row.organization_id, role_row.name, permission_row.permission
        FROM corporate_role AS role_row
        CROSS JOIN (
            VALUES
                ('telemetry.write'),
                ('telemetry.read'),
                ('telemetry.list'),
                ('telemetry.export'),
                ('telemetry.manage'),
                ('telemetry.delete')
        ) AS permission_row(permission)
        WHERE role_row.name = 'superadmin'
        ON CONFLICT DO NOTHING
        """
    )
    if op.get_bind().dialect.name == "postgresql":
        tenant_expression = (
            "current_setting('ai_stp.organization_id', true) = '*' OR "
            "organization_id = current_setting('ai_stp.organization_id', true)"
        )
        for table_name in TELEMETRY_TABLES:
            op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
            op.execute(
                f"CREATE POLICY {table_name}_tenant_policy ON {table_name} "
                f"USING ({tenant_expression}) WITH CHECK ({tenant_expression})"
            )
            op.execute(
                f"CREATE TRIGGER {table_name}_tenant_immutable "
                f"BEFORE UPDATE OF organization_id ON {table_name} "
                "FOR EACH ROW EXECUTE FUNCTION ai_stp_reject_tenant_change()"
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table_name in TELEMETRY_TABLES:
            op.execute(f"DROP TRIGGER {table_name}_tenant_immutable ON {table_name}")
            op.execute(f"DROP POLICY {table_name}_tenant_policy ON {table_name}")
            op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")
    op.execute(
        """
        DELETE FROM corporate_role_permission
        WHERE role = 'superadmin' AND permission IN (
            'telemetry.write', 'telemetry.read', 'telemetry.list',
            'telemetry.export', 'telemetry.manage', 'telemetry.delete'
        )
        """
    )
    op.drop_index("ix_telemetry_audit_organization_id", table_name="telemetry_audit")
    op.drop_table("telemetry_audit")
    op.drop_table("telemetry_revocation")
    op.drop_table("telemetry_policy")
    op.drop_index("ix_telemetry_event_account_id", table_name="telemetry_event")
    op.drop_table("telemetry_event")
