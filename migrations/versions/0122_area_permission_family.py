"""Backfill the ``area.*`` permission family for existing corporate roles.

Technology areas moved off the shared ``category.*`` verbs onto dedicated
``area.*`` permissions. Every role grant that covers a ``category.*`` verb
receives the matching ``area.*`` verb so existing custom and built-in roles keep
exactly the access they had before the split.
"""

import sqlalchemy as sa
from alembic import op

revision = "0122_area_permission_family"
down_revision = "0121_corporate_fixture_demo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO corporate_role_permission (organization_id, role, permission)
            SELECT organization_id, role, 'area.' || substring(permission from 10)
            FROM corporate_role_permission
            WHERE permission LIKE 'category.%'
            ON CONFLICT DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM corporate_role_permission WHERE permission LIKE 'area.%'"))
