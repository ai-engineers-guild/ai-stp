"""Bring migrated DDL back to what the ORM models declare.

Model declarations drifted from the migration chain in four ways:
lookup indexes declared with ``index=True`` were never created, single-column
uniqueness exists twice (a named unique constraint plus a redundant plain
index, or an auto-named constraint beside a conventional one), and
server-defaulted timestamp columns were created nullable while every model
declares them ``Mapped[datetime]``.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0109_schema_model_parity"
down_revision: str | None = "0108_project_link_account_local_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEXES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("ix_ownership_claim_from_account_id", "ownership_claim", ("from_account_id",)),
    ("ix_ownership_claim_to_account_id", "ownership_claim", ("to_account_id",)),
    ("ix_project_link_actor_account_id", "project_link", ("actor_account_id",)),
    ("ix_project_link_device_id", "project_link", ("device_id",)),
    ("ix_project_link_plan_device_id", "project_link_plan", ("device_id",)),
    ("ix_project_sync_plan_device_id", "project_sync_plan", ("device_id",)),
    ("ix_project_unlink_plan_device_id", "project_unlink_plan", ("device_id",)),
    ("ix_sync_revision_entity_id", "sync_revision", ("entity_id",)),
)

NOT_NULL_COLUMNS: tuple[tuple[str, str], ...] = (
    ("corporate_assignment_distribution", "created_at"),
    ("corporate_assignment_distribution", "updated_at"),
    ("corporate_bootstrap_receipt", "created_at"),
    ("corporate_catalog_assignment", "created_at"),
    ("corporate_catalog_assignment", "updated_at"),
    ("corporate_catalog_lifecycle", "created_at"),
    ("corporate_catalog_lifecycle", "updated_at"),
    ("corporate_catalog_maintainer", "created_at"),
    ("corporate_catalog_maintainer", "updated_at"),
    ("corporate_catalog_verification", "created_at"),
    ("corporate_catalog_verification", "updated_at"),
    ("corporate_dashboard_view", "created_at"),
    ("corporate_dashboard_view", "updated_at"),
    ("corporate_job_title", "created_at"),
    ("corporate_job_title", "updated_at"),
    ("corporate_mutation_receipt", "created_at"),
    ("corporate_project", "created_at"),
    ("corporate_project", "updated_at"),
    ("corporate_project_member", "created_at"),
    ("corporate_provisioned_identity", "created_at"),
    ("corporate_role_binding", "created_at"),
    ("corporate_role_binding", "updated_at"),
    ("corporate_service_principal", "created_at"),
    ("corporate_service_principal", "updated_at"),
    ("corporate_team", "created_at"),
    ("corporate_team", "updated_at"),
    ("corporate_team_member", "created_at"),
    ("organization", "created_at"),
    ("organization", "updated_at"),
    ("organization_membership", "created_at"),
    ("organization_membership", "updated_at"),
    ("organization_resource", "created_at"),
    ("project_identity", "created_at"),
    ("project_identity", "updated_at"),
    ("project_link", "created_at"),
    ("project_link", "updated_at"),
    ("project_link_plan", "created_at"),
    ("project_link_proposal", "created_at"),
    ("project_revision", "created_at"),
    ("project_revision_head", "updated_at"),
    ("project_revision_receipt", "created_at"),
    ("project_sync_plan", "created_at"),
    ("project_unlink_plan", "created_at"),
    ("telemetry_audit", "created_at"),
    ("telemetry_event", "received_at"),
    ("telemetry_policy", "created_at"),
    ("telemetry_policy", "updated_at"),
    ("telemetry_revocation", "created_at"),
    ("telemetry_revocation", "updated_at"),
)


def upgrade() -> None:
    for name, table, columns in INDEXES:
        op.create_index(name, table, list(columns))

    # Single-column uniqueness converges on one named constraint per column;
    # the secondary indexes below duplicate the constraint's own btree.
    op.drop_index("ix_sync_outbox_account_sequence", table_name="sync_outbox")
    op.drop_index("ix_public_document_slug", table_name="public_document")
    op.execute(
        "ALTER TABLE public_document RENAME CONSTRAINT public_document_slug_key "
        "TO uq_public_document_slug"
    )
    op.drop_index(
        "ix_oauth_identity_alias_oauth_identity_id",
        table_name="oauth_identity_alias",
    )
    op.drop_index(
        "ix_external_product_canonical_domain",
        table_name="external_product",
    )
    op.execute(
        "ALTER TABLE external_product "
        "RENAME CONSTRAINT external_product_canonical_domain_key "
        "TO uq_external_product_canonical_domain"
    )

    for table, column in NOT_NULL_COLUMNS:
        op.execute(f"UPDATE {table} SET {column} = now() WHERE {column} IS NULL")
        op.alter_column(table, column, nullable=False)


def downgrade() -> None:
    for table, column in reversed(NOT_NULL_COLUMNS):
        op.alter_column(table, column, nullable=True)

    op.execute(
        "ALTER TABLE external_product "
        "RENAME CONSTRAINT uq_external_product_canonical_domain "
        "TO external_product_canonical_domain_key"
    )
    op.create_index(
        "ix_external_product_canonical_domain",
        "external_product",
        ["canonical_domain"],
        unique=True,
    )
    op.create_index(
        "ix_oauth_identity_alias_oauth_identity_id",
        "oauth_identity_alias",
        ["oauth_identity_id"],
    )
    op.execute(
        "ALTER TABLE public_document RENAME CONSTRAINT uq_public_document_slug "
        "TO public_document_slug_key"
    )
    op.create_index("ix_public_document_slug", "public_document", ["slug"])
    op.create_index(
        "ix_sync_outbox_account_sequence",
        "sync_outbox",
        ["account_id", "sequence"],
    )

    for name, table, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table)
