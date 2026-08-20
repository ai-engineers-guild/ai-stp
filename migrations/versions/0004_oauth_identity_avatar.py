"""oauth identity avatar and display name

Revision ID: 0004_oauth_identity_avatar
Revises: 0003_catalog_publication_state
Create Date: 2026-08-06

Additive columns for provider profile presentation on the account surface:
avatar_url (HTTPS URL from Google picture / GitHub avatar_url) and display_name
(provider label). No binary blobs — URLs only (SPEC-013: still no email on wire).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_oauth_identity_avatar"
down_revision: str | None = "0003_catalog_publication_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "oauth_identity",
        sa.Column("avatar_url", sa.String(length=2048), nullable=True),
    )
    op.add_column(
        "oauth_identity",
        sa.Column("display_name", sa.String(length=120), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("oauth_identity", "display_name")
    op.drop_column("oauth_identity", "avatar_url")
