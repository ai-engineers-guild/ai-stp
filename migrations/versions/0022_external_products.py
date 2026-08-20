"""external products and catalog relations

Revision ID: 0022_external_products
Revises: 0021_repository_metrics
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_external_products"
down_revision: str | None = "0021_repository_metrics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "external_product",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("canonical_domain", sa.String(253), nullable=False),
        sa.Column("primary_url", sa.String(512), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_domain"),
    )
    op.create_table(
        "external_product_country",
        sa.Column("external_product_id", sa.Integer(), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.ForeignKeyConstraint(
            ["external_product_id"], ["external_product.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("external_product_id", "country_code"),
    )
    op.create_index(
        "ix_external_product_country_country_code",
        "external_product_country",
        ["country_code"],
    )
    op.create_index(
        "ix_external_product_canonical_domain",
        "external_product",
        ["canonical_domain"],
        unique=True,
    )
    op.create_table(
        "catalog_external_product",
        sa.Column("catalog_metadata_id", sa.Integer(), nullable=False),
        sa.Column("external_product_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["catalog_metadata_id"], ["catalog_metadata.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["external_product_id"], ["external_product.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("catalog_metadata_id", "external_product_id"),
    )


def downgrade() -> None:
    op.drop_table("catalog_external_product")
    op.drop_index("ix_external_product_canonical_domain", table_name="external_product")
    op.drop_index("ix_external_product_country_country_code", table_name="external_product_country")
    op.drop_table("external_product_country")
    op.drop_table("external_product")
