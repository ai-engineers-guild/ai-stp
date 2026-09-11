"""Add the project DAG, provider observations and the ownership backfill index.

The index is intentionally append-only: it preserves the account attribution of
legacy rows while giving every cloud-owned row one explicit personal tenant.
New project rows carry ``organization_id`` directly; legacy tables are migrated
without rewriting their business keys or public identities.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0059_project_ledger_and_ownership_scope"
down_revision: str | None = "0058_b2b00_context_and_project_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


LEGACY_SCOPE_ROWS = (
    ("catalog_metadata", "id", "owner_account_id"),
    ("catalog_identity", "stable_id", "owner_account_id"),
    ("catalog_search_projection", "id", "owner_account_id"),
    ("component_media", "id", "owner_account_id"),
    ("object_location", "id", "owner_account_id"),
    ("sync_revision", "revision_id", "account_id"),
    ("sync_entity_head", "entity_id", "account_id"),
    ("sync_event_receipt", "id", "account_id"),
    ("sync_outbox", "event_id", "account_id"),
    ("publication_plan", "id", "actor_account_id"),
    ("visibility_plan", "id", "actor_account_id"),
    ("access_grant", "id", "owner_account_id"),
    ("grant_invitation", "id", "owner_account_id"),
    ("report_case", "id", "reporter_account_id"),
    ("account_author_verification", "account_id", "account_id"),
    ("profile_revision", "id", "account_id"),
    ("avatar_asset", "id", "account_id"),
    ("account_policy_acceptance", "id", "account_id"),
    ("official_upstream_source", "id", "owner_account_id"),
    ("setup_family", "family_id", "owner_account_id"),
    ("github_connector", "id", "account_id"),
    ("github_authorization_flow", "state_hash", "account_id"),
    ("github_source_binding", "id", "account_id"),
    ("github_action_plan", "id", "account_id"),
    ("distribution_visibility_plan", "id", "account_id"),
)


def _assert_legacy_scope_is_total(
    connection: sa.Connection,
    rows: Sequence[tuple[str, str, str]] = LEGACY_SCOPE_ROWS,
) -> None:
    """Fail closed for orphaned or ambiguously attributed cloud rows."""
    ambiguous = connection.execute(
        sa.text(
            "SELECT account.id FROM account "
            "LEFT JOIN organization ON organization.owner_account_id = account.id "
            "AND organization.kind = 'personal' "
            "GROUP BY account.id HAVING COUNT(organization.id) <> 1"
        )
    ).fetchone()
    if ambiguous is not None:
        raise RuntimeError("personal organization attribution is missing or ambiguous")

    for table_name, _key_column, account_column in rows:
        account_expression = _account_expression(table_name, account_column)
        orphaned = connection.execute(
            sa.text(
                "SELECT 1 FROM "
                + table_name
                + " AS source LEFT JOIN organization ON organization.owner_account_id = "
                + account_expression
                + " AND organization.kind = 'personal' WHERE "
                + account_expression
                + " IS NULL OR organization.id IS NULL LIMIT 1"
            )
        ).fetchone()
        if orphaned is not None:
            raise RuntimeError(f"unattributed cloud rows in {table_name}")


def _account_expression(table_name: str, account_column: str) -> str:
    """Resolve nullable object-location ownership from its catalog parent."""
    if table_name == "object_location":
        return (
            "COALESCE(source.owner_account_id, (SELECT metadata.owner_account_id "
            "FROM catalog_metadata AS metadata "
            "WHERE metadata.id = source.catalog_metadata_id))"
        )
    return "source." + account_column


def _ensure_visibility_plan_table(connection: sa.Connection) -> None:
    """Repair databases stamped at 0057 before the parallel 0056 branch existed."""
    if sa.inspect(connection).has_table("visibility_plan"):
        return

    op.create_table(
        "visibility_plan",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "actor_account_id",
            sa.String(64),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "actor_account_id", "idempotency_key", name="uq_visibility_plan_actor_key"
        ),
        sa.CheckConstraint(
            "state in ('planned', 'applied', 'expired', 'refused')", name="ck_visibility_plan_state"
        ),
    )
    op.create_index("ix_visibility_plan_actor_account_id", "visibility_plan", ["actor_account_id"])


def _backfill_organization_resources(
    connection: sa.Connection,
    rows: Sequence[tuple[str, str, str]] = LEGACY_SCOPE_ROWS,
) -> None:
    """Idempotently materialize the immutable organization scope of old rows."""
    _assert_legacy_scope_is_total(connection, rows)
    for table_name, key_column, account_column in rows:
        # These names are constants in this migration, not user input.
        key_expression = "CAST(source." + key_column + " AS VARCHAR(512))"
        account_expression = _account_expression(table_name, account_column)
        if table_name == "sync_revision":
            key_expression = (
                "CAST(source.account_id AS VARCHAR(64)) || ':' || "
                "CAST(source.revision_id AS VARCHAR(128))"
            )
        elif table_name == "sync_entity_head":
            key_expression = (
                "CAST(source.account_id AS VARCHAR(64)) || ':' || "
                "CAST(source.entity_id AS VARCHAR(128))"
            )
        elif table_name == "sync_event_receipt":
            key_expression = (
                "CAST(source.account_id AS VARCHAR(64)) || ':' || CAST(source.id AS VARCHAR(128))"
            )
        elif table_name == "sync_outbox":
            key_expression = (
                "CAST(source.account_id AS VARCHAR(64)) || ':' || "
                "CAST(source.event_id AS VARCHAR(128))"
            )
        connection.execute(
            sa.text(
                "INSERT INTO organization_resource "
                "(organization_id, table_name, row_key, attribution_account_id, "
                "attribution_column) "
                "SELECT organization.id, :table_name, "
                + key_expression
                + ", "
                + account_expression
                + ", :attribution_column"
                + " FROM "
                + table_name
                + " AS source JOIN organization ON organization.owner_account_id = "
                + account_expression
                + " AND organization.kind = 'personal' "
                "WHERE " + account_expression + " IS NOT NULL "
                "ON CONFLICT (table_name, row_key) DO NOTHING"
            ),
            {"table_name": table_name, "attribution_column": account_column},
        )


def upgrade() -> None:
    op.create_table(
        "organization_resource",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("table_name", sa.String(128), nullable=False),
        sa.Column("row_key", sa.String(512), nullable=False),
        sa.Column("attribution_account_id", sa.String(64), nullable=False),
        sa.Column("attribution_column", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["attribution_account_id"], ["account.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("table_name", "row_key", name="uq_organization_resource_row"),
    )
    op.create_index(
        "ix_organization_resource_organization", "organization_resource", ["organization_id"]
    )
    op.create_index(
        "ix_organization_resource_account", "organization_resource", ["attribution_account_id"]
    )

    # The source account remains the attribution owner. The personal org is
    # stable and already exists for every account after 0058.
    connection = op.get_bind()
    _ensure_visibility_plan_table(connection)
    _backfill_organization_resources(connection)
    for table_name, _key_column, account_column in LEGACY_SCOPE_ROWS:
        op.add_column(
            table_name,
            sa.Column("organization_id", sa.String(64), nullable=True),
        )
        account_expression = _account_expression(table_name, account_column)
        connection.execute(
            sa.text(
                "UPDATE " + table_name + " AS source SET organization_id = (SELECT organization.id "
                "FROM organization WHERE organization.owner_account_id = "
                + account_expression
                + " AND organization.kind = 'personal') WHERE organization_id IS NULL"
            )
        )
        op.alter_column(table_name, "organization_id", nullable=False)
        op.create_foreign_key(
            "fk_" + table_name + "_organization",
            table_name,
            "organization",
            ["organization_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index("ix_" + table_name + "_organization_id", table_name, ["organization_id"])

    # Anonymous audit entries remain organization-free; every attributed event
    # and every newly enqueued job can carry the same explicit tenant key.
    for table_name in ("audit_event", "job"):
        op.add_column(table_name, sa.Column("organization_id", sa.String(64), nullable=True))
        op.create_foreign_key(
            "fk_" + table_name + "_organization",
            table_name,
            "organization",
            ["organization_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index("ix_" + table_name + "_organization_id", table_name, ["organization_id"])
    # Adding the immutable tenant attribution is a metadata backfill, not an
    # audit mutation. The trigger rejects every UPDATE, so suspend it only for
    # this single statement while the application is stopped.
    connection.execute(sa.text("ALTER TABLE audit_event DISABLE TRIGGER audit_event_append_only"))
    connection.execute(
        sa.text(
            "UPDATE audit_event AS event SET organization_id = (SELECT organization.id "
            "FROM organization WHERE organization.owner_account_id = event.actor_account_id "
            "AND organization.kind = 'personal') WHERE event.actor_account_id IS NOT NULL"
        )
    )
    connection.execute(sa.text("ALTER TABLE audit_event ENABLE TRIGGER audit_event_append_only"))

    op.add_column("project_identity", sa.Column("provider_kind", sa.String(32), nullable=True))
    op.add_column(
        "project_identity", sa.Column("provider_installation_id", sa.String(128), nullable=True)
    )
    op.add_column(
        "project_identity", sa.Column("provider_namespace_id", sa.String(256), nullable=True)
    )
    op.add_column(
        "project_identity", sa.Column("immutable_repository_id", sa.String(128), nullable=True)
    )
    op.add_column("project_identity", sa.Column("current_url", sa.String(512), nullable=True))
    op.add_column("project_identity", sa.Column("observed_name", sa.String(200), nullable=True))
    op.add_column(
        "project_identity", sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "uq_project_identity_provider_repository",
        "project_identity",
        ["organization_id", "immutable_repository_id"],
        unique=True,
        postgresql_where=sa.text(
            "namespace = 'provider' AND state = 'active' AND immutable_repository_id IS NOT NULL"
        ),
        sqlite_where=sa.text(
            "namespace = 'provider' AND state = 'active' AND immutable_repository_id IS NOT NULL"
        ),
    )
    op.add_column("project_link", sa.Column("conflict_server_revision", sa.String(71)))
    op.add_column("project_link", sa.Column("conflict_client_revision", sa.String(71)))
    op.add_column("project_link", sa.Column("conflict_common_ancestor", sa.String(71)))

    op.create_table(
        "project_revision",
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("remote_project_id", sa.String(64), nullable=False),
        sa.Column("revision_id", sa.String(71), nullable=False),
        sa.Column("parent_revision_ids", sa.JSON, nullable=False),
        sa.Column("operation", sa.String(16), nullable=False),
        sa.Column("content_digest", sa.String(71), nullable=False),
        sa.Column("projection", sa.JSON, nullable=False),
        sa.Column("actor_account_id", sa.String(64), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["remote_project_id"], ["project_identity.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["actor_account_id"], ["account.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("organization_id", "remote_project_id", "revision_id"),
        sa.CheckConstraint(
            "operation in ('upsert', 'tombstone')", name="ck_project_revision_operation"
        ),
        sa.CheckConstraint(
            "json_array_length(parent_revision_ids) <= 2", name="ck_project_revision_parents"
        ),
    )
    op.create_index(
        "ix_project_revision_project_created",
        "project_revision",
        ["organization_id", "remote_project_id", "created_at"],
    )
    op.create_table(
        "project_revision_head",
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("remote_project_id", sa.String(64), nullable=False),
        sa.Column("revision_id", sa.String(71), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["remote_project_id"], ["project_identity.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("organization_id", "remote_project_id"),
    )
    op.create_table(
        "project_revision_receipt",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("remote_project_id", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_fingerprint", sa.String(71), nullable=False),
        sa.Column("response_body", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "organization_id",
            "remote_project_id",
            "idempotency_key",
            name="uq_project_revision_receipt_idempotency",
        ),
    )
    op.create_table(
        "project_link_proposal",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("local_project_id", sa.String(64), nullable=False),
        sa.Column("remote_project_id", sa.String(64), nullable=False),
        sa.Column("provider_project_id", sa.String(64), nullable=True),
        sa.Column("evidence", sa.JSON, nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="proposed"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.CheckConstraint("state = 'proposed'", name="ck_project_link_proposal_state"),
    )


def downgrade() -> None:
    op.drop_table("project_link_proposal")
    op.drop_table("project_revision_receipt")
    op.drop_table("project_revision_head")
    op.drop_index("ix_project_revision_project_created", table_name="project_revision")
    op.drop_table("project_revision")
    op.drop_index("uq_project_identity_provider_repository", table_name="project_identity")
    op.drop_column("project_link", "conflict_common_ancestor")
    op.drop_column("project_link", "conflict_client_revision")
    op.drop_column("project_link", "conflict_server_revision")
    for column in (
        "observed_at",
        "observed_name",
        "current_url",
        "immutable_repository_id",
        "provider_namespace_id",
        "provider_installation_id",
        "provider_kind",
    ):
        op.drop_column("project_identity", column)
    for table_name, _key_column, _account_column in reversed(LEGACY_SCOPE_ROWS):
        op.drop_index("ix_" + table_name + "_organization_id", table_name=table_name)
        op.drop_constraint("fk_" + table_name + "_organization", table_name, type_="foreignkey")
        op.drop_column(table_name, "organization_id")
    for table_name in ("job", "audit_event"):
        op.drop_index("ix_" + table_name + "_organization_id", table_name=table_name)
        op.drop_constraint("fk_" + table_name + "_organization", table_name, type_="foreignkey")
        op.drop_column(table_name, "organization_id")
    op.drop_index("ix_organization_resource_account", table_name="organization_resource")
    op.drop_index("ix_organization_resource_organization", table_name="organization_resource")
    op.drop_table("organization_resource")
