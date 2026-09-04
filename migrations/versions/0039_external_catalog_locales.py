"""localized service and country presentation

Revision ID: 0039_external_catalog_locales
Revises: 0038_content_revision_media
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0039_external_catalog_locales"
down_revision: str | None = "0038_content_revision_media"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "external_product",
        "description",
        existing_type=sa.String(320),
        type_=sa.String(2000),
        existing_nullable=True,
    )
    op.create_table(
        "external_product_locale",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("external_product_id", sa.Integer(), nullable=False),
        sa.Column("locale", sa.String(8), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.String(2000), nullable=False),
        sa.Column("source_url", sa.String(512), nullable=False),
        sa.CheckConstraint("locale in ('ru', 'en')", name="ck_external_product_locale_locale"),
        sa.ForeignKeyConstraint(
            ["external_product_id"], ["external_product.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "external_product_id", "locale", name="uq_external_product_locale_identity"
        ),
    )
    op.create_index(
        "ix_external_product_locale_external_product_id",
        "external_product_locale",
        ["external_product_id"],
    )
    op.create_table(
        "country_locale",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("locale", sa.String(8), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.CheckConstraint("country_code ~ '^[A-Z]{2}$'", name="ck_country_locale_code"),
        sa.CheckConstraint("locale in ('ru', 'en')", name="ck_country_locale_locale"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("country_code", "locale", name="uq_country_locale_identity"),
    )
    op.create_index("ix_country_locale_country_code", "country_locale", ["country_code"])


def downgrade() -> None:
    op.drop_index("ix_country_locale_country_code", table_name="country_locale")
    op.drop_table("country_locale")
    op.drop_index(
        "ix_external_product_locale_external_product_id",
        table_name="external_product_locale",
    )
    op.drop_table("external_product_locale")
    op.alter_column(
        "external_product",
        "description",
        existing_type=sa.String(2000),
        type_=sa.String(320),
        existing_nullable=True,
    )
