"""multiple official git and package sources on the shared resolver

Revision ID: 0035_official_upstream_multi
Revises: 0034_ownership_claims
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035_official_upstream_multi"
down_revision: str | None = "0034_ownership_claims"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_official_upstream_source_slot", "official_upstream_source", type_="unique"
    )
    op.drop_constraint(
        "ck_official_upstream_source_slot", "official_upstream_source", type_="check"
    )
    op.add_column(
        "official_upstream_source",
        sa.Column("kind", sa.String(length=16), server_default="git", nullable=False),
    )
    op.add_column(
        "official_upstream_source",
        sa.Column("ecosystem", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "official_upstream_source",
        sa.Column("package_name", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "official_upstream_source",
        sa.Column("package_version", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "official_upstream_source",
        sa.Column("package_filename", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "official_upstream_source",
        sa.Column("package_platform", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "official_upstream_source",
        sa.Column("last_canonical_coordinate", sa.String(length=1024), nullable=True),
    )
    op.alter_column(
        "official_upstream_source",
        "repository_url",
        existing_type=sa.String(length=512),
        nullable=True,
    )
    op.alter_column(
        "official_upstream_source",
        "tracked_ref",
        existing_type=sa.String(length=256),
        nullable=True,
    )
    op.alter_column(
        "official_upstream_source",
        "component_subpath",
        existing_type=sa.String(length=512),
        nullable=True,
    )
    op.alter_column(
        "official_upstream_source",
        "last_commit",
        existing_type=sa.String(length=40),
        type_=sa.String(length=256),
        existing_nullable=True,
    )
    op.alter_column(
        "official_upstream_sync",
        "commit",
        existing_type=sa.String(length=40),
        type_=sa.String(length=256),
        existing_nullable=True,
    )
    op.create_check_constraint(
        "ck_official_upstream_source_kind",
        "official_upstream_source",
        "kind in ('git', 'package')",
    )
    op.create_check_constraint(
        "ck_official_upstream_source_kind_fields",
        "official_upstream_source",
        "("
        "kind = 'git' AND repository_url IS NOT NULL AND tracked_ref IS NOT NULL "
        "AND component_subpath IS NOT NULL"
        ") OR ("
        "kind = 'package' AND ecosystem IS NOT NULL AND package_name IS NOT NULL "
        "AND package_version IS NOT NULL"
        ")",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_official_upstream_source_kind_fields",
        "official_upstream_source",
        type_="check",
    )
    op.drop_constraint(
        "ck_official_upstream_source_kind", "official_upstream_source", type_="check"
    )
    op.alter_column(
        "official_upstream_sync",
        "commit",
        existing_type=sa.String(length=256),
        type_=sa.String(length=40),
        existing_nullable=True,
    )
    op.alter_column(
        "official_upstream_source",
        "last_commit",
        existing_type=sa.String(length=256),
        type_=sa.String(length=40),
        existing_nullable=True,
    )
    op.alter_column(
        "official_upstream_source",
        "component_subpath",
        existing_type=sa.String(length=512),
        nullable=False,
    )
    op.alter_column(
        "official_upstream_source",
        "tracked_ref",
        existing_type=sa.String(length=256),
        nullable=False,
    )
    op.alter_column(
        "official_upstream_source",
        "repository_url",
        existing_type=sa.String(length=512),
        nullable=False,
    )
    op.drop_column("official_upstream_source", "last_canonical_coordinate")
    op.drop_column("official_upstream_source", "package_platform")
    op.drop_column("official_upstream_source", "package_filename")
    op.drop_column("official_upstream_source", "package_version")
    op.drop_column("official_upstream_source", "package_name")
    op.drop_column("official_upstream_source", "ecosystem")
    op.drop_column("official_upstream_source", "kind")
    op.create_check_constraint(
        "ck_official_upstream_source_slot",
        "official_upstream_source",
        "slot = 'official'",
    )
    op.create_unique_constraint(
        "uq_official_upstream_source_slot", "official_upstream_source", ["slot"]
    )
