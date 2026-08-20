"""create sprint-1 platform storage tables

Revision ID: 0002_sprint1_core
Revises: 0001_create_job
Create Date: 2026-08-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_sprint1_core"
down_revision: str | None = "0001_create_job"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "account",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_table(
        "oauth_identity",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("email_verified", sa.Boolean(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "state in ('pending', 'linked', 'conflict', 'revoked')",
            name="ck_oauth_identity_state",
        ),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "provider",
            "provider_subject",
            name="uq_oauth_identity_provider_subject",
        ),
    )
    op.create_index("ix_oauth_identity_account_id", "oauth_identity", ["account_id"])
    op.create_table(
        "device",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("state in ('active', 'revoked')", name="ck_device_state"),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("account_id", "public_key", name="uq_device_account_public_key"),
    )
    op.create_index("ix_device_account_id", "device", ["account_id"])
    op.create_table(
        "account_session",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_account_session_account_id", "account_session", ["account_id"])
    op.create_index("ix_account_session_device_id", "account_session", ["device_id"])
    op.create_index("ix_account_session_expires_at", "account_session", ["expires_at"])
    op.create_table(
        "catalog_metadata",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_account_id", sa.String(length=64), nullable=False),
        sa.Column("object_kind", sa.String(length=32), nullable=False),
        sa.Column("stable_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=True),
        sa.Column("current_revision_id", sa.String(length=73), nullable=False),
        sa.Column("visibility", sa.String(length=32), nullable=False),
        sa.Column("lifecycle_state", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["owner_account_id"], ["account.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("object_kind", "stable_id", name="uq_catalog_metadata_kind_stable_id"),
        sa.UniqueConstraint("stable_id", "version", name="uq_catalog_metadata_stable_id_version"),
    )
    op.create_index(
        "ix_catalog_metadata_owner_account_id",
        "catalog_metadata",
        ["owner_account_id"],
    )
    op.create_index("ix_catalog_metadata_stable_id", "catalog_metadata", ["stable_id"])
    op.create_table(
        "object_location",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("catalog_metadata_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=64), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("digest", sa.String(length=71), nullable=False),
        sa.Column("content_id", sa.String(length=71), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("size_bytes >= 0", name="ck_object_location_size_non_negative"),
        sa.ForeignKeyConstraint(
            ["catalog_metadata_id"],
            ["catalog_metadata.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "catalog_metadata_id",
            "purpose",
            name="uq_object_location_metadata_purpose",
        ),
        sa.UniqueConstraint("object_key", name="uq_object_location_object_key"),
    )
    op.create_index(
        "ix_object_location_catalog_metadata_id",
        "object_location",
        ["catalog_metadata_id"],
    )
    op.create_table(
        "audit_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_account_id", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("target_table", sa.String(length=128), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["actor_account_id"], ["account.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_audit_event_actor_account_id", "audit_event", ["actor_account_id"])
    op.execute(
        """
        CREATE FUNCTION reject_audit_event_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'audit_event is append-only';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_event_append_only
        BEFORE UPDATE OR DELETE ON audit_event
        FOR EACH ROW EXECUTE FUNCTION reject_audit_event_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER audit_event_append_only ON audit_event")
    op.execute("DROP FUNCTION reject_audit_event_mutation()")
    op.drop_index("ix_audit_event_actor_account_id", table_name="audit_event")
    op.drop_table("audit_event")
    op.drop_index("ix_object_location_catalog_metadata_id", table_name="object_location")
    op.drop_table("object_location")
    op.drop_index("ix_catalog_metadata_stable_id", table_name="catalog_metadata")
    op.drop_index("ix_catalog_metadata_owner_account_id", table_name="catalog_metadata")
    op.drop_table("catalog_metadata")
    op.drop_index("ix_account_session_expires_at", table_name="account_session")
    op.drop_index("ix_account_session_device_id", table_name="account_session")
    op.drop_index("ix_account_session_account_id", table_name="account_session")
    op.drop_table("account_session")
    op.drop_index("ix_device_account_id", table_name="device")
    op.drop_table("device")
    op.drop_index("ix_oauth_identity_account_id", table_name="oauth_identity")
    op.drop_table("oauth_identity")
    op.drop_table("account")
