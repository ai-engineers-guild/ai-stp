"""Install the functional taxonomy in existing corporate organizations."""

import sqlalchemy as sa
from alembic import op

from ai_stp_platform.technology_taxonomy import (
    classify_seed_technologies,
    install_technology_taxonomy,
)

revision = "0118_technology_taxonomy_defaults"
down_revision = "0117_technology_finding_reviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("SELECT set_config('ai_stp.organization_id', '*', true)"))
    for organization_id in connection.scalars(
        sa.text("SELECT id FROM organization WHERE kind = 'corporate'")
    ):
        defaults = install_technology_taxonomy(connection, organization_id)
        classified = classify_seed_technologies(connection, organization_id)
        if defaults or classified:
            connection.execute(
                sa.text(
                    "UPDATE organization SET policy_revision = policy_revision + 1 WHERE id = :id"
                ),
                {"id": organization_id},
            )
    op.execute("ALTER TABLE technology_area ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE technology_area FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY technology_area_tenant_policy ON technology_area "
        "USING (current_setting('ai_stp.organization_id', true) = '*' OR "
        "organization_id = current_setting('ai_stp.organization_id', true)) "
        "WITH CHECK (current_setting('ai_stp.organization_id', true) = '*' OR "
        "organization_id = current_setting('ai_stp.organization_id', true))"
    )


def downgrade() -> None:
    # Editable registry data is retained: rolling back code must not delete
    # tenant extensions or relationships created after this data migration.
    op.execute("DROP POLICY technology_area_tenant_policy ON technology_area")
    op.execute("ALTER TABLE technology_area DISABLE ROW LEVEL SECURITY")
