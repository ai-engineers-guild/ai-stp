"""Organization report timezone."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0103_report_timezone"
down_revision: str | None = "0102_usage_collection_policy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "telemetry_policy",
        sa.Column("report_timezone", sa.String(length=64), nullable=False, server_default="UTC"),
    )


def downgrade() -> None:
    op.drop_column("telemetry_policy", "report_timezone")
