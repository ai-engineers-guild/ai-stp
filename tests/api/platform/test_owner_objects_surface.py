"""The owner "my objects" surface and the boundary that keeps it private.

Every read here filters on the owning account. That filter is the whole
authorization story for the surface: there is no separate permission check to
fall back on, so a regression turns one owner's catalog into everyone's. These
tests pin the boundary from the outside, through the ASGI app, rather than
trusting the query.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.session import issue_session
from ai_stp_api.settings import Settings
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account, CatalogMetadata

pytestmark = pytest.mark.platform


async def _account_with_session(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> tuple[str, str]:
    async with sessionmaker() as db:
        account = Account(id=new_id("account"))
        db.add(account)
        await db.flush()
        issued = await issue_session(db, account_id=account.id, device_id=None, ttl_seconds=3600)
        await db.commit()
        return account.id, issued.raw_token


async def _own_version(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    owner_id: str,
    object_kind: str = "component",
    stable_id: str | None = None,
    version: str = "1.0",
    name: str | None = None,
    with_digest: bool = False,
    artifact_digest_only: bool = False,
) -> str:
    stable_id = stable_id or new_id(object_kind)
    digest = "sha256:" + "a" * 64
    document: dict[str, object] = {"description": "Passport description"}
    if artifact_digest_only:
        document["artifact"] = {"digest": digest, "size_bytes": 11}
    async with sessionmaker() as db:
        db.add(
            CatalogMetadata(
                owner_account_id=owner_id,
                object_kind=object_kind,
                stable_id=stable_id,
                version=version,
                current_revision_id="revision_" + "0" * 64,
                visibility="public",
                lifecycle_state="active",
                name=name or f"{object_kind}-fixture",
                passport_digest=digest if with_digest else None,
                passport_document=document,
            )
        )
        await db.commit()
    return stable_id


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_the_list_shows_one_row_per_object_not_per_version(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    owner_id, token = await _account_with_session(sessionmaker)
    stable_id = await _own_version(sessionmaker, owner_id=owner_id, version="1.0")
    await _own_version(sessionmaker, owner_id=owner_id, stable_id=stable_id, version="1.1")

    response = await client.get("/v1/owner/objects", headers=_auth(token))

    assert response.status_code == 200
    items = response.json()["items"]
    mine = [item for item in items if item["stable_id"] == stable_id]
    assert len(mine) == 1, "two versions of one object must collapse into one summary"
    assert mine[0]["object_kind"] == "component"


@pytest.mark.asyncio
async def test_the_list_never_reaches_another_accounts_objects(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    _mine_id, my_token = await _account_with_session(sessionmaker)
    other_id, _other_token = await _account_with_session(sessionmaker)
    foreign = await _own_version(sessionmaker, owner_id=other_id, name="not-yours")

    response = await client.get("/v1/owner/objects", headers=_auth(my_token))

    assert response.status_code == 200
    assert all(item["stable_id"] != foreign for item in response.json()["items"])


@pytest.mark.asyncio
async def test_the_list_filters_by_object_kind(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    owner_id, token = await _account_with_session(sessionmaker)
    component = await _own_version(sessionmaker, owner_id=owner_id, object_kind="component")
    setup = await _own_version(sessionmaker, owner_id=owner_id, object_kind="setup")

    response = await client.get("/v1/owner/objects?object_kind=setup", headers=_auth(token))

    assert response.status_code == 200
    ids = {item["stable_id"] for item in response.json()["items"]}
    assert setup in ids
    assert component not in ids


@pytest.mark.asyncio
async def test_an_owner_reads_their_own_object_and_version(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    owner_id, token = await _account_with_session(sessionmaker)
    stable_id = await _own_version(sessionmaker, owner_id=owner_id, version="1.0")

    detail = await client.get(f"/v1/owner/objects/component/{stable_id}", headers=_auth(token))
    assert detail.status_code == 200
    assert detail.json()["stable_id"] == stable_id

    version = await client.get(
        f"/v1/owner/objects/component/{stable_id}/versions/1.0", headers=_auth(token)
    )
    assert version.status_code == 200
    assert version.json()["version"] == "1.0"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path_suffix",
    ["", "/versions/1.0"],
    ids=["object", "version"],
)
async def test_another_accounts_object_is_not_found_rather_than_forbidden(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
    path_suffix: str,
) -> None:
    """A miss, not a refusal: a refusal would confirm the object exists.

    The owner surface is not a permission gate over a shared catalog — an object
    the caller does not own is simply not part of their surface, and saying
    "forbidden" would leak that someone else owns that exact identifier.
    """
    client, sessionmaker, _settings = db_api_client
    _mine_id, my_token = await _account_with_session(sessionmaker)
    other_id, _other_token = await _account_with_session(sessionmaker)
    foreign = await _own_version(sessionmaker, owner_id=other_id)

    response = await client.get(
        f"/v1/owner/objects/component/{foreign}{path_suffix}", headers=_auth(my_token)
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_an_unknown_version_of_an_owned_object_is_not_found(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    owner_id, token = await _account_with_session(sessionmaker)
    stable_id = await _own_version(sessionmaker, owner_id=owner_id, version="1.0")

    response = await client.get(
        f"/v1/owner/objects/component/{stable_id}/versions/9.9", headers=_auth(token)
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_publication_cannot_be_started_on_someone_elses_version(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    """The write side of the same boundary, checked separately from the reads."""
    client, sessionmaker, _settings = db_api_client
    _mine_id, my_token = await _account_with_session(sessionmaker)
    other_id, _other_token = await _account_with_session(sessionmaker)
    foreign = await _own_version(sessionmaker, owner_id=other_id, with_digest=True)

    response = await client.post(
        f"/v1/owner/objects/component/{foreign}/versions/1.0/publication-plans",
        headers=_auth(my_token),
        json={
            "schema_version": 1,
            "device_id": new_id("device"),
            "idempotency_key": new_id("device") + "-publish",
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_the_owner_surface_cannot_bypass_the_publication_validator(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    """Starting a plan from stored state still validates the stored passport.

    This route builds the plan server-side from the version's own passport
    instead of accepting one from the browser, which makes it the obvious place
    for an incomplete passport to slip past the canonical validator. It does
    not: the same barrier that #254 added on create rejects it here too, and a
    plan is never created for a passport that the public projection would later
    refuse to read.
    """
    client, sessionmaker, _settings = db_api_client
    owner_id, token = await _account_with_session(sessionmaker)
    stable_id = await _own_version(sessionmaker, owner_id=owner_id, with_digest=True)

    response = await client.post(
        f"/v1/owner/objects/component/{stable_id}/versions/1.0/publication-plans",
        headers=_auth(token),
        json={
            "schema_version": 1,
            "device_id": new_id("device"),
            "idempotency_key": new_id("device") + "-publish",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "AI_STP_VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_a_version_without_a_content_digest_cannot_start_publication(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    """No digest means nothing exact to publish, and that is a refusal, not a plan."""
    client, sessionmaker, _settings = db_api_client
    owner_id, token = await _account_with_session(sessionmaker)
    stable_id = await _own_version(sessionmaker, owner_id=owner_id, with_digest=False)

    response = await client.post(
        f"/v1/owner/objects/component/{stable_id}/versions/1.0/publication-plans",
        headers=_auth(token),
        json={
            "schema_version": 1,
            "device_id": new_id("device"),
            "idempotency_key": new_id("device") + "-publish",
        },
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_presentation_falls_back_to_the_passport_description(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    """An object that has never been given a bio still reads as something.

    The mutable presentation bio is optional; until an owner writes one the
    surface shows the passport's immutable description rather than an empty
    card, and the two must not be confused for each other.
    """
    client, sessionmaker, _settings = db_api_client
    owner_id, token = await _account_with_session(sessionmaker)
    stable_id = await _own_version(sessionmaker, owner_id=owner_id)

    response = await client.get(
        f"/v1/owner/objects/component/{stable_id}/presentation", headers=_auth(token)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["stable_id"] == stable_id
    assert body["bio"] == "Passport description"
    assert body["media"] == []


@pytest.mark.asyncio
async def test_presentation_of_another_accounts_component_is_not_found(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    _mine_id, my_token = await _account_with_session(sessionmaker)
    other_id, _other_token = await _account_with_session(sessionmaker)
    foreign = await _own_version(sessionmaker, owner_id=other_id)

    response = await client.get(
        f"/v1/owner/objects/component/{foreign}/presentation", headers=_auth(my_token)
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_a_missing_digest_column_falls_back_to_the_declared_artifact_digest(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    """Seeded and drafted rows predate the digest column and must still publish.

    The fallback reads the artifact digest out of the stored passport. It is a
    real path, not a defensive branch: the first-party seed corpus reaches
    publication through it, and losing it would make those objects unpublishable
    with a message about a missing digest they visibly have.
    """
    client, sessionmaker, _settings = db_api_client
    owner_id, token = await _account_with_session(sessionmaker)
    stable_id = await _own_version(sessionmaker, owner_id=owner_id, artifact_digest_only=True)

    response = await client.post(
        f"/v1/owner/objects/component/{stable_id}/versions/1.0/publication-plans",
        headers=_auth(token),
        json={
            "schema_version": 1,
            "device_id": new_id("device"),
            "idempotency_key": new_id("device") + "-publish",
        },
    )

    # It reaches the passport validator rather than stopping at "no digest",
    # which is the whole point of the fallback.
    assert response.status_code == 400
    body = response.json()["error"]
    assert body["code"] == "AI_STP_VALIDATION_ERROR"
    assert "digest" not in body.get("message", "").lower()
