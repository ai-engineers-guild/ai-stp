"""Explicit local Twinby demo. Never part of application startup or production seed."""

# pyright: reportPrivateUsage=false

from hashlib import sha256
from typing import Any, Literal, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.support.catalog_seed import (
    FIXTURE_PUBLISHED_AT,
    _component_body,
    _component_ref,
    _passport_digest,
    _seal_component,
    _seal_setup,
    _setup_body,
    upsert_seed_version,
)

from ai_stp_platform.catalog_ownership_models import CorporateCatalogOwnership
from ai_stp_platform.db import Base
from ai_stp_platform.models import Account
from ai_stp_platform.organization_models import (
    CorporateCatalogAssignment,
    CorporateProject,
    CorporateRoleBinding,
    CorporateTeam,
    CorporateTeamMember,
    Organization,
    OrganizationMembership,
)
from ai_stp_platform.technology_models import (
    EmployeeTechnology,
    ProjectTeamRelation,
    ProjectTechnologyRelation,
    Technology,
    TechnologyAlias,
    TechnologyCategory,
    TechnologyClassification,
    TechnologyTeamResponsibility,
)
from ai_stp_platform.tenant_scope import set_tenant_scope

PROVENANCE = "ai_stp:corporate-overview-demo:1"
T = TypeVar("T", bound=Base)
PEOPLE = (
    ("Alex Kim", "Project Lead"),
    ("Elena Smirnova", "Engineering Lead"),
    ("Maria Kolesnikova", "ML Engineer"),
    ("Ivan Sokolov", "Data Analyst"),
    ("Anna Morozova", "Research Engineer"),
    ("Maksim Ryabov", "Project Lead"),
    ("Natalia Petrova", "Support Lead"),
    ("Ilya Kuznetsov", "Platform Lead"),
    ("Daria Volkova", "Support Specialist"),
    ("Pavel Orlov", "Support Engineer"),
    ("Sofia Lebedeva", "DevOps Engineer"),
    ("Dmitry Fedorov", "Platform Engineer"),
    ("Oleg Smirnov", "Data Engineer"),
)
# The five pre-existing local memberships are kept, but generated placeholder
# labels are replaced so the demo never exposes internal account ids as names.
LEGACY_MEMBER_NAMES = {
    "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z": "Nina Volkova",
    "account_01JQZK7B8N4M6P2R9T5V0X3YA1": "Sergey Petrov",
    "account_01KZB5N3KR7Y6PVNBR41XGG7W1": "Artem Letyushev",
    "account_01M1CPQ5KXWKZXG58MZX8ZF4GJ": "Mikhail Orlov",
    "account_01M2APVCY4D7VBRQQF9N7W4N6A": "Biba",
}
TEAMS = (
    ("Product & Engineering", "Build and iterate on growth features.", (2, 3, 4), 1),
    ("Customer Success", "User support and success operations.", (8, 9), 6),
    ("Platform Engineering", "Infrastructure, tooling and platform services.", (10, 11), 7),
    ("Data Platform", "Data infrastructure and experimentation.", (0, 5, 12), None),
)
TECHNOLOGIES = (
    ("Python", "Language"),
    ("PostgreSQL", "DBMS"),
    ("Kubernetes", "Container and orchestration platform"),
    ("Terraform", "Infrastructure provisioning tool"),
    ("AWS", "Cloud platform"),
    ("ClickHouse", "DBMS"),
)
COMPONENTS = (
    "Claude Code",
    "Context7",
    "User Service",
    "Growth API",
    "Jupyter",
    "MLflow",
    "Weights & Biases",
    "Evaluation Suite",
    "Agent Gateway",
    "Context Registry",
    "Knowledge Ingestion",
    "Prompt Registry",
    "Intercom",
    "Zendesk",
    "Support Service",
    "Notification Worker",
    "Support Playbook",
    "Response Templates",
    "Cluster",
    "VPC",
    "EKS",
    "Infrastructure Review",
    "Deployment Hook",
    "Health Check",
    "Monitoring Agent",
    "Incident Runbook",
    "Security Policy",
    "Access Review",
    "Backup Hook",
    "Release Command",
    "Platform Settings",
    "Memory Service",
)
SETUPS = (
    "staging",
    "production",
    "research",
    "support-staging",
    "support-production",
    "dev",
    "prod",
    "analytics",
)


def fixture_id(prefix: str, key: str) -> str:
    """Fixed valid IDs, scoped by tenant where IDs are globally unique."""
    return prefix + "_0" + sha256(f"{PROVENANCE}:{key}".encode()).hexdigest()[:25].upper()


async def seed_demo(
    db: AsyncSession, organization_id: str, expected_revision: int
) -> dict[str, int]:
    await set_tenant_scope(db, organization_id)
    org = await db.get(Organization, organization_id, with_for_update=True)
    if org is None or org.kind != "corporate" or org.state != "active":
        raise ValueError("active corporate organization required")
    if org.revision != expected_revision or org.display_name not in {"test_twinby", "Twinby"}:
        raise ValueError("demo target precondition changed")
    projects = list(
        (
            await db.scalars(
                select(CorporateProject).where(CorporateProject.organization_id == organization_id)
            )
        ).all()
    )
    by_name = {row.name: row for row in projects}
    if set(by_name) != {"Growth Experiments", "Twinby Dating Core"}:
        raise ValueError("demo requires the two existing reference projects")
    members = list(
        (
            await db.scalars(
                select(OrganizationMembership).where(
                    OrganizationMembership.organization_id == organization_id
                )
            )
        ).all()
    )
    demo_accounts = [fixture_id("account", f"{organization_id}:{name}") for name, _ in PEOPLE]
    existing = [row for row in members if row.account_id not in demo_accounts]
    if len(existing) != 5:
        raise ValueError("demo expects five existing memberships; no existing member is removed")
    if org.display_name != "Twinby":
        org.display_name = "Twinby"
        org.revision += 1
    for member in existing:
        if member.account_id in LEGACY_MEMBER_NAMES:
            display_name = LEGACY_MEMBER_NAMES[member.account_id]
            member.display_name = display_name
            account = await db.get(Account, member.account_id)
            if account is not None:
                account.display_name = display_name
    for (name, title), account_id in zip(PEOPLE, demo_accounts, strict=True):
        if await db.get(Account, account_id) is None:
            db.add(Account(id=account_id))  # No credentials, OAuth identity, or public profile.
            await db.flush()
        member = await db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.account_id == account_id,
            )
        )
        if member is None:
            db.add(
                OrganizationMembership(
                    organization_id=organization_id,
                    account_id=account_id,
                    display_name=name,
                    role="staff",
                    state="active",
                    profile={"description": title},
                    profile_revision=1,
                )
            )
    await db.flush()

    async def add(model: type[T], key: Any, **fields: Any) -> T:
        row = await db.get(model, key)
        if row is None:
            row = model(**fields)
            db.add(row)
            await db.flush()
        return row

    teams: list[CorporateTeam] = []
    for name, description, roster, lead in TEAMS:
        team = await db.scalar(
            select(CorporateTeam).where(
                CorporateTeam.organization_id == organization_id, CorporateTeam.name == name
            )
        )
        if team is None:
            team = await add(
                CorporateTeam,
                fixture_id("operation", f"{organization_id}:{name}"),
                id=fixture_id("operation", f"{organization_id}:{name}"),
                organization_id=organization_id,
                name=name,
                description=description,
            )
        elif not team.description:
            team.description = description
            team.revision += 1
        teams.append(team)
        for person in roster + (() if lead is None else (lead,)):
            account_id = demo_accounts[person]
            await add(
                CorporateTeamMember,
                (organization_id, team.id, account_id),
                organization_id=organization_id,
                team_id=team.id,
                account_id=account_id,
                role="lead" if person == lead else "staff",
            )
    for member in existing:
        await add(
            CorporateTeamMember,
            (organization_id, teams[3].id, member.account_id),
            organization_id=organization_id,
            team_id=teams[3].id,
            account_id=member.account_id,
            role="staff",
        )
    for project_name, team_indices, lead in (
        ("Growth Experiments", (0, 3), 0),
        ("Twinby Dating Core", (1, 2), 5),
    ):
        project = by_name[project_name]
        if not project.profile:
            project.profile = {
                "description": "Drive user growth through experimental products and features."
                if lead == 0
                else "Core platform for Twinby dating service."
            }
            project.profile_revision += 1
        await add(
            CorporateRoleBinding,
            fixture_id("operation", f"{organization_id}:{project.id}:lead"),
            id=fixture_id("operation", f"{organization_id}:{project.id}:lead"),
            organization_id=organization_id,
            account_id=demo_accounts[lead],
            role="lead",
            scope_kind="project",
            scope_id=project.id,
            state="active",
        )
        for index in team_indices:
            relation_id = fixture_id(
                "relation", f"{organization_id}:{project.id}:{teams[index].id}"
            )
            await add(
                ProjectTeamRelation,
                (organization_id, relation_id),
                id=relation_id,
                organization_id=organization_id,
                project_id=project.id,
                team_id=teams[index].id,
                role="owner" if index == team_indices[0] else "contributor",
            )
    tech_ids: list[str] = []
    for name, category in TECHNOLOGIES:
        category_id = fixture_id("category", category)
        await add(
            TechnologyCategory,
            (organization_id, category_id),
            organization_id=organization_id,
            id=category_id,
            name=category,
            normalized_name=category.casefold(),
            provenance=PROVENANCE,
        )
        tech_id = fixture_id("technology", name)
        tech_ids.append(tech_id)
        await add(
            Technology,
            (organization_id, tech_id),
            organization_id=organization_id,
            id=tech_id,
            name=name,
            description=f"{name} in the Twinby demo technology landscape.",
            lifecycle="active",
            provenance=PROVENANCE,
        )
        await add(
            TechnologyAlias,
            (organization_id, name.casefold()),
            organization_id=organization_id,
            normalized_name=name.casefold(),
            name=name,
            technology_id=tech_id,
            canonical=True,
        )
        await add(
            TechnologyClassification,
            (organization_id, tech_id, category_id),
            organization_id=organization_id,
            technology_id=tech_id,
            category_id=category_id,
        )
    for project_name, indices in (
        ("Growth Experiments", (0, 1)),
        ("Twinby Dating Core", (2, 3, 4)),
    ):
        for index in indices:
            relation_id = fixture_id("relation", f"{organization_id}:{project_name}:{index}")
            await add(
                ProjectTechnologyRelation,
                (organization_id, relation_id),
                id=relation_id,
                organization_id=organization_id,
                project_id=by_name[project_name].id,
                technology_id=tech_ids[index],
            )
    for team, indices in zip(teams, ((0, 1), (0, 1), (2, 3, 4), (5,)), strict=True):
        for index in indices:
            relation_id = fixture_id("relation", f"{organization_id}:{team.id}:tech:{index}")
            await add(
                TechnologyTeamResponsibility,
                (organization_id, relation_id),
                id=relation_id,
                organization_id=organization_id,
                team_id=team.id,
                technology_id=tech_ids[index],
            )
    for person in (2, 3, 4):
        relation_id = fixture_id("relation", f"{organization_id}:{person}:python")
        await add(
            EmployeeTechnology,
            (organization_id, relation_id),
            id=relation_id,
            organization_id=organization_id,
            account_id=demo_accounts[person],
            technology_id=tech_ids[0],
        )

    catalog_ids: dict[str, list[str]] = {"component": [], "setup": []}
    kind_names: tuple[tuple[Literal["component", "setup"], tuple[str, ...]], ...] = (
        ("component", COMPONENTS),
        ("setup", SETUPS),
    )
    for kind, names in kind_names:
        for name in names:
            stable_id = fixture_id(kind, f"{organization_id}:{name}")
            catalog_ids[kind].append(stable_id)
            fields: dict[str, Any] = {
                "stable_id": stable_id,
                "name": name,
                "description": f"Local demo: {name}. Not an installable production configuration.",
                "version": "1.0",
                "tags": ["devops"],
                "harness_id": "claude-code",
                "owner_id": demo_accounts[0],
            }
            passport = (
                _seal_component(_component_body(**fields, component_type="skill"))
                if kind == "component"
                else _seal_setup(
                    _setup_body(
                        **fields,
                        purpose="local-demo",
                        target_role="developer",
                        components=[_component_ref(catalog_ids["component"][0])],
                    )
                )
            )
            await upsert_seed_version(
                db,
                object_kind=kind,
                passport=passport,
                published_at_wire=FIXTURE_PUBLISHED_AT,
                passport_digest=_passport_digest(passport),
            )
            await add(
                CorporateCatalogOwnership,
                (organization_id, kind, stable_id),
                organization_id=organization_id,
                object_kind=kind,
                stable_id=stable_id,
                owner_account_id=demo_accounts[0],
            )
    assignments = (
        ("project_id", by_name["Growth Experiments"].id, range(12), (0, 1, 2)),
        ("project_id", by_name["Twinby Dating Core"].id, range(12, 32), (3, 4, 5, 6, 7)),
        ("team_id", teams[0].id, range(8), (0, 1)),
        ("team_id", teams[1].id, range(12, 18), (3, 4)),
        ("team_id", teams[2].id, range(18, 32), (5, 6, 7)),
        ("account_id", demo_accounts[2], (4, 5), (5,)),
        ("account_id", demo_accounts[3], (), (7,)),
        ("account_id", demo_accounts[4], (6,), (2,)),
    )
    for column, subject_id, components, setups in assignments:
        for kind, indices in (("component", components), ("setup", setups)):
            for index in indices:
                stable_id = catalog_ids[kind][index]
                assignment_id = fixture_id(
                    "operation", f"{organization_id}:{subject_id}:{stable_id}"
                )
                await add(
                    CorporateCatalogAssignment,
                    assignment_id,
                    id=assignment_id,
                    organization_id=organization_id,
                    **{column: subject_id},
                    object_kind=kind,
                    stable_id=stable_id,
                    version="1.0",
                )
    await db.flush()
    totals: dict[str, int] = {}
    for key, model in (
        ("projects", CorporateProject),
        ("teams", CorporateTeam),
        ("employees", OrganizationMembership),
        ("technologies", Technology),
    ):
        totals[key] = int(
            await db.scalar(
                select(func.count())
                .select_from(model)
                .where(model.organization_id == organization_id)
            )
            or 0
        )
    return totals
