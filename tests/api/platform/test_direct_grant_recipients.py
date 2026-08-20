"""Direct access-grant recipient identifiers (#229 and #230)."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.errors import CATEGORY_CODE, ErrorCategory
from ai_stp_api.session import issue_session
from ai_stp_api.settings import Settings
from ai_stp_foundation.ids import new_id
from ai_stp_platform.grant_identity_models import OAuthIdentityAlias
from ai_stp_platform.models import Account, CatalogMetadata, OAuthIdentity

_STABLE_ID = "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z"


async def _account_token(
    sessionmaker: async_sessionmaker[AsyncSession], *, github_username: str | None = None
) -> tuple[str, str]:
    async with sessionmaker() as db:
        account = Account(id=new_id("account"))
        db.add(account)
        await db.flush()
        if github_username is not None:
            identity = OAuthIdentity(
                account_id=account.id,
                provider="github",
                provider_subject=new_id("sub"),
                email=f"{github_username}@example.com",
                email_verified=True,
                state="linked",
            )
            db.add(identity)
            await db.flush()
            db.add(
                OAuthIdentityAlias(
                    oauth_identity_id=identity.id,
                    provider="github",
                    normalized_value=github_username,
                )
            )
        issued = await issue_session(db, account_id=account.id, device_id=None, ttl_seconds=3600)
        await db.commit()
        return account.id, issued.raw_token


async def _owned_component(
    sessionmaker: async_sessionmaker[AsyncSession], *, owner_account_id: str
) -> None:
    async with sessionmaker() as db:
        db.add(
            CatalogMetadata(
                owner_account_id=owner_account_id,
                object_kind="component",
                stable_id=_STABLE_ID,
                version="1.0",
                current_revision_id="revision_" + "0" * 64,
                visibility="private",
                lifecycle_state="draft",
                name="owned",
            )
        )
        await db.commit()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_github_username_grant_normalizes_lists_authorizes_and_revokes(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    owner_id, owner_token = await _account_token(sessionmaker)
    grantee_id, grantee_token = await _account_token(sessionmaker, github_username="octo-cat")
    await _owned_component(sessionmaker, owner_account_id=owner_id)

    created = await client.post(
        "/v1/grants/direct",
        headers=_auth(owner_token),
        json={
            "schema_version": 1,
            "object_kind": "component",
            "stable_id": _STABLE_ID,
            "major": 1,
            "recipient_kind": "github_username",
            "recipient": " @Octo-Cat ",
            "idempotency_key": "github-grant-create",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["grantee_account_id"] == grantee_id
    assert body["recipient_kind"] == "github_username"
    assert body["recipient"] == "octo-cat"

    listed = await client.get("/v1/grants", headers=_auth(grantee_token))
    assert listed.status_code == 200
    assert listed.json()["grants"][0]["recipient"] == "octo-cat"

    revoked = await client.post(
        f"/v1/grants/{body['grant_id']}/revoke",
        headers=_auth(owner_token),
        json={
            "schema_version": 1,
            "reason": "done",
            "idempotency_key": "github-revoke-case",
        },
    )
    assert revoked.status_code == 200


async def test_github_username_rejects_invalid_and_hides_unknown_recipient(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    owner_id, owner_token = await _account_token(sessionmaker)
    await _owned_component(sessionmaker, owner_account_id=owner_id)
    base = {
        "schema_version": 1,
        "object_kind": "component",
        "stable_id": _STABLE_ID,
        "major": 1,
        "recipient_kind": "github_username",
        "idempotency_key": "github-error-case",
    }
    invalid = await client.post(
        "/v1/grants/direct",
        headers=_auth(owner_token),
        json={**base, "recipient": "bad--name"},
    )
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == CATEGORY_CODE[ErrorCategory.VALIDATION]

    unknown = await client.post(
        "/v1/grants/direct",
        headers=_auth(owner_token),
        json={**base, "recipient": "unknown-user"},
    )
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == CATEGORY_CODE[ErrorCategory.NOT_FOUND]


async def test_user_id_grant_creates_lists_and_revokes_without_reinterpreting_id(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    owner_id, owner_token = await _account_token(sessionmaker)
    grantee_id, grantee_token = await _account_token(sessionmaker)
    await _owned_component(sessionmaker, owner_account_id=owner_id)
    payload = {
        "schema_version": 1,
        "object_kind": "component",
        "stable_id": _STABLE_ID,
        "major": 1,
        "recipient_kind": "user_id",
        "recipient": grantee_id,
        "idempotency_key": "user-id-grant-create",
    }

    created = await client.post("/v1/grants/direct", headers=_auth(owner_token), json=payload)
    assert created.status_code == 201
    body = created.json()
    assert body["grantee_account_id"] == grantee_id
    assert body["recipient_kind"] == "user_id"
    assert body["recipient"] == grantee_id

    listed = await client.get("/v1/grants", headers=_auth(grantee_token))
    assert listed.status_code == 200
    assert listed.json()["grants"][0]["grant_id"] == body["grant_id"]

    revoked = await client.post(
        f"/v1/grants/{body['grant_id']}/revoke",
        headers=_auth(owner_token),
        json={
            "schema_version": 1,
            "reason": "done",
            "idempotency_key": "user-id-grant-revoke",
        },
    )
    assert revoked.status_code == 200


async def test_user_id_rejects_malformed_and_hides_unknown_account(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    owner_id, owner_token = await _account_token(sessionmaker)
    await _owned_component(sessionmaker, owner_account_id=owner_id)
    base = {
        "schema_version": 1,
        "object_kind": "component",
        "stable_id": _STABLE_ID,
        "major": 1,
        "recipient_kind": "user_id",
        "idempotency_key": "user-id-error-case",
    }
    malformed = await client.post(
        "/v1/grants/direct",
        headers=_auth(owner_token),
        json={**base, "recipient": "OctoCat"},
    )
    assert malformed.status_code == 400
    assert malformed.json()["error"]["code"] == CATEGORY_CODE[ErrorCategory.VALIDATION]

    unknown = await client.post(
        "/v1/grants/direct",
        headers=_auth(owner_token),
        json={**base, "recipient": "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z"},
    )
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == CATEGORY_CODE[ErrorCategory.NOT_FOUND]
