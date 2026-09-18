"""Backfill corporate governance permissions for existing roles."""

from collections.abc import Sequence

from alembic import op

revision: str = "0078_corporate_catalog_permissions"
down_revision: str | None = "0077_corporate_job_titles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO corporate_role_permission (organization_id, role, permission)
        SELECT role_row.organization_id, role_row.name, permission_row.permission
        FROM corporate_role AS role_row
        CROSS JOIN (
            VALUES
                ('catalog_object.read'),
                ('catalog_object.edit'),
                ('catalog_object.publish'),
                ('catalog_object.verify'),
                ('catalog_object.assign'),
                ('catalog_object.ownership_transfer'),
                ('catalog_object.maintainer'),
                ('catalog_object.lifecycle'),
                ('catalog_object.audit'),
                ('catalog_object.explain')
        ) AS permission_row(permission)
        WHERE role_row.name = 'superadmin'
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO corporate_role_permission (organization_id, role, permission)
        SELECT role_row.organization_id, role_row.name, 'catalog_object.read'
        FROM corporate_role AS role_row
        WHERE role_row.name IN ('lead', 'staff')
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM corporate_role_permission
        WHERE role IN ('superadmin', 'lead', 'staff')
          AND permission LIKE 'catalog_object.%'
        """
    )
