"""Persist the last publish receipt on public_profile for idempotent retries."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0097_profile_publish_idempotency"
down_revision: str | None = "0096_device_session_semantics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "public_profile",
        sa.Column("last_publish_key", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "public_profile",
        sa.Column("last_publish_fingerprint", sa.String(length=71), nullable=True),
    )
    op.add_column(
        "public_profile",
        sa.Column("last_publish_response", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("public_profile", "last_publish_response")
    op.drop_column("public_profile", "last_publish_fingerprint")
    op.drop_column("public_profile", "last_publish_key")
