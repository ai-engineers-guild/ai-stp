"""public profile revisions, avatars, public documents (SPEC-028/031)

Revision ID: 0009_public_profile_documents
Revises: 0007_publication_grants_reports
Create Date: 2026-08-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_public_profile_documents"
down_revision: str | None = "0007_publication_grants_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "public_profile",
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("published_revision_id", sa.String(length=64), nullable=True),
        sa.Column("draft_revision_id", sa.String(length=64), nullable=True),
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
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("account_id"),
    )

    op.create_table(
        "profile_revision",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("lifecycle", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=True),
        sa.Column("bio", sa.String(length=500), nullable=True),
        sa.Column("links", sa.JSON(), nullable=False),
        sa.Column("avatar_asset_id", sa.String(length=64), nullable=True),
        sa.Column("content_digest", sa.String(length=80), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "lifecycle in ('draft', 'published', 'superseded')",
            name="ck_profile_revision_lifecycle",
        ),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_profile_revision_account_id", "profile_revision", ["account_id"])

    op.create_table(
        "avatar_asset",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("public_url", sa.String(length=2048), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
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
            "state in ('processing', 'ready', 'rejected', 'deleted')",
            name="ck_avatar_asset_state",
        ),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_avatar_asset_account_id", "avatar_asset", ["account_id"])

    op.create_table(
        "public_document",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind in ('technical', 'privacy', 'cookies', 'service_rules', "
            "'author_content_and_license')",
            name="ck_public_document_kind",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_public_document_slug", "public_document", ["slug"])

    op.create_table(
        "document_revision",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("locale", sa.String(length=16), nullable=False),
        sa.Column("lifecycle", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("markdown_source", sa.Text(), nullable=False),
        sa.Column("content_digest", sa.String(length=80), nullable=False),
        sa.Column("renderer_version", sa.String(length=32), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("source_path", sa.String(length=512), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supersedes_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "lifecycle in ('draft', 'published', 'superseded')",
            name="ck_document_revision_lifecycle",
        ),
        sa.ForeignKeyConstraint(["document_id"], ["public_document.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "locale",
            "content_digest",
            name="uq_document_revision_digest",
        ),
    )
    op.create_index("ix_document_revision_document_id", "document_revision", ["document_id"])


def downgrade() -> None:
    op.drop_table("document_revision")
    op.drop_table("public_document")
    op.drop_table("avatar_asset")
    op.drop_table("profile_revision")
    op.drop_table("public_profile")
