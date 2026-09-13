"""Preserve employee display names inside their organization."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0072_tenant_member_display_names"
down_revision: str | None = "0071_corporate_catalog_assignments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organization_membership", sa.Column("display_name", sa.String(80), nullable=True)
    )
    op.execute(
        "UPDATE organization_membership AS membership SET display_name = account.display_name "
        "FROM account WHERE account.id = membership.account_id"
    )


def downgrade() -> None:
    op.drop_column("organization_membership", "display_name")
