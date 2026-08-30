"""additive SEO snapshots, revisions, articles and service presentation

Revision ID: 0031_seo_projections
Revises: 0030_shared_object_key
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031_seo_projections"
down_revision: str | None = "0030_shared_object_key"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "external_product", sa.Column("description", sa.String(length=320), nullable=True)
    )
    op.add_column("external_product", sa.Column("source_url", sa.String(length=512), nullable=True))
    op.add_column(
        "external_product",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column(
        "external_product",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_table(
        "seo_fact_snapshot",
        sa.Column("id", sa.String(length=71), nullable=False),
        sa.Column("subject_kind", sa.String(length=16), nullable=False),
        sa.Column("subject_id", sa.String(length=253), nullable=False),
        sa.Column("source_revision", sa.String(length=128), nullable=False),
        sa.Column("locale", sa.String(length=8), nullable=False),
        sa.Column("source_digest", sa.String(length=71), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("facts", sa.JSON(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "subject_kind in ('component', 'setup', 'article', 'service', 'country')",
            name="ck_seo_fact_snapshot_kind",
        ),
        sa.CheckConstraint("locale in ('ru', 'en')", name="ck_seo_fact_snapshot_locale"),
        sa.CheckConstraint("schema_version = 1", name="ck_seo_fact_snapshot_schema"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "subject_kind",
            "subject_id",
            "locale",
            "source_digest",
            name="uq_seo_fact_snapshot_identity",
        ),
    )
    op.create_index("ix_seo_fact_snapshot_subject_id", "seo_fact_snapshot", ["subject_id"])
    op.create_table(
        "seo_revision",
        sa.Column("id", sa.String(length=73), nullable=False),
        sa.Column("snapshot_id", sa.String(length=71), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("profile", sa.JSON(), nullable=False),
        sa.Column("profile_digest", sa.String(length=71), nullable=False),
        sa.Column("template_version", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("generator_kind", sa.String(length=16), nullable=False),
        sa.Column("model_alias", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state in ("
            "'building', 'base_ready', 'enriching', 'validating', "
            "'active', 'rejected', 'failed', 'stale')",
            name="ck_seo_revision_state",
        ),
        sa.CheckConstraint(
            "generator_kind in ('template', 'model')",
            name="ck_seo_revision_generator",
        ),
        sa.ForeignKeyConstraint(["snapshot_id"], ["seo_fact_snapshot.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "snapshot_id",
            "generator_kind",
            "template_version",
            "prompt_version",
            "model_alias",
            name="uq_seo_revision_identity",
        ),
    )
    op.create_index("ix_seo_revision_snapshot_id", "seo_revision", ["snapshot_id"])
    op.create_table(
        "seo_generation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("value", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("INSERT INTO seo_generation (id, value) VALUES (1, 0)")
    op.create_table(
        "seo_active_revision",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("subject_kind", sa.String(length=16), nullable=False),
        sa.Column("subject_id", sa.String(length=253), nullable=False),
        sa.Column("locale", sa.String(length=8), nullable=False),
        sa.Column("revision_id", sa.String(length=73), nullable=False),
        sa.Column("snapshot_id", sa.String(length=71), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("index_eligible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "subject_kind in ('component', 'setup', 'article', 'service', 'country')",
            name="ck_seo_active_revision_kind",
        ),
        sa.CheckConstraint("locale in ('ru', 'en')", name="ck_seo_active_revision_locale"),
        sa.ForeignKeyConstraint(["revision_id"], ["seo_revision.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["seo_fact_snapshot.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "subject_kind",
            "subject_id",
            "locale",
            name="uq_seo_active_revision_subject_locale",
        ),
    )
    op.create_index("ix_seo_active_revision_subject_id", "seo_active_revision", ["subject_id"])
    op.create_table(
        "article",
        sa.Column("id", sa.String(length=160), nullable=False),
        sa.Column("article_type", sa.String(length=32), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("source_kind", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "article_type in ('article', 'blog_post', 'changelog', 'release_notes')",
            name="ck_article_type",
        ),
        sa.CheckConstraint(
            "source_kind in ('repository', 'staff')",
            name="ck_article_source_kind",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("article_type", "slug", name="uq_article_type_slug"),
    )
    op.create_table(
        "article_revision",
        sa.Column("id", sa.String(length=73), nullable=False),
        sa.Column("article_id", sa.String(length=160), nullable=False),
        sa.Column("locale", sa.String(length=8), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=320), nullable=False),
        sa.Column("published_at", sa.String(length=10), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("content_digest", sa.String(length=71), nullable=False),
        sa.Column("source_kind", sa.String(length=16), nullable=False),
        sa.Column("source_ref", sa.String(length=40), nullable=True),
        sa.Column("source_path", sa.String(length=512), nullable=True),
        sa.Column("actor_account_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("locale in ('ru', 'en')", name="ck_article_revision_locale"),
        sa.CheckConstraint(
            "source_kind in ('repository', 'staff')",
            name="ck_article_revision_source_kind",
        ),
        sa.ForeignKeyConstraint(["article_id"], ["article.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_account_id"], ["account.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "article_id",
            "locale",
            "content_digest",
            name="uq_article_revision_identity",
        ),
    )
    op.create_index("ix_article_revision_article_id", "article_revision", ["article_id"])
    op.create_table(
        "article_active",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("article_id", sa.String(length=160), nullable=False),
        sa.Column("locale", sa.String(length=8), nullable=False),
        sa.Column("revision_id", sa.String(length=73), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("locale in ('ru', 'en')", name="ck_article_active_locale"),
        sa.ForeignKeyConstraint(["article_id"], ["article.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["revision_id"], ["article_revision.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("article_id", "locale", name="uq_article_active_identity"),
    )
    op.create_index("ix_article_active_article_id", "article_active", ["article_id"])
    op.create_table(
        "article_repository_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("snapshot_digest", sa.String(length=71), nullable=True),
        sa.Column("commit", sa.String(length=40), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_article_repository_state_singleton"),
        sa.CheckConstraint("generation >= 0", name="ck_article_repository_state_generation"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("INSERT INTO article_repository_state (id, generation) VALUES (1, 0)")


def downgrade() -> None:
    op.drop_table("article_repository_state")
    op.drop_index("ix_article_active_article_id", table_name="article_active")
    op.drop_table("article_active")
    op.drop_index("ix_article_revision_article_id", table_name="article_revision")
    op.drop_table("article_revision")
    op.drop_table("article")
    op.drop_index("ix_seo_active_revision_subject_id", table_name="seo_active_revision")
    op.drop_table("seo_active_revision")
    op.drop_table("seo_generation")
    op.drop_index("ix_seo_revision_snapshot_id", table_name="seo_revision")
    op.drop_table("seo_revision")
    op.drop_index("ix_seo_fact_snapshot_subject_id", table_name="seo_fact_snapshot")
    op.drop_table("seo_fact_snapshot")
    op.drop_column("external_product", "updated_at")
    op.drop_column("external_product", "created_at")
    op.drop_column("external_product", "source_url")
    op.drop_column("external_product", "description")
