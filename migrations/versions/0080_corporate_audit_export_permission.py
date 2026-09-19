"""Backfill audit export permission for existing corporate superadmins."""

from collections.abc import Sequence

from alembic import op

revision: str = "0080_corporate_audit_export_permission"
down_revision: str | None = "0079_corporate_job_title_permissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO corporate_role_permission (organization_id, role, permission)
        SELECT organization_id, name, 'audit.export'
        FROM corporate_role
        WHERE name = 'superadmin'
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM corporate_role_permission
        WHERE role = 'superadmin' AND permission = 'audit.export'
        """
    )
