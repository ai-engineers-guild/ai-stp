"""Seed project link permissions into the ADR-0179 policy table.

Corporate capability projection reads this table. `project.link` is already an
implemented personal capability, and a native usage hook cannot resolve an
installation until the caller's role can create that link.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0104_project_link_permissions"
down_revision: str | None = "0103_report_timezone"
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
                ('project.link'),
                ('project.unlink')
        ) AS permission_row(permission)
        WHERE role_row.name IN ('superadmin', 'lead')
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO corporate_role_permission (organization_id, role, permission)
        SELECT organization_id, name, 'project.link'
        FROM corporate_role
        WHERE name = 'staff'
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM corporate_role_permission
        WHERE role IN ('superadmin', 'lead')
          AND permission IN ('project.link', 'project.unlink')
        """
    )
    op.execute(
        """
        DELETE FROM corporate_role_permission
        WHERE role = 'staff' AND permission = 'project.link'
        """
    )
