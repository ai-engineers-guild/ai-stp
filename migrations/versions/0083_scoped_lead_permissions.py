"""Backfill scoped lead permissions and catalog_object.delete for superadmin."""

from collections.abc import Sequence

from alembic import op

revision: str = "0083_scoped_lead_permissions"
down_revision: str | None = "0082_bulk_assignment_distribution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO corporate_role_permission (organization_id, role, permission)
        SELECT organization_id, name, 'catalog_object.delete'
        FROM corporate_role
        WHERE name = 'superadmin'
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO corporate_role_permission (organization_id, role, permission)
        SELECT role_row.organization_id, role_row.name, permission_row.permission
        FROM corporate_role AS role_row
        CROSS JOIN (
            VALUES
                ('member.update'),
                ('member.delete'),
                ('team.update'),
                ('team.delete')
        ) AS permission_row(permission)
        WHERE role_row.name = 'lead'
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        DELETE FROM corporate_role_permission
        WHERE role = 'lead' AND permission = 'project.update'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM corporate_role_permission
        WHERE role = 'superadmin' AND permission = 'catalog_object.delete'
        """
    )
    op.execute(
        """
        DELETE FROM corporate_role_permission
        WHERE role = 'lead'
          AND permission IN ('member.update', 'member.delete', 'team.update', 'team.delete')
        """
    )
    op.execute(
        """
        INSERT INTO corporate_role_permission (organization_id, role, permission)
        SELECT organization_id, name, 'project.update'
        FROM corporate_role
        WHERE name = 'lead'
        ON CONFLICT DO NOTHING
        """
    )
