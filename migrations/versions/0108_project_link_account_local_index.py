"""Index project_link by (organization_id, local_project_id).

The link writer resolves a local project to its tenant-scoped row on every
sync; the partial uniqueness index does not cover the plain lookup shape, so
the model declared the plain index but no migration ever created it.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0108_project_link_account_local_index"
down_revision: str | None = "0107_device_public_key_global"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "project_link"
INDEX = "ix_project_link_account_local"


def upgrade() -> None:
    op.create_index(INDEX, TABLE, ["organization_id", "local_project_id"])


def downgrade() -> None:
    op.drop_index(INDEX, table_name=TABLE)
