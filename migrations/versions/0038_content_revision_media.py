"""store article cover metadata for previews"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038_content_revision_media"
down_revision: str | None = "0037_request_case_topics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "article_revision", sa.Column("cover_image", sa.String(length=512), nullable=True)
    )
    op.add_column("article_revision", sa.Column("cover_alt", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("article_revision", "cover_alt")
    op.drop_column("article_revision", "cover_image")
