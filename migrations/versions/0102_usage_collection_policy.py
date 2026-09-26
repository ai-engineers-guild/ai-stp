"""Independent collection and local registration controls for usage facts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0102_usage_collection_policy"
down_revision: str | None = "0101_direct_component_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "telemetry_policy",
        sa.Column(
            "usage_collection_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "telemetry_policy",
        sa.Column(
            "usage_registration_required", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.create_check_constraint(
        "ck_telemetry_policy_usage_required",
        "telemetry_policy",
        "NOT usage_registration_required OR usage_collection_enabled",
    )


def downgrade() -> None:
    op.drop_constraint("ck_telemetry_policy_usage_required", "telemetry_policy", type_="check")
    op.drop_column("telemetry_policy", "usage_registration_required")
    op.drop_column("telemetry_policy", "usage_collection_enabled")
