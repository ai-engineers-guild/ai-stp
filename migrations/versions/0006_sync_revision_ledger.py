"""private registry revision sync ledger (SPEC-025, ADR-0045)

Revision ID: 0006_sync_revision_ledger
Revises: 0005_device_authorization
Create Date: 2026-08-07

Four account-scoped roles: immutable revision, one head per entity, durable
event receipt, and ordered accepted outbox. No cursor table and no broker job.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_sync_revision_ledger"
down_revision: str | None = "0005_device_authorization"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sync_revision",
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("revision_id", sa.String(length=73), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("entity_kind", sa.String(length=32), nullable=False),
        sa.Column("parent_revision_ids", sa.JSON(), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("content_digest", sa.String(length=71), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "accepted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "entity_kind in ("
            "'developer_passport', 'device_summary', 'component_private', "
            "'setup_private', 'unverified_consent')",
            name="ck_sync_revision_entity_kind",
        ),
        sa.CheckConstraint(
            "operation in ('upsert', 'tombstone')",
            name="ck_sync_revision_operation",
        ),
        sa.CheckConstraint("schema_version = 1", name="ck_sync_revision_schema_version"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name="fk_sync_revision_account",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("account_id", "revision_id", name="pk_sync_revision"),
    )
    op.create_index(
        "ix_sync_revision_account_entity",
        "sync_revision",
        ["account_id", "entity_id"],
    )

    op.create_table(
        "sync_entity_head",
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("revision_id", sa.String(length=73), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name="fk_sync_entity_head_account",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("account_id", "entity_id", name="pk_sync_entity_head"),
    )

    op.create_table(
        "sync_event_receipt",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("revision_id", sa.String(length=73), nullable=True),
        sa.Column("server_head_revision_id", sa.String(length=73), nullable=True),
        sa.Column("response_body", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "state in ('accepted', 'rejected', 'conflict', 'superseded')",
            name="ck_sync_event_receipt_state",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name="fk_sync_event_receipt_account",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "account_id",
            "idempotency_key",
            name="uq_sync_event_receipt_account_idempotency",
        ),
    )
    op.create_index(
        "ix_sync_event_receipt_account_id",
        "sync_event_receipt",
        ["account_id"],
    )

    op.create_table(
        "sync_outbox",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("entity_kind", sa.String(length=32), nullable=False),
        sa.Column("revision_id", sa.String(length=73), nullable=False),
        sa.Column("parent_revision_ids", sa.JSON(), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("content_digest", sa.String(length=71), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "accepted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name="fk_sync_outbox_account",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("account_id", "sequence", name="uq_sync_outbox_account_sequence"),
        sa.UniqueConstraint("account_id", "event_id", name="uq_sync_outbox_account_event"),
    )
    op.create_index(
        "ix_sync_outbox_account_sequence",
        "sync_outbox",
        ["account_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_index("ix_sync_outbox_account_sequence", table_name="sync_outbox")
    op.drop_table("sync_outbox")
    op.drop_index("ix_sync_event_receipt_account_id", table_name="sync_event_receipt")
    op.drop_table("sync_event_receipt")
    op.drop_table("sync_entity_head")
    op.drop_index("ix_sync_revision_account_entity", table_name="sync_revision")
    op.drop_table("sync_revision")
