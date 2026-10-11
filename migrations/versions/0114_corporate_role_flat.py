"""Corporate roles are flat.

Role inheritance through `corporate_role.parent_role` is removed: a role's
permission set is exactly its `corporate_role_permission` rows. Before the
column is dropped, every role's effective (inherited) permissions are
flattened into its own rows so the effective set is preserved.

Downgrade restores the nullable column only; the removed hierarchy edges are
not recoverable.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0114_corporate_role_flat"
down_revision: str | tuple[str, str] | None = (
    "0113_technology_category_icon",
    "0123_finding_review_dependency",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Materialize each role's transitive ancestor permissions into its own
    # corporate_role_permission rows. The seen-array walk terminates on
    # cycles; DISTINCT + ON CONFLICT dedupes already-direct permissions.
    op.execute(
        sa.text(
            """
            WITH RECURSIVE walk AS (
                SELECT
                    organization_id,
                    name AS role_name,
                    parent_role AS ancestor,
                    ARRAY[name]::varchar[] AS seen
                FROM corporate_role
                WHERE parent_role IS NOT NULL
              UNION ALL
                SELECT
                    w.organization_id,
                    w.role_name,
                    r.parent_role,
                    w.seen || r.name
                FROM walk w
                JOIN corporate_role r
                  ON r.organization_id = w.organization_id
                 AND r.name = w.ancestor
                WHERE r.parent_role IS NOT NULL
                  AND NOT r.name = ANY(w.seen)
            )
            INSERT INTO corporate_role_permission (organization_id, role, permission)
            SELECT DISTINCT w.organization_id, w.role_name, p.permission
            FROM walk w
            JOIN corporate_role_permission p
              ON p.organization_id = w.organization_id
             AND p.role = w.ancestor
            ON CONFLICT DO NOTHING
            """
        )
    )
    op.drop_column("corporate_role", "parent_role")


def downgrade() -> None:
    op.add_column("corporate_role", sa.Column("parent_role", sa.String(64), nullable=True))
