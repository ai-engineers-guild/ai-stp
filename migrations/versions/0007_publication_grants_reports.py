"""publication plans, validation, grants, reports (SPEC-026, ADR-0067)

Revision ID: 0007_publication_grants_reports
Revises: 0006_sync_revision_ledger
Create Date: 2026-08-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_publication_grants_reports"
down_revision: str | None = "0006_sync_revision_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "publication_plan",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("actor_account_id", sa.String(length=64), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("object_kind", sa.String(length=32), nullable=False),
        sa.Column("stable_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("content_digest", sa.String(length=71), nullable=False),
        sa.Column("policy_version", sa.String(length=32), nullable=False),
        sa.Column("plan_hash", sa.String(length=128), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("passport", sa.JSON(), nullable=False),
        sa.Column("attestations", sa.JSON(), nullable=False),
        sa.Column("effects", sa.JSON(), nullable=False),
        sa.Column("component_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("confirm_idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state in ("
            "'draft', 'ready', 'validating', 'publish_planned', "
            "'published', 'failed', 'cancelled', 'stale')",
            name="ck_publication_plan_state",
        ),
        sa.CheckConstraint(
            "object_kind in ('component', 'setup')",
            name="ck_publication_plan_object_kind",
        ),
        sa.ForeignKeyConstraint(["actor_account_id"], ["account.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "actor_account_id",
            "idempotency_key",
            name="uq_publication_plan_actor_idempotency",
        ),
    )
    op.create_index(
        "ix_publication_plan_actor_account_id", "publication_plan", ["actor_account_id"]
    )
    op.create_index("ix_publication_plan_stable_id", "publication_plan", ["stable_id"])

    op.create_table(
        "validation_snapshot",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("plan_id", sa.String(length=64), nullable=False),
        sa.Column("content_digest", sa.String(length=71), nullable=False),
        sa.Column("policy_version", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("component_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state in ('running', 'passed', 'warning', 'failed', 'degraded')",
            name="ck_validation_snapshot_state",
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["publication_plan.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", name="uq_validation_snapshot_plan"),
    )
    op.create_index("ix_validation_snapshot_plan_id", "validation_snapshot", ["plan_id"])

    op.create_table(
        "evidence_binding",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("check_id", sa.String(length=64), nullable=False),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("mandatory", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["snapshot_id"], ["validation_snapshot.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "snapshot_id",
            "check_id",
            name="uq_evidence_binding_snapshot_check",
        ),
    )
    op.create_index("ix_evidence_binding_snapshot_id", "evidence_binding", ["snapshot_id"])

    op.create_table(
        "access_grant",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("object_kind", sa.String(length=32), nullable=False),
        sa.Column("stable_id", sa.String(length=64), nullable=False),
        sa.Column("major", sa.Integer(), nullable=False),
        sa.Column("owner_account_id", sa.String(length=64), nullable=False),
        sa.Column("grantee_account_id", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("state in ('active', 'revoked')", name="ck_access_grant_state"),
        sa.CheckConstraint(
            "object_kind in ('component', 'setup')",
            name="ck_access_grant_object_kind",
        ),
        sa.ForeignKeyConstraint(["owner_account_id"], ["account.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["grantee_account_id"], ["account.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "object_kind",
            "stable_id",
            "major",
            "grantee_account_id",
            name="uq_access_grant_target_grantee",
        ),
    )
    op.create_index("ix_access_grant_stable_id", "access_grant", ["stable_id"])
    op.create_index("ix_access_grant_owner_account_id", "access_grant", ["owner_account_id"])
    op.create_index("ix_access_grant_grantee_account_id", "access_grant", ["grantee_account_id"])

    op.create_table(
        "grant_invitation",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("owner_account_id", sa.String(length=64), nullable=False),
        sa.Column("object_kind", sa.String(length=32), nullable=False),
        sa.Column("stable_id", sa.String(length=64), nullable=False),
        sa.Column("major", sa.Integer(), nullable=False),
        sa.Column("recipient_email_normalized", sa.String(length=320), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_grant_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state in ('pending', 'accepted', 'expired', 'revoked')",
            name="ck_grant_invitation_state",
        ),
        sa.CheckConstraint(
            "object_kind in ('component', 'setup')",
            name="ck_grant_invitation_object_kind",
        ),
        sa.ForeignKeyConstraint(["owner_account_id"], ["account.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_account_id",
            "idempotency_key",
            name="uq_grant_invitation_owner_idempotency",
        ),
    )
    op.create_index(
        "ix_grant_invitation_owner_account_id", "grant_invitation", ["owner_account_id"]
    )
    op.create_index("ix_grant_invitation_stable_id", "grant_invitation", ["stable_id"])
    op.create_index(
        "ix_grant_invitation_recipient_email_normalized",
        "grant_invitation",
        ["recipient_email_normalized"],
    )

    op.create_table(
        "report_case",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("reporter_account_id", sa.String(length=64), nullable=False),
        sa.Column("object_kind", sa.String(length=32), nullable=False),
        sa.Column("stable_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("content_digest", sa.String(length=71), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("vulnerability", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("group_key", sa.String(length=200), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state in ("
            "'submitted', 'triaged', 'awaiting_author', "
            "'security_escalated', 'resolved', 'dismissed')",
            name="ck_report_case_state",
        ),
        sa.CheckConstraint(
            "object_kind in ('component', 'setup')",
            name="ck_report_case_object_kind",
        ),
        sa.ForeignKeyConstraint(["reporter_account_id"], ["account.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "reporter_account_id",
            "idempotency_key",
            name="uq_report_case_reporter_idempotency",
        ),
    )
    op.create_index("ix_report_case_reporter_account_id", "report_case", ["reporter_account_id"])
    op.create_index("ix_report_case_stable_id", "report_case", ["stable_id"])
    op.create_index("ix_report_case_group_key", "report_case", ["group_key"])

    op.create_table(
        "account_author_verification",
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("issued_by_account_id", sa.String(length=64), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("account_id"),
    )


def downgrade() -> None:
    op.drop_table("account_author_verification")
    op.drop_index("ix_report_case_group_key", table_name="report_case")
    op.drop_index("ix_report_case_stable_id", table_name="report_case")
    op.drop_index("ix_report_case_reporter_account_id", table_name="report_case")
    op.drop_table("report_case")
    op.drop_index("ix_grant_invitation_recipient_email_normalized", table_name="grant_invitation")
    op.drop_index("ix_grant_invitation_stable_id", table_name="grant_invitation")
    op.drop_index("ix_grant_invitation_owner_account_id", table_name="grant_invitation")
    op.drop_table("grant_invitation")
    op.drop_index("ix_access_grant_grantee_account_id", table_name="access_grant")
    op.drop_index("ix_access_grant_owner_account_id", table_name="access_grant")
    op.drop_index("ix_access_grant_stable_id", table_name="access_grant")
    op.drop_table("access_grant")
    op.drop_index("ix_evidence_binding_snapshot_id", table_name="evidence_binding")
    op.drop_table("evidence_binding")
    op.drop_index("ix_validation_snapshot_plan_id", table_name="validation_snapshot")
    op.drop_table("validation_snapshot")
    op.drop_index("ix_publication_plan_stable_id", table_name="publication_plan")
    op.drop_index("ix_publication_plan_actor_account_id", table_name="publication_plan")
    op.drop_table("publication_plan")
