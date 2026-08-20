"""On-demand GitHub metadata and setup context budget (SPEC-049)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.api.platform.conftest import make_settings

from ai_stp_api.app import create_app
from ai_stp_api.session import issue_session
from ai_stp_api.settings import Settings
from ai_stp_contracts.catalog import GitHubMetadata
from ai_stp_contracts.context_estimator import EstimatorInput, estimate_context, estimator_for
from ai_stp_contracts.impact import ExactCoordinate
from ai_stp_foundation.ids import new_id
from ai_stp_platform.catalog_seed import (
    FIXTURE_COMPONENT_ID,
    FIXTURE_SETUP_ID,
    INCIDENT_SUBAGENT_ARTIFACT,
    SEED_A1_INCIDENT_AGENT_ID,
    SEED_A1_INCIDENT_SETUP_ID,
    load_first_party_seed,
)
from ai_stp_platform.github_metadata import unavailable_metadata
from ai_stp_platform.models import Account, CatalogMetadata
from ai_stp_platform.storage import ImmutableObjectStore

pytestmark = pytest.mark.platform


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def seeded_client(
    migrated_database_url: str,
    tmp_path_factory: pytest.TempPathFactory,
) -> AsyncIterator[AsyncClient]:
    log_dir = tmp_path_factory.mktemp("catalog-on-demand")
    settings = make_settings(log_dir, database_url=migrated_database_url)
    engine = create_async_engine(migrated_database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        store = ImmutableObjectStore(settings=settings.storage, client=app.state.object_client)
        async with sessionmaker() as session:
            await load_first_party_seed(session, store=store)
            await session.commit()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    await engine.dispose()


@pytest.mark.asyncio
async def test_catalog_list_does_not_call_github(
    seeded_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_fetch(*_args: object, **_kwargs: object) -> GitHubMetadata:
        raise AssertionError("catalog list must not call GitHub")

    monkeypatch.setattr(
        "ai_stp_api.slices.catalog.service.fetch_github_metadata",
        fail_fetch,
    )
    response = await seeded_client.get(
        "/v1/catalog/components",
        params={"page_size": "20", "include_experimental": "true"},
    )
    assert response.status_code == 200
    assert "github_archive" not in response.text


@pytest.mark.asyncio
async def test_github_metadata_is_unavailable_without_source(
    seeded_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = {"n": 0}

    async def fetch(*_args: object, **_kwargs: object) -> GitHubMetadata:
        called["n"] += 1
        return unavailable_metadata()

    monkeypatch.setattr("ai_stp_api.slices.catalog.service.fetch_github_metadata", fetch)
    response = await seeded_client.get(
        f"/v1/catalog/components/{FIXTURE_COMPONENT_ID}/versions/1.2/github-metadata"
    )
    assert response.status_code == 200
    assert response.json() == {"schema_version": 1, "stars": None, "archived": None}
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_github_metadata_makes_one_bounded_request_for_detail(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, sessionmaker, _settings = db_api_client
    stable_id = new_id("component")
    async with sessionmaker() as db:
        account = Account(id=new_id("account"))
        db.add(account)
        db.add(
            CatalogMetadata(
                owner_account_id=account.id,
                object_kind="component",
                stable_id=stable_id,
                version="1.0",
                current_revision_id="revision_" + "0" * 64,
                visibility="public",
                lifecycle_state="active",
                name="tool",
                passport_digest="sha256:" + "a" * 64,
                passport_document={"source": {"repository": "https://github.com/acme/tool"}},
                published_at=datetime(2026, 8, 16, tzinfo=UTC),
                trust_lane="experimental",
            )
        )
        await db.commit()

    seen: list[str] = []

    async def fetch(repository: str, *, client: httpx.AsyncClient) -> GitHubMetadata:
        del client
        seen.append(repository)
        return GitHubMetadata(stars=9, archived=True)

    monkeypatch.setattr("ai_stp_api.slices.catalog.service.fetch_github_metadata", fetch)
    response = await client.get(f"/v1/catalog/components/{stable_id}/versions/1.0/github-metadata")
    assert response.status_code == 200
    assert response.json()["stars"] == 9
    assert response.json()["archived"] is True
    assert seen == ["https://github.com/acme/tool"]


@pytest.mark.asyncio
async def test_private_github_metadata_and_budget_are_owner_only(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    owner_id, owner_token = await _account(sessionmaker)
    _other_id, other_token = await _account(sessionmaker)
    setup_id = new_id("setup")
    async with sessionmaker() as db:
        db.add(
            CatalogMetadata(
                owner_account_id=owner_id,
                object_kind="setup",
                stable_id=setup_id,
                version="1.0",
                current_revision_id="revision_" + "1" * 64,
                visibility="private",
                lifecycle_state="draft",
                name="secret",
                passport_digest="sha256:" + "b" * 64,
                passport_document={"kind": "setup", "components": []},
            )
        )
        await db.commit()

    missing = await client.get(f"/v1/catalog/setups/{setup_id}/versions/1.0/github-metadata")
    outsider = await client.get(
        f"/v1/catalog/setups/{setup_id}/versions/1.0/github-metadata",
        headers=_auth(other_token),
    )
    owner = await client.get(
        f"/v1/catalog/setups/{setup_id}/versions/1.0/github-metadata",
        headers=_auth(owner_token),
    )
    assert missing.status_code == 404
    assert outsider.status_code == 404
    assert owner.status_code == 200


@pytest.mark.asyncio
async def test_public_context_budget_does_not_include_account_inventory(
    seeded_client: AsyncClient,
) -> None:
    response = await seeded_client.get(
        f"/v1/catalog/setups/{FIXTURE_SETUP_ID}/versions/1.0/context-budget"
    )
    assert response.status_code in {200, 400}
    body = response.json()
    dumped = str(body)
    assert "devices" not in dumped
    assert "installed_targets" not in dumped
    assert "projects" not in dumped
    if response.status_code == 200:
        assert body["schema_version"] == 1
        assert body["coordinate"]["stable_id"] == FIXTURE_SETUP_ID
    else:
        assert body["error"]["code"] == "AI_STP_VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_incident_setup_budget_reports_conditional_subagent_tokens(
    seeded_client: AsyncClient,
) -> None:
    estimator = estimator_for("ai-stp:utf8-bytes/1")
    assert estimator is not None
    expected = estimate_context(
        [
            EstimatorInput(
                coordinate=ExactCoordinate(
                    stable_id=SEED_A1_INCIDENT_AGENT_ID,
                    version="1.0",
                    passport_digest="sha256:" + "a" * 64,
                ),
                component_type="agent",
                files=(INCIDENT_SUBAGENT_ARTIFACT,),
            )
        ],
        estimator,
    )
    listed = await seeded_client.get(
        "/v1/catalog/components",
        params={"page_size": "50", "include_experimental": "true"},
    )
    assert listed.status_code == 200
    names = [item["latest_name"] for item in listed.json()["experimental"]]
    assert "firstparty-incident-subagent" in names
    response = await seeded_client.get(
        f"/v1/catalog/setups/{SEED_A1_INCIDENT_SETUP_ID}/versions/1.0/context-budget"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["always_tokens"] == 0
    assert body["conditional_tokens"] == expected.conditional_tokens
    assert body["total_tokens"] == expected.conditional_tokens
    assert body["components"][0]["component"]["stable_id"] == SEED_A1_INCIDENT_AGENT_ID
    assert body["components"][0]["loading"] == "conditional"
    assert body["components"][0]["tokens"] == expected.components[0].tokens


async def _account(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> tuple[str, str]:
    async with sessionmaker() as db:
        account = Account(id=new_id("account"))
        db.add(account)
        await db.flush()
        issued = await issue_session(db, account_id=account.id, device_id=None, ttl_seconds=3600)
        await db.commit()
        return account.id, issued.raw_token
