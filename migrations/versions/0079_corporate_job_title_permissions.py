"""Backfill job-title permissions for existing corporate superadmins."""

from collections.abc import Sequence

from alembic import op

revision: str = "0079_corporate_job_title_permissions"
down_revision: str | None = "0078_corporate_catalog_permissions"
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
                ('job_title.create'),
                ('job_title.read'),
                ('job_title.update'),
                ('job_title.list')
        ) AS permission_row(permission)
        WHERE role_row.name = 'superadmin'
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM corporate_role_permission
        WHERE role = 'superadmin'
          AND permission LIKE 'job_title.%'
        """
    )
