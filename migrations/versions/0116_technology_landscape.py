"""Technology landscape areas, category binding, and scan journal columns."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0116_technology_landscape"
down_revision: str | Sequence[str] | None = "0115_saml_sso_request"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "technology_area",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("normalized_name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(2000), server_default="", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("provenance", sa.String(256), nullable=False),
        sa.Column("state", sa.String(16), server_default="active", nullable=False),
        sa.Column(
            "organization_id",
            sa.String(64),
            sa.ForeignKey("organization.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("organization_id", "id"),
        sa.UniqueConstraint("organization_id", "normalized_name", name="uq_technology_area_name"),
        sa.CheckConstraint("revision >= 1", name="ck_technology_area_revision"),
        sa.CheckConstraint(
            "state IN ('draft','active','archived')", name="ck_technology_area_state"
        ),
    )
    op.add_column("technology_category", sa.Column("area_id", sa.String(64), nullable=True))
    op.create_foreign_key(
        "fk_technology_category_area",
        "technology_category",
        "technology_area",
        ["organization_id", "area_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )
    op.add_column("technology_scan", sa.Column("source", sa.String(16), nullable=True))
    op.add_column("technology_scan", sa.Column("repository", sa.String(512), nullable=True))
    op.add_column("technology_scan", sa.Column("branch", sa.String(128), nullable=True))
    op.add_column("technology_scan", sa.Column("commit", sa.String(128), nullable=True))
    op.add_column(
        "technology_scan",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_technology_scan_source",
        "technology_scan",
        "source IS NULL OR source IN ('gitlab','github','local')",
    )
    op.create_index(
        "ix_technology_scan_project",
        "technology_scan",
        ["organization_id", "project_id"],
    )


def downgrade() -> None:
    linked = op.get_bind().scalar(
        sa.text("SELECT 1 FROM technology_category WHERE area_id IS NOT NULL LIMIT 1")
    )
    if linked:
        raise RuntimeError("unbind technology categories from areas before downgrade")
    op.drop_index("ix_technology_scan_project", table_name="technology_scan")
    op.drop_constraint("ck_technology_scan_source", "technology_scan", type_="check")
    op.drop_column("technology_scan", "created_at")
    op.drop_column("technology_scan", "commit")
    op.drop_column("technology_scan", "branch")
    op.drop_column("technology_scan", "repository")
    op.drop_column("technology_scan", "source")
    op.drop_constraint("fk_technology_category_area", "technology_category", type_="foreignkey")
    op.drop_column("technology_category", "area_id")
    op.drop_table("technology_area")
