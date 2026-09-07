"""Remove public portability projections and accept the canonical cli kind.

Revision ID: 0050_exact_public_targets_and_cli_taxonomy
Revises: 0049_catalog_projections_assurance_families
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0050_exact_public_targets_and_cli_taxonomy"
down_revision: str | None = "0049_catalog_projections_assurance_families"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COMPONENT_TYPES = (
    "instruction",
    "skill",
    "mcp",
    "hook",
    "command",
    "agent",
    "plugin",
    "setting",
    "cli",
)


def upgrade() -> None:
    op.add_column("target_assessment", sa.Column("payload_digest", sa.String(71), nullable=True))
    op.drop_constraint("ck_target_assessment_stored_state", "target_assessment", type_="check")
    op.create_check_constraint(
        "ck_target_assessment_stored_state",
        "target_assessment",
        sa.text("stored_state in ('not_verified', 'verified', 'failed', 'stale')"),
    )
    op.drop_index(
        "ix_catalog_search_projection_claimed_harnesses",
        table_name="catalog_search_projection",
    )
    op.drop_column("catalog_search_projection", "claimed_harness_ids")
    op.drop_constraint(
        "ck_official_upstream_source_component_type",
        "official_upstream_source",
        type_="check",
    )
    values = ", ".join(f"'{item}'" for item in _COMPONENT_TYPES)
    op.create_check_constraint(
        "ck_official_upstream_source_component_type",
        "official_upstream_source",
        sa.text(f"component_type in ({values})"),
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_official_upstream_source_component_type",
        "official_upstream_source",
        type_="check",
    )
    op.create_check_constraint(
        "ck_official_upstream_source_component_type",
        "official_upstream_source",
        sa.text(
            "component_type in ('instruction', 'skill', 'mcp', 'hook', 'command', "
            "'agent', 'plugin', 'setting')"
        ),
    )
    op.drop_constraint("ck_target_assessment_stored_state", "target_assessment", type_="check")
    op.create_check_constraint(
        "ck_target_assessment_stored_state",
        "target_assessment",
        sa.text("stored_state in ('not_verified', 'verified', 'failed')"),
    )
    op.drop_column("target_assessment", "payload_digest")
    op.add_column(
        "catalog_search_projection",
        sa.Column(
            "claimed_harness_ids", sa.ARRAY(sa.String(32)), server_default="{}", nullable=False
        ),
    )
    op.create_index(
        "ix_catalog_search_projection_claimed_harnesses",
        "catalog_search_projection",
        ["claimed_harness_ids"],
        postgresql_using="gin",
    )
