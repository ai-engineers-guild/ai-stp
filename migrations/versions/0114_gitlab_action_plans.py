"""GitLab administration grants: durable action plans for confirmed mutations."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0114_gitlab_action_plans"
down_revision: str | Sequence[str] | None = "0113_gitlab_source_connector"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gitlab_action_plan",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "account_id",
            sa.String(64),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "device_id",
            sa.String(64),
            sa.ForeignKey("device.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "connector_id",
            sa.String(64),
            sa.ForeignKey("gitlab_connector.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("gitlab_base_url", sa.String(512), nullable=False),
        sa.Column("authorization_revision", sa.String(64), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=True),
        sa.Column("namespace_id", sa.BigInteger(), nullable=True),
        sa.Column("path_with_namespace", sa.String(256), nullable=True),
        sa.Column("previous_visibility", sa.String(16), nullable=True),
        sa.Column("recipient_id", sa.BigInteger(), nullable=True),
        sa.Column("recipient", sa.String(255), nullable=True),
        sa.Column("access_level", sa.String(16), nullable=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("path", sa.String(255), nullable=True),
        sa.Column("target_visibility", sa.String(16), nullable=True),
        sa.Column("plan_hash", sa.String(71), nullable=False),
        sa.Column("request_hash", sa.String(71), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("result", sa.String(32), nullable=True),
        sa.Column("error_reason", sa.String(64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("account_id", "idempotency_key", name="uq_gitlab_action_request"),
    )
    op.add_column("gitlab_action_plan", sa.Column("organization_id", sa.String(64), nullable=True))
    op.execute(
        "UPDATE gitlab_action_plan AS source SET organization_id = (SELECT organization.id "
        "FROM organization WHERE organization.owner_account_id = source.account_id "
        "AND organization.kind = 'personal') WHERE organization_id IS NULL"
    )
    op.alter_column("gitlab_action_plan", "organization_id", nullable=False)
    op.create_foreign_key(
        "fk_gitlab_action_plan_organization",
        "gitlab_action_plan",
        "organization",
        ["organization_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_gitlab_action_plan_organization_id", "gitlab_action_plan", ["organization_id"]
    )


def downgrade() -> None:
    op.drop_table("gitlab_action_plan")
