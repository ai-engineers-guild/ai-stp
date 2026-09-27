"""Retain unmapped scan coordinates as the registry review queue."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0097_technology_unmapped_coordinates"
down_revision: str | None = "0096_heartbeat_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT = (
    "current_setting('ai_stp.organization_id', true) = '*' OR "
    "organization_id = current_setting('ai_stp.organization_id', true)"
)
TABLE = "technology_unmapped_coordinate"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("coordinate", sa.String(512), nullable=False),
        sa.Column("scope", sa.String(128), nullable=False),
        sa.Column("scan_id", sa.String(64), nullable=False),
        sa.Column("project_namespace", sa.String(16), server_default="remote", nullable=False),
        sa.PrimaryKeyConstraint("organization_id", "project_id", "scope", "kind", "coordinate"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id", "project_namespace"],
            [
                "project_identity.organization_id",
                "project_identity.id",
                "project_identity.namespace",
            ],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "kind IN ('package','image','executable','configuration','alias')",
            name="ck_unmapped_kind",
        ),
        sa.CheckConstraint("project_namespace = 'remote'", name="ck_unmapped_namespace"),
    )
    op.create_index("ix_unmapped_coordinate_scan", TABLE, ["organization_id", "scan_id"])
    op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f'CREATE POLICY "{TABLE}_tenant_policy" ON "{TABLE}" USING ({TENANT}) WITH CHECK ({TENANT})'
    )
    op.execute(
        f'CREATE TRIGGER "{TABLE}_identity_immutable" BEFORE INSERT OR UPDATE '
        f'ON "{TABLE}" FOR EACH ROW EXECUTE FUNCTION '
        "ai_stp_technology_identity_immutable()"
    )


def downgrade() -> None:
    op.drop_table(TABLE)
