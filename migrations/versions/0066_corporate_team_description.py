"""Add tenant-private team descriptions without changing existing assignments."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0066_corporate_team_description"
down_revision: str | None = "0065_dynamic_corporate_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "corporate_team",
        sa.Column("description", sa.String(2000), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("corporate_team", "description")
