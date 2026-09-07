"""Accept standalone CLI sources and require explicitly derived support tiers.

Revision ID: 0048_canonical_catalog_consumers
Revises: 0047_repair_official_locale_collisions
"""

from __future__ import annotations

from alembic import op

revision: str = "0048_canonical_catalog_consumers"
down_revision: str | None = "0047_repair_official_locale_collisions"
branch_labels = None
depends_on = None

# These are the immutable DDL states of this transition. The ORM reads the
# current passport registry; a future kind still needs its own migration.
_PREVIOUS_KINDS = "'instruction', 'skill', 'mcp', 'hook', 'command', 'agent', 'plugin', 'setting'"
_CONSTRAINT = "ck_official_upstream_source_component_type"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "official_upstream_source", type_="check")
    op.create_check_constraint(
        _CONSTRAINT, "official_upstream_source", f"component_type in ({_PREVIOUS_KINDS}, 'cli')"
    )
    op.alter_column("catalog_search_projection", "support_tier", server_default=None)


def downgrade() -> None:
    # Existing CLI rows deliberately make this fail; never relabel a program
    # as a slash command or delete its history to permit an older constraint.
    op.drop_constraint(_CONSTRAINT, "official_upstream_source", type_="check")
    op.create_check_constraint(
        _CONSTRAINT, "official_upstream_source", f"component_type in ({_PREVIOUS_KINDS})"
    )
    op.alter_column("catalog_search_projection", "support_tier", server_default="primary")
