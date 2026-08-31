"""legal onboarding and immutable policy acceptances

Revision ID: 0032_legal_onboarding
Revises: 0031_seo_projections
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032_legal_onboarding"
down_revision: str | None = "0031_seo_projections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "account",
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
    )
    op.create_check_constraint(
        "ck_account_status",
        "account",
        "status in ('onboarding_pending', 'active', 'deletion_pending')",
    )
    op.alter_column("account", "show_profile_publicly", server_default=sa.false())
    op.alter_column("account", "allow_publisher_listing", server_default=sa.false())
    op.add_column(
        "document_revision",
        sa.Column("policy_version", sa.String(length=32), server_default="1.0", nullable=False),
    )
    op.add_column(
        "document_revision", sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.drop_constraint("ck_public_document_kind", "public_document", type_="check")
    op.create_check_constraint(
        "ck_public_document_kind",
        "public_document",
        "kind in ('technical', 'privacy', 'cookies', 'service_rules', "
        "'author_content_and_license', 'personal_data_consent')",
    )
    op.create_table(
        "account_policy_acceptance",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("document_revision_id", sa.String(length=64), nullable=False),
        sa.Column("acceptance_type", sa.String(length=32), nullable=False),
        sa.Column(
            "accepted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("locale", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=32), server_default="web_onboarding", nullable=False),
        sa.CheckConstraint(
            "acceptance_type in ('service_rules', 'personal_data_consent')",
            name="ck_account_policy_acceptance_type",
        ),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["document_revision_id"], ["document_revision.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id",
            "document_revision_id",
            "acceptance_type",
            name="uq_account_policy_acceptance_exact",
        ),
    )
    op.create_index(
        "ix_account_policy_acceptance_account_id", "account_policy_acceptance", ["account_id"]
    )
    op.create_index(
        "ix_account_policy_acceptance_document_revision_id",
        "account_policy_acceptance",
        ["document_revision_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_account_policy_acceptance_document_revision_id", table_name="account_policy_acceptance"
    )
    op.drop_index("ix_account_policy_acceptance_account_id", table_name="account_policy_acceptance")
    op.drop_table("account_policy_acceptance")
    op.drop_constraint("ck_public_document_kind", "public_document", type_="check")
    op.create_check_constraint(
        "ck_public_document_kind",
        "public_document",
        "kind in ('technical', 'privacy', 'cookies', 'service_rules', "
        "'author_content_and_license')",
    )
    op.drop_column("document_revision", "effective_at")
    op.drop_column("document_revision", "policy_version")
    op.alter_column("account", "allow_publisher_listing", server_default=sa.true())
    op.alter_column("account", "show_profile_publicly", server_default=sa.true())
    op.drop_constraint("ck_account_status", "account", type_="check")
    op.drop_column("account", "status")
