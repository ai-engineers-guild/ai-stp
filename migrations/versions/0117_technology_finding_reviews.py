"""Preserve finding decisions and order mapping publications by time."""

import sqlalchemy as sa
from alembic import op

revision = "0117_technology_finding_reviews"
down_revision = "0116_technology_landscape"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "technology_coordinate_mapping",
        sa.Column(
            "published_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "technology_finding_review",
        sa.Column(
            "organization_id",
            sa.String(64),
            sa.ForeignKey("organization.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("scan_id", sa.String(64), nullable=False),
        sa.Column("finding_key", sa.String(71), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("coordinate", sa.String(512), nullable=False),
        sa.Column("context", sa.String(32), nullable=True),
        sa.Column("technology_id", sa.String(64), nullable=True),
        sa.Column("review", sa.String(16), nullable=False),
        sa.Column("comment", sa.String(500), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("organization_id", "scan_id", "finding_key"),
        sa.ForeignKeyConstraint(
            ["organization_id", "scan_id"],
            ["technology_scan.organization_id", "technology_scan.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "technology_id"],
            ["technology.organization_id", "technology.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("review IN ('confirmed','rejected')", name="ck_finding_review"),
        sa.CheckConstraint("revision >= 1", name="ck_finding_review_revision"),
    )

    op.execute("ALTER TABLE technology_finding_review ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE technology_finding_review FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY technology_finding_review_tenant_policy ON technology_finding_review "
        "USING (current_setting('ai_stp.organization_id', true) = '*' OR "
        "organization_id = current_setting('ai_stp.organization_id', true)) "
        "WITH CHECK (current_setting('ai_stp.organization_id', true) = '*' OR "
        "organization_id = current_setting('ai_stp.organization_id', true))"
    )


def downgrade() -> None:
    op.drop_table("technology_finding_review")
    op.drop_column("technology_coordinate_mapping", "published_at")
