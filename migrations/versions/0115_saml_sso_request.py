"""SAML SSO: pending SP-initiated requests and assertion replay guard."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0115_saml_sso_request"
down_revision: str | Sequence[str] | None = "0114_gitlab_action_plans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "saml_sso_request",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("relay_state", sa.String(80), nullable=False),
        sa.Column("flow", sa.String(8), nullable=False, server_default="login"),
        sa.Column("client", sa.String(8), nullable=False, server_default="web"),
        sa.Column("return_to", sa.String(512), nullable=True),
        sa.Column(
            "link_account_id",
            sa.String(64),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "device_id",
            sa.String(64),
            sa.ForeignKey("device.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("assertion_id", sa.String(255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("relay_state", name="uq_saml_sso_request_relay_state"),
        sa.CheckConstraint("flow in ('login', 'link')", name="ck_saml_sso_request_flow"),
    )
    op.create_index("ix_saml_sso_request_expires_at", "saml_sso_request", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_saml_sso_request_expires_at", table_name="saml_sso_request")
    op.drop_table("saml_sso_request")
