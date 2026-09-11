"""Add remote organizations, tenant membership and explicit project links.

Revision ID: 0058_b2b00_context_and_project_links
Revises: 0057_catalog_assurance_expiry_compat
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from ulid import ULID

revision: str = "0058_b2b00_context_and_project_links"
down_revision: str | None = "0057_catalog_assurance_expiry_compat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organization",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("owner_account_id", sa.String(64), nullable=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["owner_account_id"], ["account.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("kind in ('personal', 'corporate')", name="ck_organization_kind"),
        sa.CheckConstraint("revision >= 1", name="ck_organization_revision"),
    )
    op.create_index("ix_organization_owner_account_id", "organization", ["owner_account_id"])
    op.create_index(
        "uq_organization_personal_owner",
        "organization",
        ["owner_account_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'personal'"),
    )

    op.create_table(
        "organization_membership",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="member"),
        sa.Column("state", sa.String(16), nullable=False, server_default="active"),
        sa.Column("revision", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "organization_id", "account_id", name="uq_organization_membership_account"
        ),
        sa.CheckConstraint(
            "role in ('owner', 'admin', 'member')", name="ck_organization_membership_role"
        ),
        sa.CheckConstraint(
            "state in ('active', 'suspended')", name="ck_organization_membership_state"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_organization_membership_revision"),
    )
    op.create_index(
        "ix_organization_membership_organization_id",
        "organization_membership",
        ["organization_id"],
    )
    op.create_index(
        "ix_organization_membership_account_id", "organization_membership", ["account_id"]
    )
    connection = op.get_bind()
    account_ids = connection.execute(sa.text("SELECT id FROM account ORDER BY id")).scalars().all()
    for account_id in account_ids:
        organization_id = f"organization_{ULID()}"
        connection.execute(
            sa.text(
                "INSERT INTO organization "
                "(id, kind, owner_account_id, display_name, revision) "
                "VALUES (:id, 'personal', :account_id, 'Personal', 1)"
            ),
            {"id": organization_id, "account_id": account_id},
        )
        connection.execute(
            sa.text(
                "INSERT INTO organization_membership "
                "(organization_id, account_id, role, state, revision) "
                "VALUES (:organization_id, :account_id, 'owner', 'active', 1)"
            ),
            {"organization_id": organization_id, "account_id": account_id},
        )

    op.create_table(
        "project_identity",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("namespace", sa.String(16), nullable=False),
        sa.Column("external_key", sa.String(512), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False, server_default="1"),
        sa.Column("state", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "organization_id", "namespace", "external_key", name="uq_project_identity_external"
        ),
        sa.CheckConstraint(
            "namespace in ('remote', 'provider')", name="ck_project_identity_namespace"
        ),
        sa.CheckConstraint(
            "state in ('active', 'archived', 'deleted')", name="ck_project_identity_state"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_project_identity_revision"),
    )
    op.create_index("ix_project_identity_organization_id", "project_identity", ["organization_id"])

    op.create_table(
        "project_link",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("plan_id", sa.String(64), nullable=False),
        sa.Column("plan_digest", sa.String(71), nullable=False),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("actor_account_id", sa.String(64), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("local_project_id", sa.String(64), nullable=False),
        sa.Column("remote_project_id", sa.String(64), nullable=False),
        sa.Column("provider_project_id", sa.String(64), nullable=True),
        sa.Column("state", sa.String(16), nullable=False, server_default="linked"),
        sa.Column("local_revision", sa.String(128), nullable=False),
        sa.Column("remote_revision", sa.String(128), nullable=False),
        sa.Column("provider_revision", sa.String(128), nullable=True),
        sa.Column("revision", sa.Integer, nullable=False, server_default="1"),
        sa.Column("create_idempotency_key", sa.String(128), nullable=False),
        sa.Column("unlink_idempotency_key", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_account_id"], ["account.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["remote_project_id"], ["project_identity.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["provider_project_id"], ["project_identity.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("create_idempotency_key", name="uq_project_link_create_idempotency"),
        sa.UniqueConstraint("unlink_idempotency_key", name="uq_project_link_unlink_idempotency"),
        sa.CheckConstraint(
            "state in ('linked', 'unlinked', 'conflict')", name="ck_project_link_state"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_project_link_revision"),
    )
    op.create_index("ix_project_link_organization_id", "project_link", ["organization_id"])
    op.create_index(
        "uq_project_link_local_active",
        "project_link",
        ["organization_id", "local_project_id"],
        unique=True,
        postgresql_where=sa.text("state in ('linked', 'conflict')"),
        sqlite_where=sa.text("state in ('linked', 'conflict')"),
    )

    op.create_table(
        "project_link_plan",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("actor_account_id", sa.String(64), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("local_project_id", sa.String(64), nullable=False),
        sa.Column("remote_project_id", sa.String(64), nullable=False),
        sa.Column("provider_project_id", sa.String(64), nullable=True),
        sa.Column("local_revision", sa.String(128), nullable=False),
        sa.Column("remote_revision", sa.String(128), nullable=False),
        sa.Column("provider_revision", sa.String(128), nullable=True),
        sa.Column("authorization_revision", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("plan_digest", sa.String(71), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="ready"),
        sa.Column("link_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_account_id"], ["account.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["remote_project_id"], ["project_identity.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["provider_project_id"], ["project_identity.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["link_id"], ["project_link.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_project_link_plan_key"),
        sa.CheckConstraint(
            "state in ('ready', 'applied', 'expired')", name="ck_project_link_plan_state"
        ),
    )
    op.create_index(
        "ix_project_link_plan_organization_id", "project_link_plan", ["organization_id"]
    )
    op.create_index(
        "ix_project_link_plan_actor_account_id", "project_link_plan", ["actor_account_id"]
    )

    op.create_table(
        "project_unlink_plan",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("link_id", sa.String(64), nullable=False),
        sa.Column("actor_account_id", sa.String(64), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("local_project_id", sa.String(64), nullable=False),
        sa.Column("remote_project_id", sa.String(64), nullable=False),
        sa.Column("provider_project_id", sa.String(64), nullable=True),
        sa.Column("expected_link_revision", sa.Integer, nullable=False),
        sa.Column("local_revision", sa.String(128), nullable=False),
        sa.Column("remote_revision", sa.String(128), nullable=False),
        sa.Column("provider_revision", sa.String(128), nullable=True),
        sa.Column("authorization_revision", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("plan_digest", sa.String(71), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="ready"),
        sa.Column("confirmation_idempotency_key", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["link_id"], ["project_link.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_account_id"], ["account.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_project_unlink_plan_key"
        ),
        sa.UniqueConstraint(
            "confirmation_idempotency_key", name="uq_project_unlink_plan_confirmation_key"
        ),
        sa.CheckConstraint(
            "state in ('ready', 'applied', 'expired')", name="ck_project_unlink_plan_state"
        ),
    )
    op.create_index(
        "ix_project_unlink_plan_organization_id", "project_unlink_plan", ["organization_id"]
    )
    op.create_index("ix_project_unlink_plan_link_id", "project_unlink_plan", ["link_id"])
    op.create_index(
        "ix_project_unlink_plan_actor_account_id", "project_unlink_plan", ["actor_account_id"]
    )

    op.create_table(
        "project_sync_plan",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("link_id", sa.String(64), nullable=False),
        sa.Column("actor_account_id", sa.String(64), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("expected_link_revision", sa.Integer, nullable=False),
        sa.Column("local_revision", sa.String(128), nullable=False),
        sa.Column("remote_revision", sa.String(128), nullable=False),
        sa.Column("provider_revision", sa.String(128), nullable=True),
        sa.Column("conflict_code", sa.String(32), nullable=True),
        sa.Column("common_ancestor_revision", sa.String(128), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("plan_digest", sa.String(71), nullable=False),
        sa.Column("apply_idempotency_key", sa.String(128), nullable=True),
        sa.Column("result", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["link_id"], ["project_link.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_account_id"], ["account.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("link_id", "idempotency_key", name="uq_project_sync_plan_idempotency"),
        sa.UniqueConstraint("apply_idempotency_key", name="uq_project_sync_plan_apply_idempotency"),
        sa.CheckConstraint(
            "state in ('ready', 'conflict', 'applied', 'failed', 'unknown')",
            name="ck_project_sync_plan_state",
        ),
        sa.CheckConstraint(
            "action in ('noop', 'local_to_remote', 'remote_to_local', 'merge_required')",
            name="ck_project_sync_plan_action",
        ),
    )
    op.create_index("ix_project_sync_plan_link_id", "project_sync_plan", ["link_id"])
    op.create_index(
        "ix_project_sync_plan_actor_account_id", "project_sync_plan", ["actor_account_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_project_sync_plan_actor_account_id", table_name="project_sync_plan")
    op.drop_index("ix_project_sync_plan_link_id", table_name="project_sync_plan")
    op.drop_table("project_sync_plan")
    op.drop_index("ix_project_unlink_plan_actor_account_id", table_name="project_unlink_plan")
    op.drop_index("ix_project_unlink_plan_link_id", table_name="project_unlink_plan")
    op.drop_index("ix_project_unlink_plan_organization_id", table_name="project_unlink_plan")
    op.drop_table("project_unlink_plan")
    op.drop_index("ix_project_link_plan_actor_account_id", table_name="project_link_plan")
    op.drop_index("ix_project_link_plan_organization_id", table_name="project_link_plan")
    op.drop_table("project_link_plan")
    op.drop_index("uq_project_link_local_active", table_name="project_link")
    op.drop_index("ix_project_link_organization_id", table_name="project_link")
    op.drop_table("project_link")
    op.drop_index("ix_project_identity_organization_id", table_name="project_identity")
    op.drop_table("project_identity")
    op.drop_index("ix_organization_membership_account_id", table_name="organization_membership")
    op.drop_index(
        "ix_organization_membership_organization_id", table_name="organization_membership"
    )
    op.drop_table("organization_membership")
    op.drop_index("uq_organization_personal_owner", table_name="organization")
    op.drop_index("ix_organization_owner_account_id", table_name="organization")
    op.drop_table("organization")
