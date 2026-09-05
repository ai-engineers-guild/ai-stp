"""PostgreSQL catalog search projection.

Revision ID: 0041_catalog_search_projection
Revises: 0040_public_identities_official_sync
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0041_catalog_search_projection"
down_revision: str | None = "0040_public_identities_official_sync"
branch_labels = None
depends_on = None


_VECTOR = "to_tsvector('simple', coalesce(search_text, ''))"


def upgrade() -> None:
    op.create_table(
        "catalog_search_projection",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "catalog_metadata_id",
            sa.Integer(),
            sa.ForeignKey("catalog_metadata.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("object_kind", sa.String(32), nullable=False),
        sa.Column("stable_id", sa.String(64), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("version_major", sa.Integer(), nullable=False),
        sa.Column("version_minor", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("owner_account_id", sa.String(64), nullable=False),
        sa.Column("component_type", sa.String(32)),
        sa.Column("harness_ids", postgresql.ARRAY(sa.String(32)), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.String(32)), nullable=False),
        sa.Column("tag_aliases", postgresql.ARRAY(sa.String(64)), nullable=False),
        sa.Column("trust_lane", sa.String(32), nullable=False),
        sa.Column("component_verified", sa.Boolean(), nullable=False),
        sa.Column("lifecycle_state", sa.String(32), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("likes_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("support_tier", sa.String(32), server_default="primary", nullable=False),
        sa.Column("support_state", sa.String(32), server_default="missing", nullable=False),
        sa.Column("support_expires_at", sa.DateTime(timezone=True)),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("search_vector", postgresql.TSVECTOR(), sa.Computed(_VECTOR, persisted=True)),
        sa.UniqueConstraint(
            "object_kind", "stable_id", name="uq_catalog_search_projection_kind_stable_id"
        ),
        sa.UniqueConstraint("catalog_metadata_id", name="uq_catalog_search_projection_metadata_id"),
        sa.CheckConstraint(
            "object_kind in ('component', 'setup')",
            name="ck_catalog_search_projection_kind",
        ),
        sa.CheckConstraint(
            "lifecycle_state in ('active', 'deprecated', 'blocked')",
            name="ck_catalog_search_projection_lifecycle",
        ),
    )
    op.create_index(
        "ix_catalog_search_projection_fts",
        "catalog_search_projection",
        ["search_vector"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_catalog_search_projection_tags",
        "catalog_search_projection",
        ["tags"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_catalog_search_projection_harnesses",
        "catalog_search_projection",
        ["harness_ids"],
        postgresql_using="gin",
    )
    for suffix, columns in (
        ("updated", ["object_kind", "updated_at", "stable_id"]),
        ("likes", ["object_kind", "likes_count", "updated_at", "stable_id"]),
    ):
        op.create_index(
            f"ix_catalog_search_projection_{suffix}", "catalog_search_projection", columns
        )
        op.create_index(
            f"ix_catalog_search_projection_{suffix}_active",
            "catalog_search_projection",
            columns,
            postgresql_where=sa.text("lifecycle_state = 'active'"),
        )
    op.create_index(
        "ix_catalog_search_projection_catalog_metadata_id",
        "catalog_search_projection",
        ["catalog_metadata_id"],
    )

    # Backfill in SQL so the catalog is never empty between migration and the
    # first application write. Runtime refresh enriches aliases/support state.
    op.execute(
        """
        INSERT INTO catalog_search_projection (
            catalog_metadata_id, object_kind, stable_id, version,
            version_major, version_minor, name, description, owner_account_id,
            component_type, harness_ids, tags, tag_aliases, trust_lane,
            component_verified, lifecycle_state, published_at, updated_at,
            likes_count, support_tier, support_state, search_text
        )
        SELECT id, object_kind, stable_id, version,
               split_part(version, '.', 1)::integer,
               split_part(version, '.', 2)::integer,
               coalesce(name, passport_document->>'name', ''),
               left(coalesce(passport_document->>'description', ''), 8000),
               owner_account_id, passport_document->>'component_type',
               ARRAY(
                   SELECT DISTINCT value FROM (
                       SELECT passport_document->>'harness_id' AS value
                       UNION ALL
                       SELECT item->>'harness_id'
                       FROM jsonb_array_elements(
                           coalesce(passport_document::jsonb->'adaptations', '[]'::jsonb)
                       ) AS item
                   ) harnesses WHERE value IS NOT NULL AND value <> ''
               ),
               ARRAY(
                   SELECT jsonb_array_elements_text(
                       coalesce(passport_document::jsonb->'tags', '[]'::jsonb)
                   )
               ),
               ARRAY(
                   SELECT vocabulary.alias
                   FROM jsonb_array_elements_text(
                       coalesce(passport_document::jsonb->'tags', '[]'::jsonb)
                   ) AS tag(id)
                   JOIN (VALUES
                       ('python', 'Python'), ('python', 'py'), ('python', 'python3'),
                       ('tests', 'Tests'), ('tests', 'testing'),
                       ('code-review', 'Code review'), ('code-review', 'review'),
                       ('documentation', 'Documentation'), ('documentation', 'docs'),
                       ('devops', 'DevOps'), ('devops', 'ci'),
                       ('security', 'Security'), ('security', 'sec'),
                       ('refactor', 'Refactor'), ('refactor', 'cleanup'),
                       ('github', 'GitHub'),
                       ('planning', 'Planning'), ('planning', 'plan'),
                       ('release', 'Release'), ('release', 'publish')
                   ) AS vocabulary(tag_id, alias) ON vocabulary.tag_id = tag.id
               ), trust_lane, component_verified,
               lifecycle_state, published_at, coalesce(updated_at, published_at),
               coalesce(likes_count, 0), 'primary', 'missing',
               lower(
                   coalesce(name, passport_document->>'name', '') || ' ' ||
                   left(coalesce(passport_document->>'description', ''), 8000) || ' ' ||
                   stable_id || ' ' || owner_account_id || ' ' ||
                   coalesce(passport_document->>'tags', '')
               )
        FROM (
            SELECT DISTINCT ON (object_kind, stable_id) *
            FROM catalog_metadata
            WHERE visibility = 'public'
              AND lifecycle_state IN ('active', 'deprecated', 'blocked')
              AND published_at IS NOT NULL AND version IS NOT NULL
              AND passport_document IS NOT NULL AND passport_digest IS NOT NULL
              AND trust_lane IS NOT NULL
            ORDER BY object_kind, stable_id,
                     split_part(version, '.', 1)::integer DESC,
                     split_part(version, '.', 2)::integer DESC
        ) latest
        """
    )
    op.execute(
        """
        UPDATE catalog_search_projection
        SET search_text = search_text || ' ' || array_to_string(tag_aliases, ' ')
        WHERE cardinality(tag_aliases) > 0
        """
    )


def downgrade() -> None:
    op.drop_table("catalog_search_projection")
