"""browser sessions as revocable devices

Revision ID: 0017_web_devices
Revises: 0016_github_username_grants
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0017_web_devices"
down_revision: str | None = "0016_github_username_grants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "device",
        sa.Column("device_type", sa.String(length=32), nullable=False, server_default="cli"),
    )
    op.add_column("device", sa.Column("approximate_location", sa.String(length=160), nullable=True))
    op.add_column("device", sa.Column("user_agent", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("device", "user_agent")
    op.drop_column("device", "approximate_location")
    op.drop_column("device", "device_type")
