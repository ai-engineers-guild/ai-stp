"""Defaults, scanner coverage, and owner edits on a migrated tenant registry."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate.service import bootstrap
from ai_stp_api.slices.technology.service import import_seed
from ai_stp_contracts.corporate import CorporateBootstrapRequest
from ai_stp_contracts.technology import TechnologySeedRequest
from ai_stp_contracts.technology_seed import SEED_TECHNOLOGIES
from ai_stp_contracts.technology_taxonomy import (
    CATEGORY_IDS,
    TAXONOMY_AREAS,
    TAXONOMY_CATEGORIES,
    TAXONOMY_CLASSIFICATIONS,
)
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account
from ai_stp_platform.organization_models import Organization
from ai_stp_platform.technology_models import (
    Technology,
    TechnologyAlias,
    TechnologyArea,
    TechnologyCategory,
    TechnologyClassification,
)
from ai_stp_platform.technology_taxonomy import (
    classify_seed_technologies,
    install_technology_taxonomy,
)
from ai_stp_platform.tenant_scope import set_tenant_scope


async def test_default_taxonomy_classifies_scanner_corpus_and_preserves_edits(
    db_session: AsyncSession,
) -> None:
    account_id = new_id("account")
    db_session.add(Account(id=account_id, status="active"))
    await db_session.flush()
    organization = await bootstrap(
        db_session,
        payload=CorporateBootstrapRequest(
            organization_name="Taxonomy acceptance",
            superadmin_account_id=account_id,
            idempotency_key="taxonomy-bootstrap-0001",
        ),
        request_id="taxonomy-test",
    )
    org = organization.organization_id
    assert (
        len(
            list(
                await db_session.scalars(
                    select(TechnologyArea).where(TechnologyArea.organization_id == org)
                )
            )
        )
        == 13
    )
    assert (
        len(
            list(
                await db_session.scalars(
                    select(TechnologyCategory).where(TechnologyCategory.organization_id == org)
                )
            )
        )
        == 117
    )
    assert not await (await db_session.connection()).run_sync(install_technology_taxonomy, org)
    await import_seed(
        db_session,
        ctx=AuthContext(account_id, "taxonomy-session", None, "active", False, False),
        organization_id=org,
        payload=TechnologySeedRequest(
            authorization_revision=1, idempotency_key="taxonomy-seed-0001"
        ),
        request_id="taxonomy-test",
    )
    classes: dict[str, set[str]] = {}
    for technology_id, category_id in await db_session.execute(
        select(TechnologyClassification.technology_id, TechnologyClassification.category_id).where(
            TechnologyClassification.organization_id == org
        )
    ):
        classes.setdefault(technology_id, set()).add(category_id)
    for technology_id, _metadata in SEED_TECHNOLOGIES:
        assert set(TAXONOMY_CLASSIFICATIONS[technology_id]) <= classes[technology_id]
    assert CATEGORY_IDS["server-frameworks"] in classes["technology_00000000000000000000000033"]
    assert CATEGORY_IDS["analytical-databases"] in classes["technology_00000000000000000000000086"]
    assert len(TAXONOMY_CLASSIFICATIONS["technology_00000000000000000000000001"]) > 1
    category = await db_session.get(TechnologyCategory, (org, CATEGORY_IDS["server-frameworks"]))
    assert category is not None and category.area_id == TAXONOMY_AREAS[2][0]
    category.name = "Owner server tools"
    category.normalized_name = "owner server tools"
    category.description = "Owner description"
    category.state = "archived"
    category.revision += 1
    await db_session.flush()
    assert not await (await db_session.connection()).run_sync(install_technology_taxonomy, org)
    assert not await (await db_session.connection()).run_sync(classify_seed_technologies, org)
    await db_session.refresh(category)
    assert (category.name, category.description, category.state, category.revision) == (
        "Owner server tools",
        "Owner description",
        "archived",
        2,
    )
    technology = await db_session.get(Technology, (org, "technology_00000000000000000000000033"))
    assert technology is not None and technology.revision == 1
    assert len(TAXONOMY_CATEGORIES) == 117


async def test_upgrade_reuses_owner_named_defaults_and_classifies_older_alias_ids(
    db_session: AsyncSession,
) -> None:
    org, area, category, custom, technology = (
        new_id(prefix) for prefix in ("organization", "area", "category", "category", "technology")
    )
    await set_tenant_scope(db_session, "*")
    db_session.add(Organization(id=org, kind="corporate", display_name="Legacy taxonomy"))
    await db_session.flush()
    db_session.add(
        TechnologyArea(
            organization_id=org,
            id=area,
            name="Owner area",
            normalized_name="owner area",
            provenance="manual",
        )
    )
    await db_session.flush()
    db_session.add_all(
        [
            TechnologyCategory(
                organization_id=org,
                id=category,
                area_id=area,
                name="Server web and API frameworks",
                normalized_name="server web and api frameworks",
                description="Owner category",
                provenance="manual",
                revision=4,
            ),
            TechnologyCategory(
                organization_id=org,
                id=custom,
                area_id=area,
                name="Owner classification",
                normalized_name="owner classification",
                provenance="manual",
            ),
            Technology(
                organization_id=org, id=technology, name="FastAPI", provenance="manual", revision=5
            ),
        ]
    )
    await db_session.flush()
    db_session.add_all(
        [
            TechnologyAlias(
                organization_id=org,
                technology_id=technology,
                name="FastAPI",
                normalized_name="fastapi",
                canonical=True,
            ),
            TechnologyClassification(
                organization_id=org, technology_id=technology, category_id=custom
            ),
        ]
    )
    await db_session.flush()
    connection = await db_session.connection()
    assert await connection.run_sync(install_technology_taxonomy, org)
    assert await connection.run_sync(classify_seed_technologies, org)
    assert not await connection.run_sync(install_technology_taxonomy, org)
    assert not await connection.run_sync(classify_seed_technologies, org)
    row = await db_session.get(TechnologyCategory, (org, category))
    assert row is not None and (row.area_id, row.description, row.revision) == (
        area,
        "Owner category",
        4,
    )
    assert set(
        await db_session.scalars(
            select(TechnologyClassification.category_id).where(
                TechnologyClassification.organization_id == org,
                TechnologyClassification.technology_id == technology,
            )
        )
    ) == {category, custom}
    row_technology = await db_session.get(Technology, (org, technology))
    assert row_technology is not None and row_technology.revision == 6
