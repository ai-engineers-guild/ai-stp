"""Retain governed category identity when removed from new classification choices."""

from collections.abc import Sequence

from alembic import op

revision: str = "0069_retained_category_removal"
down_revision: str | None = "0068_retained_project_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE technology_category ADD COLUMN state VARCHAR(16) NOT NULL DEFAULT 'active'"
    )
    op.execute(
        "ALTER TABLE technology_category ADD CONSTRAINT ck_technology_category_state "
        "CHECK (state IN ('active','archived'))"
    )


def downgrade() -> None:
    """Remove category state for an explicit schema downgrade."""
    op.drop_constraint("ck_technology_category_state", "technology_category", type_="check")
    op.drop_column("technology_category", "state")
