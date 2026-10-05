"""Read-only GitLab connector: scoped grants and immutable source bindings."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0113_gitlab_source_connector"
down_revision: str | Sequence[str] | None = "0112_replay_skipped_feature_chain"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GITLAB_TABLES = ("gitlab_connector", "gitlab_authorization_flow", "gitlab_source_binding")


def upgrade() -> None:
    op.create_table(
        "gitlab_connector",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "account_id",
            sa.String(64),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("gitlab_base_url", sa.String(512), nullable=False),
        sa.Column("connection_organization_id", sa.String(64), nullable=False),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("gitlab_subject", sa.String(255), nullable=False),
        sa.Column("authorization_revision", sa.String(64), nullable=False),
        sa.Column("token_ciphertext", sa.Text(), nullable=True),
        sa.Column("refresh_token_ciphertext", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("projects", sa.JSON(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "account_id", "gitlab_base_url", "purpose", name="uq_gitlab_connector_owner"
        ),
    )
    op.create_table(
        "gitlab_authorization_flow",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column(
            "account_id",
            sa.String(64),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(128), nullable=False),
        sa.Column("connection_organization_id", sa.String(64), nullable=False),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("locale", sa.String(2), nullable=False),
        sa.Column("callback_uri", sa.String(512), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "gitlab_source_binding",
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
            sa.ForeignKey("gitlab_connector.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("gitlab_base_url", sa.String(512), nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("namespace_id", sa.BigInteger(), nullable=False),
        sa.Column("path_with_namespace", sa.String(256), nullable=False),
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
        sa.UniqueConstraint("account_id", "idempotency_key", name="uq_gitlab_source_request"),
    )
    for table_name in _GITLAB_TABLES:
        op.add_column(table_name, sa.Column("organization_id", sa.String(64), nullable=True))
        op.execute(
            "UPDATE " + table_name + " AS source SET organization_id = (SELECT organization.id "
            "FROM organization WHERE organization.owner_account_id = source.account_id "
            "AND organization.kind = 'personal') WHERE organization_id IS NULL"
        )
        op.alter_column(table_name, "organization_id", nullable=False)
        op.create_foreign_key(
            "fk_" + table_name + "_organization",
            table_name,
            "organization",
            ["organization_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index("ix_" + table_name + "_organization_id", table_name, ["organization_id"])
    op.add_column(
        "publication_plan",
        sa.Column("gitlab_source_binding_id", sa.String(64), nullable=True),
    )
    op.create_foreign_key(
        "fk_publication_gitlab_source_binding",
        "publication_plan",
        "gitlab_source_binding",
        ["gitlab_source_binding_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_publication_gitlab_source_binding",
        "publication_plan",
        ["gitlab_source_binding_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_publication_gitlab_source_binding", "publication_plan", type_="unique")
    op.drop_constraint(
        "fk_publication_gitlab_source_binding", "publication_plan", type_="foreignkey"
    )
    op.drop_column("publication_plan", "gitlab_source_binding_id")
    for table_name in _GITLAB_TABLES:
        op.drop_index("ix_" + table_name + "_organization_id", table_name=table_name)
        op.drop_constraint("fk_" + table_name + "_organization", table_name, type_="foreignkey")
        op.drop_column(table_name, "organization_id")
    op.drop_table("gitlab_source_binding")
    op.drop_table("gitlab_authorization_flow")
    op.drop_table("gitlab_connector")
