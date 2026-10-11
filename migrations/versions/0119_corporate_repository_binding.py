"""Allow an explicit corporate repository source without a CLI device link."""

import sqlalchemy as sa
from alembic import op

revision = "0119_corporate_repository_binding"
down_revision = "0118_technology_taxonomy_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "corporate_repository_binding",
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("remote_project_id", sa.String(64), nullable=False),
        sa.Column(
            "provider_project_id",
            sa.String(64),
            sa.ForeignKey("project_identity.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "actor_account_id",
            sa.String(64),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("plan_digest", sa.String(71), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.PrimaryKeyConstraint("organization_id", "remote_project_id"),
        sa.ForeignKeyConstraint(
            ["organization_id", "remote_project_id"],
            ["corporate_project.organization_id", "corporate_project.id"],
            ondelete="RESTRICT",
        ),
    )
    op.execute("ALTER TABLE corporate_repository_binding ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE corporate_repository_binding FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY corporate_repository_binding_tenant_policy "
        "ON corporate_repository_binding USING "
        "(current_setting('ai_stp.organization_id', true) = '*' OR "
        "organization_id = current_setting('ai_stp.organization_id', true)) "
        "WITH CHECK (current_setting('ai_stp.organization_id', true) = '*' OR "
        "organization_id = current_setting('ai_stp.organization_id', true))"
    )


def downgrade() -> None:
    op.drop_table("corporate_repository_binding")
