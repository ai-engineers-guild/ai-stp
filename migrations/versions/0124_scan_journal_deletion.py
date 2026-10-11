"""Preserve observations when administrators remove scan journal entries."""

import sqlalchemy as sa
from alembic import op

revision = "0124_scan_journal_deletion"
down_revision = "0114_corporate_role_flat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "technology_scan_deletion",
        sa.Column(
            "organization_id",
            sa.String(64),
            sa.ForeignKey("organization.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("deleted_by", sa.String(64), nullable=False),
        sa.Column(
            "deleted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("organization_id", "id"),
    )

    op.execute("ALTER TABLE technology_scan_deletion ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE technology_scan_deletion FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY technology_scan_deletion_tenant_policy ON technology_scan_deletion "
        "USING (current_setting('ai_stp.organization_id', true) = '*' OR "
        "organization_id = current_setting('ai_stp.organization_id', true)) "
        "WITH CHECK (current_setting('ai_stp.organization_id', true) = '*' OR "
        "organization_id = current_setting('ai_stp.organization_id', true))"
    )


def downgrade() -> None:
    op.drop_table("technology_scan_deletion")
