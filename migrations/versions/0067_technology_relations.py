"""Freeze tenant technology storage and exact corporate project identities.

DDL is an immutable migration snapshot, not imported from current ORM mappings.
Downgrade removes new structures but retains backfilled project identities.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0067_technology_relations"
down_revision: str | None = "0066_corporate_team_description"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = [
    "technology",
    "technology_category",
    "technology_landscape_policy",
    "organization_technology_decision",
    "project_technology_relation",
    "technology_alias",
    "technology_classification",
    "technology_coordinate_mapping",
    "technology_reference",
    "technology_scan",
    "technology_team_responsibility",
    "project_team_relation",
    "technology_usage_fact",
]
DDL = (
    """CREATE TABLE technology (
	id VARCHAR(64) NOT NULL,
	name VARCHAR(200) NOT NULL,
	description VARCHAR(4000) DEFAULT '' NOT NULL,
	icon_url VARCHAR(2048),
	official_urls JSON DEFAULT '[]' NOT NULL,
	lifecycle VARCHAR(16) DEFAULT 'draft' NOT NULL,
	restore_lifecycle VARCHAR(16) DEFAULT 'draft' NOT NULL,
	redirect_id VARCHAR(64),
	provenance VARCHAR(256) NOT NULL,
	revision INTEGER DEFAULT '1' NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	organization_id VARCHAR(64) NOT NULL,
	PRIMARY KEY (organization_id, id),
	FOREIGN KEY(organization_id, redirect_id) REFERENCES technology (organization_id, id) ON
        DELETE RESTRICT,
    CONSTRAINT ck_technology_lifecycle CHECK (
        lifecycle IN ('draft','active','deprecated','archived')),
	CONSTRAINT ck_technology_restore CHECK (restore_lifecycle IN ('draft','active','deprecated')),
	CONSTRAINT ck_technology_redirect CHECK (redirect_id IS NULL OR redirect_id <> id),
	CONSTRAINT ck_technology_revision CHECK (revision >= 1),
	FOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE RESTRICT
)""",
    """CREATE TABLE technology_category (
	id VARCHAR(64) NOT NULL,
	name VARCHAR(200) NOT NULL,
	normalized_name VARCHAR(200) NOT NULL,
	description VARCHAR(2000) DEFAULT '' NOT NULL,
	revision INTEGER DEFAULT '1' NOT NULL,
	provenance VARCHAR(256) NOT NULL,
	organization_id VARCHAR(64) NOT NULL,
	PRIMARY KEY (organization_id, id),
	CONSTRAINT uq_technology_category_name UNIQUE (organization_id, normalized_name),
	CONSTRAINT ck_technology_category_revision CHECK (revision >= 1),
	FOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE RESTRICT
)""",
    """CREATE TABLE technology_landscape_policy (
	inactivity_months INTEGER DEFAULT '9' NOT NULL,
	revision INTEGER DEFAULT '1' NOT NULL,
	organization_id VARCHAR(64) NOT NULL,
	PRIMARY KEY (organization_id),
	CONSTRAINT ck_landscape_inactivity CHECK (inactivity_months BETWEEN 1 AND 120),
	CONSTRAINT ck_landscape_policy_revision CHECK (revision >= 1),
	FOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE RESTRICT
)""",
    """CREATE TABLE organization_technology_decision (
	technology_id VARCHAR(64) NOT NULL,
	lead_account_id VARCHAR(64),
	approved BOOLEAN DEFAULT 'false' NOT NULL,
	adoption VARCHAR(16) DEFAULT 'none' NOT NULL,
	revision INTEGER DEFAULT '1' NOT NULL,
	organization_id VARCHAR(64) NOT NULL,
	PRIMARY KEY (organization_id, technology_id),
	FOREIGN KEY(organization_id, technology_id) REFERENCES technology (organization_id, id) ON
        DELETE RESTRICT,
	FOREIGN KEY(organization_id, lead_account_id) REFERENCES organization_membership
        (organization_id, account_id) ON DELETE RESTRICT,
	CONSTRAINT ck_technology_adoption CHECK (adoption IN ('none','assess','trial','adopt','hold')),
	CONSTRAINT ck_technology_decision_revision CHECK (revision >= 1),
	FOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE RESTRICT
)""",
    """CREATE TABLE project_technology_relation (
	id VARCHAR(64) NOT NULL,
	project_id VARCHAR(64) NOT NULL,
	project_namespace VARCHAR(16) DEFAULT 'remote' NOT NULL,
	technology_id VARCHAR(64) NOT NULL,
	state VARCHAR(16) DEFAULT 'current' NOT NULL,
	revision INTEGER DEFAULT '1' NOT NULL,
	organization_id VARCHAR(64) NOT NULL,
	PRIMARY KEY (organization_id, id),
	CONSTRAINT uq_project_technology_pair UNIQUE (organization_id, project_id, technology_id),
	FOREIGN KEY(organization_id, project_id, project_namespace) REFERENCES project_identity
        (organization_id, id, namespace) ON DELETE RESTRICT,
	CONSTRAINT ck_project_technology_namespace CHECK (project_namespace = 'remote'),
	FOREIGN KEY(organization_id, technology_id) REFERENCES technology (organization_id, id) ON
        DELETE RESTRICT,
	CONSTRAINT ck_project_technology_state CHECK (state IN ('current','retired')),
	CONSTRAINT ck_project_technology_revision CHECK (revision >= 1),
	FOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE RESTRICT
)""",
    """CREATE TABLE technology_alias (
	normalized_name VARCHAR(200) NOT NULL,
	technology_id VARCHAR(64) NOT NULL,
	name VARCHAR(200) NOT NULL,
	canonical BOOLEAN DEFAULT 'false' NOT NULL,
	organization_id VARCHAR(64) NOT NULL,
	PRIMARY KEY (organization_id, normalized_name),
	FOREIGN KEY(organization_id, technology_id) REFERENCES technology (organization_id, id) ON
        DELETE RESTRICT,
	FOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE RESTRICT
)""",
    """CREATE TABLE technology_classification (
	technology_id VARCHAR(64) NOT NULL,
	category_id VARCHAR(64) NOT NULL,
	organization_id VARCHAR(64) NOT NULL,
	PRIMARY KEY (organization_id, technology_id, category_id),
	FOREIGN KEY(organization_id, technology_id) REFERENCES technology (organization_id, id) ON
        DELETE RESTRICT,
	FOREIGN KEY(organization_id, category_id) REFERENCES technology_category (organization_id, id)
        ON DELETE RESTRICT,
	FOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE RESTRICT
)""",
    """CREATE TABLE technology_coordinate_mapping (
	version VARCHAR(128) NOT NULL,
	kind VARCHAR(32) NOT NULL,
	coordinate VARCHAR(512) NOT NULL,
	technology_id VARCHAR(64) NOT NULL,
	provenance VARCHAR(256) NOT NULL,
	organization_id VARCHAR(64) NOT NULL,
	PRIMARY KEY (organization_id, version, kind, coordinate, technology_id),
	FOREIGN KEY(organization_id, technology_id) REFERENCES technology (organization_id, id) ON
        DELETE RESTRICT,
	CONSTRAINT ck_mapping_kind CHECK (kind IN
        ('package','image','executable','configuration','alias')),
	FOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE RESTRICT
)""",
    """CREATE TABLE technology_reference (
	object_id VARCHAR(64) NOT NULL,
	technology_id VARCHAR(64) NOT NULL,
	meaning VARCHAR(16) NOT NULL,
	object_kind VARCHAR(16) NOT NULL,
	organization_id VARCHAR(64) NOT NULL,
	PRIMARY KEY (organization_id, object_id, technology_id, meaning),
	FOREIGN KEY(organization_id, technology_id) REFERENCES technology (organization_id, id) ON
        DELETE RESTRICT,
	CONSTRAINT ck_technology_reference_object CHECK (object_kind IN ('component','setup')),
	CONSTRAINT ck_technology_reference_meaning CHECK (meaning IN ('subject','applicability')),
	FOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE RESTRICT
)""",
    """CREATE TABLE technology_scan (
	id VARCHAR(64) NOT NULL,
	project_id VARCHAR(64) NOT NULL,
	project_namespace VARCHAR(16) DEFAULT 'remote' NOT NULL,
	fingerprint VARCHAR(71) NOT NULL,
	handoff JSON NOT NULL,
	organization_id VARCHAR(64) NOT NULL,
	PRIMARY KEY (organization_id, id),
	FOREIGN KEY(organization_id, project_id, project_namespace) REFERENCES project_identity
        (organization_id, id, namespace) ON DELETE RESTRICT,
	CONSTRAINT ck_technology_scan_namespace CHECK (project_namespace = 'remote'),
	FOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE RESTRICT
)""",
    """CREATE TABLE technology_team_responsibility (
	id VARCHAR(64) NOT NULL,
	technology_id VARCHAR(64) NOT NULL,
	team_id VARCHAR(64) NOT NULL,
	state VARCHAR(16) DEFAULT 'current' NOT NULL,
	revision INTEGER DEFAULT '1' NOT NULL,
	organization_id VARCHAR(64) NOT NULL,
	PRIMARY KEY (organization_id, id),
	CONSTRAINT uq_technology_team_pair UNIQUE (organization_id, technology_id, team_id),
	FOREIGN KEY(organization_id, technology_id) REFERENCES technology (organization_id, id) ON
        DELETE RESTRICT,
	FOREIGN KEY(organization_id, team_id) REFERENCES corporate_team (organization_id, id) ON
        DELETE RESTRICT,
	CONSTRAINT ck_technology_team_state CHECK (state IN ('current','retired')),
	CONSTRAINT ck_technology_team_revision CHECK (revision >= 1),
	FOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE RESTRICT
)""",
    """CREATE TABLE project_team_relation (
	id VARCHAR(64) NOT NULL,
	project_id VARCHAR(64) NOT NULL,
	team_id VARCHAR(64) NOT NULL,
	role VARCHAR(16) NOT NULL,
	state VARCHAR(16) DEFAULT 'current' NOT NULL,
	revision INTEGER DEFAULT '1' NOT NULL,
	organization_id VARCHAR(64) NOT NULL,
	PRIMARY KEY (organization_id, id),
	CONSTRAINT uq_project_team_pair UNIQUE (organization_id, project_id, team_id),
	FOREIGN KEY(organization_id, project_id) REFERENCES corporate_project (organization_id, id) ON
        DELETE RESTRICT,
	FOREIGN KEY(organization_id, team_id) REFERENCES corporate_team (organization_id, id) ON
        DELETE RESTRICT,
	CONSTRAINT ck_project_team_role CHECK (role IN ('owner','responsible','contributor')),
	CONSTRAINT ck_project_team_state CHECK (state IN ('current','retired')),
	CONSTRAINT ck_project_team_revision CHECK (revision >= 1),
	FOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE RESTRICT
)""",
    """CREATE TABLE technology_usage_fact (
	relation_id VARCHAR(64) NOT NULL,
	context VARCHAR(32) NOT NULL,
	review VARCHAR(16) NOT NULL,
	version VARCHAR(128),
	version_kind VARCHAR(32) DEFAULT 'unknown' NOT NULL,
	freshness VARCHAR(16) DEFAULT 'unknown' NOT NULL,
	evidence JSON DEFAULT '[]' NOT NULL,
	organization_id VARCHAR(64) NOT NULL,
	PRIMARY KEY (organization_id, relation_id, context),
	FOREIGN KEY(organization_id, relation_id) REFERENCES project_technology_relation
        (organization_id, id) ON DELETE RESTRICT,
	CONSTRAINT ck_usage_context CHECK (context IN
        ('production','development','testing','browser_support')),
	CONSTRAINT ck_usage_review CHECK (review IN
        ('proposed','confirmed','rejected','overridden','retired')),
	CONSTRAINT ck_usage_freshness CHECK (freshness IN ('current','stale','absent','unknown')),
	CONSTRAINT ck_usage_version_kind CHECK (version_kind IN
        ('unknown','declared_range','observed_version')),
	CONSTRAINT ck_usage_version_value CHECK ((version_kind = 'unknown') = (version IS NULL)),
	FOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE RESTRICT
)""",
    """CREATE UNIQUE INDEX uq_project_owner ON project_team_relation (organization_id, project_id)
        WHERE state = 'current' AND role = 'owner'""",
)


def upgrade() -> None:
    op.execute("SELECT set_config('ai_stp.organization_id', '*', true)")
    op.create_unique_constraint(
        "uq_project_identity_tenant_id", "project_identity", ["organization_id", "id"]
    )
    op.create_unique_constraint(
        "uq_project_identity_tenant_namespace",
        "project_identity",
        ["organization_id", "id", "namespace"],
    )
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM corporate_project c JOIN project_identity p ON p.id = c.id
                WHERE p.organization_id <> c.organization_id OR p.namespace <> 'remote'
                   OR p.display_name <> c.name OR p.state <> c.state
            ) THEN
                RAISE EXCEPTION 'corporate project identity collision; reconcile exact IDs first';
            END IF;
        END $$;
    """)
    op.execute("""
        INSERT INTO project_identity
            (id, organization_id, namespace, external_key, display_name, state, revision)
        SELECT c.id, c.organization_id, 'remote', 'corporate:' || c.id, c.name, c.state, c.revision
        FROM corporate_project c WHERE NOT EXISTS (SELECT 1 FROM project_identity p WHERE p.id
        = c.id)
    """)
    op.add_column(
        "corporate_project",
        sa.Column("identity_namespace", sa.String(16), nullable=False, server_default="remote"),
    )
    op.add_column(
        "corporate_project",
        sa.Column("repository_activity_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("corporate_project", sa.Column("activity_override", sa.String(16), nullable=True))
    op.create_check_constraint(
        "ck_corporate_project_identity", "corporate_project", "identity_namespace = 'remote'"
    )
    op.create_check_constraint(
        "ck_corporate_project_activity_override",
        "corporate_project",
        "activity_override IS NULL OR activity_override IN ('active','inactive')",
    )
    op.create_foreign_key(
        "fk_corporate_project_identity",
        "corporate_project",
        "project_identity",
        ["organization_id", "id", "identity_namespace"],
        ["organization_id", "id", "namespace"],
        ondelete="RESTRICT",
    )
    for statement in DDL:
        op.execute(statement)
    op.execute("""
        CREATE FUNCTION ai_stp_technology_identity_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
            IF TG_OP = 'UPDATE' AND (
                NEW.organization_id IS DISTINCT FROM OLD.organization_id
                OR to_jsonb(NEW) -> 'id' IS DISTINCT FROM to_jsonb(OLD) -> 'id'
                OR to_jsonb(NEW) -> 'project_id' IS DISTINCT FROM to_jsonb(OLD) -> 'project_id'
                OR to_jsonb(NEW) -> 'technology_id' IS DISTINCT FROM to_jsonb(OLD) ->
        'technology_id'
                OR to_jsonb(NEW) -> 'team_id' IS DISTINCT FROM to_jsonb(OLD) -> 'team_id'
                OR to_jsonb(NEW) -> 'relation_id' IS DISTINCT FROM to_jsonb(OLD) -> 'relation_id'
            ) THEN
                RAISE EXCEPTION 'technology relation identity and endpoints are immutable';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM organization
                WHERE id = NEW.organization_id AND kind = 'corporate') THEN
                RAISE EXCEPTION 'technology registry requires a corporate tenant';
            END IF;
            RETURN NEW;
        END $$;
    """)
    tenant = (
        "current_setting('ai_stp.organization_id', true) = '*' OR "
        "organization_id = current_setting('ai_stp.organization_id', true)"
    )
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_policy ON {table} USING ({tenant}) WITH CHECK ({tenant})"
        )
        op.execute(
            f"CREATE TRIGGER {table}_identity_immutable BEFORE INSERT OR UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION ai_stp_technology_identity_immutable()"
        )
    for table in ("technology_scan", "technology_coordinate_mapping"):
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_audit_event_mutation()"
        )
    op.execute("""
        INSERT INTO corporate_role_permission (organization_id, role, permission)
        SELECT r.organization_id, r.name, p.permission
        FROM corporate_role r CROSS JOIN (VALUES
            ('category.create'), ('category.read'), ('category.update'), ('category.delete'),
            ('category.list'), ('technology.create'), ('technology.read'), ('technology.update'),
            ('technology.delete'), ('technology.list'), ('technology.approve'),
            ('technology.merge'),
            ('technology.responsibility'), ('landscape.read'), ('landscape.manage'),
            ('technology.scan.publish'),
            ('project_team.create'), ('project_team.read'), ('project_team.update'),
            ('project_team.delete'), ('project_team.list'),
            ('project_technology.create'), ('project_technology.read'),
            ('project_technology.update'),
            ('project_technology.delete'), ('project_technology.list'),
            ('technology_team.create'), ('technology_team.read'), ('technology_team.update'),
            ('technology_team.delete'), ('technology_team.list'),
            ('technology_decision.create'), ('technology_decision.read'),
            ('technology_decision.update'),
            ('technology_decision.delete'), ('technology_decision.list')
        ) p(permission) WHERE r.name = 'superadmin'
        ON CONFLICT DO NOTHING
    """)
    op.execute(
        "UPDATE organization SET policy_revision = policy_revision + 1 WHERE kind = 'corporate'"
    )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
    op.execute("DROP FUNCTION ai_stp_technology_identity_immutable()")
    op.drop_constraint("fk_corporate_project_identity", "corporate_project", type_="foreignkey")
    op.drop_constraint("ck_corporate_project_activity_override", "corporate_project", type_="check")
    op.drop_constraint("ck_corporate_project_identity", "corporate_project", type_="check")
    for column in ("activity_override", "repository_activity_at", "identity_namespace"):
        op.drop_column("corporate_project", column)
    op.drop_constraint("uq_project_identity_tenant_namespace", "project_identity", type_="unique")
    op.drop_constraint("uq_project_identity_tenant_id", "project_identity", type_="unique")
