"""Remember the category selected for a finding without replacing global classifications."""

import sqlalchemy as sa
from alembic import op

revision = "0120_finding_review_category"
down_revision = "0119_corporate_repository_binding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "technology_finding_review", sa.Column("category_id", sa.String(64), nullable=True)
    )
    op.create_foreign_key(
        "fk_finding_review_category",
        "technology_finding_review",
        "technology_category",
        ["organization_id", "category_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_finding_review_category", "technology_finding_review", type_="foreignkey"
    )
    op.drop_column("technology_finding_review", "category_id")
