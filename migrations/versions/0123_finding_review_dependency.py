"""Allow ``dependency`` as a finding review verdict.

"Move to dependencies" records an owner decision that keeps the coordinate
visible in the dependency tier instead of rejecting it outright; the stored
review enum therefore gains a third value.
"""

import sqlalchemy as sa
from alembic import op

revision = "0123_finding_review_dependency"
down_revision = "0122_area_permission_family"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TABLE technology_finding_review DROP CONSTRAINT ck_finding_review"))
    op.execute(
        sa.text(
            "ALTER TABLE technology_finding_review ADD CONSTRAINT ck_finding_review "
            "CHECK (review IN ('confirmed','rejected','dependency'))"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE technology_finding_review SET review = 'rejected' WHERE review = 'dependency'"
        )
    )
    op.execute(sa.text("ALTER TABLE technology_finding_review DROP CONSTRAINT ck_finding_review"))
    op.execute(
        sa.text(
            "ALTER TABLE technology_finding_review ADD CONSTRAINT ck_finding_review "
            "CHECK (review IN ('confirmed','rejected'))"
        )
    )
