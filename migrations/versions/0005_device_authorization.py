"""device authorization pending codes (RFC 8628 device flow)

Revision ID: 0005_device_authorization
Revises: 0004_oauth_identity_avatar
Create Date: 2026-08-07

Stores pending CLI device-code authorizations until a human approves them in
the browser and the CLI exchanges the code for a session bound to a device key.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_device_authorization"
down_revision: str | None = "0004_oauth_identity_avatar"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "device_authorization",
        sa.Column("device_code", sa.String(length=256), primary_key=True),
        sa.Column("user_code", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("account_id", sa.String(length=64), nullable=True),
        sa.Column("interval_seconds", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_poll_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status in ('pending', 'approved', 'declined', 'consumed')",
            name="ck_device_authorization_status",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name="fk_device_authorization_account",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("user_code", name="uq_device_authorization_user_code"),
    )
    op.create_index(
        "ix_device_authorization_status_expires",
        "device_authorization",
        ["status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_device_authorization_status_expires", table_name="device_authorization")
    op.drop_table("device_authorization")
