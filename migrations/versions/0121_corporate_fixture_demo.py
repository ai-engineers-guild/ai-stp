"""Fixture corporate organization for local development acceptance.

The deployment allows exactly one corporate organization (`corporate bootstrap
is closed`), so the fixture is a full bootstrap-parity tenant: roles and their
permission matrix, functional taxonomy, twenty seed-identity technologies with
coordinate mappings, four teams, four projects, and twelve employees with the
same membership/binding graph `insert_membership_graph` writes. Skipped
entirely when a corporate organization already exists.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import insert

from ai_stp_api.slices.corporate.service import ROLE_PERMISSIONS
from ai_stp_contracts.technology import normalize_technology_name
from ai_stp_contracts.technology_seed import (
    SEED_COORDINATES,
    SEED_COORDINATES_VERSION,
    SEED_PROVENANCE,
    SEED_TECHNOLOGIES,
)
from ai_stp_platform.technology_taxonomy import (
    classify_seed_technologies,
    install_technology_taxonomy,
)

revision = "0121_corporate_fixture_demo"
down_revision = "0120_finding_review_category"
branch_labels = None
depends_on = None

# ck_organization_id: 'organization_' prefix + 26 chars = 39 total.
ORG = "organization_fixture0000000000000000000"

TEAMS = [
    ("team_fixture_core", "Core Platform"),
    ("team_fixture_web", "Product Web"),
    ("team_fixture_data", "Data Services"),
    ("team_fixture_ops", "Infrastructure"),
]
# (account_id, display_name, team_index, is_lead)
EMPLOYEES = [
    ("account_fixture_emp01", "Anna Smirnova", 0, True),
    ("account_fixture_emp02", "Ivan Petrov", 0, False),
    ("account_fixture_emp03", "Maria Kuznetsova", 0, False),
    ("account_fixture_emp04", "Dmitry Volkov", 1, True),
    ("account_fixture_emp05", "Elena Sokolova", 1, False),
    ("account_fixture_emp06", "Sergey Morozov", 1, False),
    ("account_fixture_emp07", "Olga Novikova", 2, True),
    ("account_fixture_emp08", "Pavel Fedorov", 2, False),
    ("account_fixture_emp09", "Tatiana Orlova", 2, False),
    ("account_fixture_emp10", "Andrey Zaitsev", 3, True),
    ("account_fixture_emp11", "Natalia Romanova", 3, False),
    ("account_fixture_emp12", "Viktor Lebedev", 3, False),
]
PROJECTS = [
    ("project_fixture_devtools", "Dev Tools"),
    ("project_fixture_portal", "Customer Portal"),
    ("project_fixture_analytics", "Analytics API"),
    ("project_fixture_deploy", "Deploy Automation"),
]
# Twenty seed identities, two per functional taxonomy category.
TECH_SUFFIXES = {
    6,  # React — web-ui
    7,  # PostgreSQL — relational-databases
    8,  # Python — languages
    9,  # TypeScript — languages
    32,  # Django — server-frameworks
    33,  # FastAPI — server-frameworks
    35,  # Next.js — web-ui
    83,  # MySQL — relational-databases
    106,  # Redis — key-value-databases
    108,  # Valkey — key-value-databases
    112,  # RabbitMQ — message-brokers
    118,  # Apache ActiveMQ — message-brokers
    130,  # GitHub Actions — ci-cd
    131,  # Jenkins — ci-cd
    139,  # Docker Compose — container-orchestration
    140,  # Kubernetes — container-orchestration
    146,  # Terraform — iac
    147,  # Pulumi — iac
    163,  # Prometheus — metrics
    164,  # Grafana — metrics
}
TECHNOLOGIES = {
    identifier: metadata.name
    for identifier, metadata in SEED_TECHNOLOGIES
    if int(identifier.rsplit("_", 1)[-1]) in TECH_SUFFIXES
}


def _strings(name: str, *columns: str) -> sa.Table:
    return sa.table(name, *(sa.column(key, sa.String()) for key in columns))


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("SELECT set_config('ai_stp.organization_id', '*', true)"))
    if connection.scalar(sa.text("SELECT 1 FROM organization WHERE kind = 'corporate' LIMIT 1")):
        return

    organizations = _strings("organization", "id", "kind", "display_name", "state")
    connection.execute(
        insert(organizations).values(
            id=ORG, kind="corporate", display_name="Fixture Corp", state="active"
        )
    )

    accounts = _strings(
        "account", "id", "handle", "handle_normalized", "display_name", "display_name_normalized"
    )
    for account_id, display_name, _team, _lead in EMPLOYEES:
        handle = ".".join(display_name.lower().split())
        connection.execute(
            insert(accounts).values(
                id=account_id,
                handle=handle,
                handle_normalized=handle,
                display_name=display_name,
                display_name_normalized=display_name.lower(),
            )
        )

    roles = _strings("corporate_role", "organization_id", "name", "parent_role")
    permissions = _strings("corporate_role_permission", "organization_id", "role", "permission")
    for role in ("superadmin", "lead", "staff"):
        connection.execute(insert(roles).values(organization_id=ORG, name=role, parent_role=None))
        for permission in ROLE_PERMISSIONS[role]:
            connection.execute(
                insert(permissions).values(organization_id=ORG, role=role, permission=permission)
            )

    teams = _strings("corporate_team", "id", "organization_id", "name", "description", "state")
    for team_id, name in TEAMS:
        connection.execute(
            insert(teams).values(
                id=team_id, organization_id=ORG, name=name, description="", state="active"
            )
        )

    memberships = _strings(
        "organization_membership",
        "organization_id",
        "account_id",
        "display_name",
        "role",
        "state",
    )
    team_members = _strings(
        "corporate_team_member", "organization_id", "team_id", "account_id", "role"
    )
    bindings = _strings(
        "corporate_role_binding",
        "id",
        "organization_id",
        "account_id",
        "role",
        "scope_kind",
        "scope_id",
        "state",
        "origin",
        "coverage",
    )
    binding_seq = 0

    def binding(account_id: str, role: str, scope_kind: str, scope_id: str, origin: str) -> None:
        nonlocal binding_seq
        binding_seq += 1
        connection.execute(
            insert(bindings).values(
                id=f"operation_fixture_{binding_seq:03d}",
                organization_id=ORG,
                account_id=account_id,
                role=role,
                scope_kind=scope_kind,
                scope_id=scope_id,
                state="active",
                origin=origin,
                coverage="self",
            )
        )

    for account_id, display_name, team_index, is_lead in EMPLOYEES:
        role = "lead" if is_lead else "staff"
        connection.execute(
            insert(memberships).values(
                organization_id=ORG,
                account_id=account_id,
                display_name=display_name,
                role=role,
                state="active",
            )
        )
        binding(account_id, role, "organization", ORG, "membership")
        team_id = TEAMS[team_index][0]
        connection.execute(
            insert(team_members).values(
                organization_id=ORG, team_id=team_id, account_id=account_id, role=role
            )
        )
        binding(account_id, role, "team", team_id, "assignment")

    identities = _strings(
        "project_identity",
        "id",
        "organization_id",
        "namespace",
        "external_key",
        "display_name",
        "state",
    )
    projects = _strings("corporate_project", "id", "organization_id", "name", "state")
    project_members = _strings(
        "corporate_project_member", "organization_id", "project_id", "account_id"
    )
    for index, (project_id, name) in enumerate(PROJECTS):
        connection.execute(
            insert(identities).values(
                id=project_id,
                organization_id=ORG,
                namespace="remote",
                external_key=f"fixture/{project_id.removeprefix('project_fixture_')}",
                display_name=name,
                state="active",
            )
        )
        connection.execute(
            insert(projects).values(id=project_id, organization_id=ORG, name=name, state="active")
        )
        for account_id, _name, team_index, _lead in EMPLOYEES:
            if team_index == index:
                connection.execute(
                    insert(project_members).values(
                        organization_id=ORG, project_id=project_id, account_id=account_id
                    )
                )

    install_technology_taxonomy(connection, ORG)
    technologies = _strings(
        "technology",
        "organization_id",
        "id",
        "name",
        "provenance",
        "lifecycle",
        "restore_lifecycle",
    )
    aliases = sa.table(
        "technology_alias",
        *(
            sa.column(key, sa.String())
            for key in ("organization_id", "technology_id", "name", "normalized_name")
        ),
        sa.column("canonical", sa.Boolean()),
    )
    mappings = _strings(
        "technology_coordinate_mapping",
        "organization_id",
        "version",
        "kind",
        "coordinate",
        "technology_id",
        "provenance",
    )
    for technology_id, name in TECHNOLOGIES.items():
        connection.execute(
            insert(technologies).values(
                organization_id=ORG,
                id=technology_id,
                name=name,
                provenance=SEED_PROVENANCE,
                lifecycle="active",
                restore_lifecycle="active",
            )
        )
        connection.execute(
            insert(aliases).values(
                organization_id=ORG,
                technology_id=technology_id,
                name=name,
                normalized_name=normalize_technology_name(name),
                canonical=True,
            )
        )
    for technology_id, kind, coordinate in SEED_COORDINATES:
        if technology_id in TECHNOLOGIES:
            connection.execute(
                insert(mappings).values(
                    organization_id=ORG,
                    version=SEED_COORDINATES_VERSION,
                    kind=kind,
                    coordinate=coordinate,
                    technology_id=technology_id,
                    provenance=SEED_PROVENANCE,
                )
            )
    classify_seed_technologies(connection, ORG, set(TECHNOLOGIES))


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("SELECT set_config('ai_stp.organization_id', '*', true)"))
    for table in (
        "technology_coordinate_mapping",
        "technology_classification",
        "technology_alias",
        "technology",
        "technology_category",
        "technology_area",
    ):
        connection.execute(
            sa.text(f"DELETE FROM {table} WHERE organization_id = :org"), {"org": ORG}
        )
    connection.execute(sa.text("DELETE FROM organization WHERE id = :org"), {"org": ORG})
    connection.execute(sa.text("DELETE FROM account WHERE id LIKE 'account\\_fixture\\_%'"))
