"""Review state on the unmapped queue and draft lifecycle for categories."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0106_technology_review_queue"
down_revision: str | None = "0105_technology_unmapped_coordinates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "technology_unmapped_coordinate"


def upgrade() -> None:
    op.drop_constraint("ck_technology_category_state", "technology_category", type_="check")
    op.create_check_constraint(
        "ck_technology_category_state",
        "technology_category",
        "state IN ('draft','active','archived')",
    )
    op.add_column(
        TABLE,
        sa.Column("candidate_technology_id", sa.String(64), nullable=True),
    )
    op.add_column(
        TABLE,
        sa.Column("resolved_technology_id", sa.String(64), nullable=True),
    )
    op.create_foreign_key(
        "fk_unmapped_candidate",
        TABLE,
        "technology",
        ["organization_id", "candidate_technology_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_unmapped_resolved",
        TABLE,
        "technology",
        ["organization_id", "resolved_technology_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_unmapped_resolved", TABLE, type_="foreignkey")
    op.drop_constraint("fk_unmapped_candidate", TABLE, type_="foreignkey")
    op.drop_column(TABLE, "resolved_technology_id")
    op.drop_column(TABLE, "candidate_technology_id")
    op.drop_constraint("ck_technology_category_state", "technology_category", type_="check")
    op.create_check_constraint(
        "ck_technology_category_state",
        "technology_category",
        "state IN ('active','archived')",
    )
