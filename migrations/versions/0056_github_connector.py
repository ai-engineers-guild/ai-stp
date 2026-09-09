"""Add scoped GitHub authorization, immutable source bindings and exact plans."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0056_github_connector"
down_revision: str | None = "0055_component_media_digest_compat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "github_connector",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "account_id",
            sa.String(64),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("github_subject", sa.String(64), nullable=False),
        sa.Column("authorization_revision", sa.String(64), nullable=False),
        sa.Column("token_ciphertext", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("installations", sa.JSON(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("account_id", "purpose", name="uq_github_connector_owner"),
    )
    op.create_table(
        "github_authorization_flow",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column(
            "account_id",
            sa.String(64),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(128), nullable=False),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("locale", sa.String(2), nullable=False),
        sa.Column("callback_uri", sa.String(512), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "github_source_binding",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "account_id",
            sa.String(64),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "connector_id",
            sa.String(64),
            sa.ForeignKey("github_connector.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("installation_id", sa.BigInteger(), nullable=False),
        sa.Column("repository_id", sa.BigInteger(), nullable=False),
        sa.Column("repository_owner_id", sa.BigInteger(), nullable=False),
        sa.Column("repository_full_name", sa.String(256), nullable=False),
        sa.Column("commit", sa.String(40), nullable=False),
        sa.Column("subpath", sa.String(512), nullable=False),
        sa.Column("source_visibility", sa.String(16), nullable=False),
        sa.Column("content_digest", sa.String(71), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("inventory", sa.JSON(), nullable=False),
        sa.Column("request_hash", sa.String(71), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("passport_digest", sa.String(71), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("account_id", "idempotency_key", name="uq_github_source_request"),
    )
    op.add_column("publication_plan", sa.Column("source_binding_id", sa.String(64), nullable=True))
    op.create_foreign_key(
        "fk_publication_source_binding",
        "publication_plan",
        "github_source_binding",
        ["source_binding_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_publication_source_binding", "publication_plan", ["source_binding_id"]
    )
    op.create_table(
        "github_action_plan",
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
            sa.ForeignKey("github_connector.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("authorization_revision", sa.String(64), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("installation_id", sa.BigInteger(), nullable=False),
        sa.Column("repository_id", sa.BigInteger(), nullable=False),
        sa.Column("repository_owner_id", sa.BigInteger(), nullable=False),
        sa.Column("repository_owner_type", sa.String(16), nullable=False),
        sa.Column("repository_full_name", sa.String(256), nullable=False),
        sa.Column("previous_visibility", sa.String(16), nullable=False),
        sa.Column("recipient", sa.String(39), nullable=True),
        sa.Column("permission", sa.String(16), nullable=True),
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
        sa.UniqueConstraint("account_id", "idempotency_key", name="uq_github_action_request"),
    )
    op.create_table(
        "distribution_visibility_plan",
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
            "metadata_id",
            sa.Integer(),
            sa.ForeignKey("catalog_metadata.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("passport_digest", sa.String(71), nullable=False),
        sa.Column("ownership_revision_id", sa.String(73), nullable=True),
        sa.Column("previous_visibility", sa.String(16), nullable=False),
        sa.Column("visibility", sa.String(16), nullable=False),
        sa.Column("plan_hash", sa.String(71), nullable=False),
        sa.Column("request_hash", sa.String(71), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "account_id", "idempotency_key", name="uq_distribution_visibility_request"
        ),
    )


def downgrade() -> None:
    op.drop_table("distribution_visibility_plan")
    op.drop_table("github_action_plan")
    op.drop_constraint("uq_publication_source_binding", "publication_plan", type_="unique")
    op.drop_constraint("fk_publication_source_binding", "publication_plan", type_="foreignkey")
    op.drop_column("publication_plan", "source_binding_id")
    op.drop_table("github_source_binding")
    op.drop_table("github_authorization_flow")
    op.drop_table("github_connector")
