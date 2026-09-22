"""Seed runtime usage permission keys into the ADR-0179 policy table."""

from collections.abc import Sequence

from alembic import op

revision: str = "0088_runtime_usage_permissions"
down_revision: str | None = "0087_runtime_usage_event"
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
                ('telemetry_usage.ingest'),
                ('telemetry_usage.read'),
                ('telemetry_usage.events'),
                ('telemetry_usage.export')
        ) AS permission_row(permission)
        WHERE role_row.name = 'superadmin'
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
                ('telemetry_usage.ingest'),
                ('telemetry_usage.read')
        ) AS permission_row(permission)
        WHERE role_row.name = 'lead'
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO corporate_role_permission (organization_id, role, permission)
        SELECT organization_id, name, 'telemetry_usage.ingest'
        FROM corporate_role
        WHERE name = 'staff'
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM corporate_role_permission
        WHERE role IN ('superadmin', 'lead', 'staff')
          AND permission IN (
              'telemetry_usage.ingest',
              'telemetry_usage.read',
              'telemetry_usage.events',
              'telemetry_usage.export'
          )
        """
    )
