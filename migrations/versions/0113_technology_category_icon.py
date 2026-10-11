"""Technology category icon.

`technology_category.icon` records the category's presentation icon: a registry
icon name (`lucide:<slug>`), an uploaded media asset (`/v1/media/avatars/…`),
or an HTTPS reference. NULL keeps the deterministic presentation fallback.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0113_technology_category_icon"
down_revision: str | Sequence[str] | None = "0112_participation_people_visibility"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("technology_category", sa.Column("icon", sa.String(2048), nullable=True))


def downgrade() -> None:
    op.drop_column("technology_category", "icon")
