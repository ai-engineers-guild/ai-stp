"""Allow direct component invocations without inventing a setup."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0101_direct_component_usage"
down_revision: str | None = "0100_usage_evidence_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column, length in (
        ("setup_stable_id", 128),
        ("setup_version", 32),
        ("setup_passport_digest", 80),
    ):
        op.alter_column(
            "runtime_usage_event",
            column,
            existing_type=sa.String(length),
            nullable=True,
        )
    op.create_check_constraint(
        "ck_runtime_usage_setup_coordinate",
        "runtime_usage_event",
        "(setup_stable_id IS NULL AND setup_version IS NULL AND setup_passport_digest IS NULL) "
        "OR (setup_stable_id IS NOT NULL AND setup_version IS NOT NULL "
        "AND setup_passport_digest IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_runtime_usage_setup_coordinate", "runtime_usage_event", type_="check")
    for column, length in (
        ("setup_stable_id", 128),
        ("setup_version", 32),
        ("setup_passport_digest", 80),
    ):
        op.alter_column(
            "runtime_usage_event",
            column,
            existing_type=sa.String(length),
            nullable=False,
        )
