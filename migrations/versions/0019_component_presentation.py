"""add mutable component presentation bio

Revision ID: 0019_component_presentation
Revises: 0018_catalog_digest
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0019_component_presentation"
down_revision: str | None = "0018_catalog_digest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("catalog_metadata", sa.Column("presentation_bio", sa.String(2000), nullable=True))


def downgrade() -> None:
    op.drop_column("catalog_metadata", "presentation_bio")
