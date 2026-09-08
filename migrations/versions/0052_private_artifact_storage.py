"""Record private publication visibility and object-store ownership metadata.

Revision ID: 0052_private_artifact_storage
Revises: 0051_target_assessment_check_details
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0052_private_artifact_storage"
down_revision: str | None = "0051_target_assessment_check_details"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("object_location", sa.Column("bucket", sa.String(length=255), nullable=True))
    op.add_column(
        "object_location",
        sa.Column("owner_account_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_object_location_owner_account_id",
        "object_location",
        ["owner_account_id"],
    )
    op.create_foreign_key(
        "fk_object_location_owner_account_id_account",
        "object_location",
        "account",
        ["owner_account_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "component_media",
        sa.Column("content_digest", sa.String(length=80), nullable=True),
    )

    op.add_column(
        "publication_plan",
        sa.Column("visibility", sa.String(length=16), nullable=True, server_default="private"),
    )
    op.execute(
        sa.text(
            "UPDATE publication_plan "
            "SET visibility = COALESCE(passport ->> 'visibility', 'private')"
        )
    )
    op.alter_column(
        "publication_plan",
        "visibility",
        existing_type=sa.String(length=16),
        nullable=False,
        server_default=None,
    )
    op.create_check_constraint(
        "ck_publication_plan_visibility",
        "publication_plan",
        "visibility in ('public', 'private')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_publication_plan_visibility", "publication_plan", type_="check")
    op.drop_column("publication_plan", "visibility")
    op.drop_constraint(
        "fk_object_location_owner_account_id_account",
        "object_location",
        type_="foreignkey",
    )
    op.drop_index("ix_object_location_owner_account_id", table_name="object_location")
    op.drop_column("component_media", "content_digest")
    op.drop_column("object_location", "owner_account_id")
    op.drop_column("object_location", "bucket")
