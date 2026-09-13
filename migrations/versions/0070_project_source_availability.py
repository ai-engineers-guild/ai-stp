"""Keep repository source availability independent from lifecycle and activity."""

from collections.abc import Sequence

from alembic import op

revision: str = "0070_project_source_availability"
down_revision: str | None = "0069_retained_category_removal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE corporate_project ADD COLUMN source_availability VARCHAR(16) "
        "NOT NULL DEFAULT 'unknown'"
    )
    op.execute(
        "ALTER TABLE corporate_project ADD CONSTRAINT ck_corporate_project_source_availability "
        "CHECK (source_availability IN ('unknown','available','unavailable'))"
    )


def downgrade() -> None:
    """Remove source availability for an explicit schema downgrade."""
    op.drop_constraint(
        "ck_corporate_project_source_availability", "corporate_project", type_="check"
    )
    op.drop_column("corporate_project", "source_availability")
