"""Device authorization idempotency, session kind, and device display name."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0096_device_session_semantics"
down_revision: str | None = "0095_minute_installation_heartbeat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "device_authorization",
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
    )
    op.create_unique_constraint(
        "uq_device_authorization_idempotency_key",
        "device_authorization",
        ["idempotency_key"],
    )
    op.add_column(
        "account_session",
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="access"),
    )
    op.create_check_constraint(
        "ck_account_session_kind",
        "account_session",
        "kind in ('access', 'refresh')",
    )
    op.add_column(
        "device",
        sa.Column("display_name", sa.String(length=160), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("device", "display_name")
    op.drop_constraint("ck_account_session_kind", "account_session", type_="check")
    op.drop_column("account_session", "kind")
    op.drop_constraint(
        "uq_device_authorization_idempotency_key", "device_authorization", type_="unique"
    )
    op.drop_column("device_authorization", "idempotency_key")
