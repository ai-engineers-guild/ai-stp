"""Allow an installation to report a partial operation through its heartbeat."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0093_partial_installation_heartbeat"
down_revision: str | None = "0092_corporate_dashboard"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "installation_heartbeat"
CONSTRAINT = "ck_installation_heartbeat_reported_state"


def _replace(states: str) -> None:
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_constraint(CONSTRAINT, type_="check")
        batch.create_check_constraint(CONSTRAINT, f"reported_state in ({states})")


def upgrade() -> None:
    _replace("'active', 'partial', 'failing', 'disabled'")


def downgrade() -> None:
    has_partial = op.get_bind().scalar(
        sa.text("SELECT 1 FROM installation_heartbeat WHERE reported_state = 'partial' LIMIT 1")
    )
    if has_partial:
        raise RuntimeError("resolve partial installation heartbeats before downgrade")
    _replace("'active', 'failing', 'disabled'")
