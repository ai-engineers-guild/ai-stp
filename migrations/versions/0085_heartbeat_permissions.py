"""Seed the telemetry.read permission for existing corporate roles (#215)."""

from collections.abc import Sequence

from alembic import op

revision: str = "0085_heartbeat_permissions"
down_revision: str | None = "0084_installation_heartbeat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO corporate_role_permission (organization_id, role, permission)
        SELECT organization_id, name, 'telemetry.read'
        FROM corporate_role
        WHERE name IN ('superadmin', 'lead')
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM corporate_role_permission
        WHERE permission = 'telemetry.read' AND role IN ('superadmin', 'lead')
        """
    )
