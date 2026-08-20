"""add catalog publication state for anonymous public read

Revision ID: 0003_catalog_publication_state
Revises: 0002_sprint1_core
Create Date: 2026-08-06

Additive-first extension of catalog_metadata for SPEC-021 / ADR-0042:
published_at, trust lane, verification axes, and a stored passport document
used for public projection. Multi-version rows require dropping the
(object_kind, stable_id) unique constraint so one stable_id may carry several
published versions.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_catalog_publication_state"
down_revision: str | None = "0002_sprint1_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_catalog_metadata_kind_stable_id",
        "catalog_metadata",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_catalog_metadata_kind_stable_id_version",
        "catalog_metadata",
        ["object_kind", "stable_id", "version"],
    )
    op.add_column(
        "catalog_metadata",
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "catalog_metadata",
        sa.Column("trust_lane", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "catalog_metadata",
        sa.Column(
            "author_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "catalog_metadata",
        sa.Column(
            "component_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "catalog_metadata",
        sa.Column("passport_digest", sa.String(length=71), nullable=True),
    )
    op.add_column(
        "catalog_metadata",
        sa.Column("passport_document", sa.JSON(), nullable=True),
    )
    op.create_check_constraint(
        "ck_catalog_metadata_trust_lane",
        "catalog_metadata",
        "trust_lane is null or trust_lane in ('authoritative', 'experimental')",
    )
    op.create_index(
        "ix_catalog_metadata_public_list",
        "catalog_metadata",
        ["object_kind", "visibility", "lifecycle_state", "published_at", "stable_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_metadata_public_list", table_name="catalog_metadata")
    op.drop_constraint("ck_catalog_metadata_trust_lane", "catalog_metadata", type_="check")
    op.drop_column("catalog_metadata", "passport_document")
    op.drop_column("catalog_metadata", "passport_digest")
    op.drop_column("catalog_metadata", "component_verified")
    op.drop_column("catalog_metadata", "author_verified")
    op.drop_column("catalog_metadata", "trust_lane")
    op.drop_column("catalog_metadata", "published_at")
    op.drop_constraint(
        "uq_catalog_metadata_kind_stable_id_version",
        "catalog_metadata",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_catalog_metadata_kind_stable_id",
        "catalog_metadata",
        ["object_kind", "stable_id"],
    )
