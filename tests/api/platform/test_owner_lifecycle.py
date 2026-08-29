"""An author deprecates their own version, and nothing else changes (`REQ-730`).

`deprecated` was declared in `PublicLifecycle`, in `LifecycleState`, in
`PUBLIC_LIFECYCLES` and in this spec's state vocabulary, offered by a CLI hint,
and written by nothing: the staff route accepts `block`, `hide` and `restore`,
and every owner version route was a read. Two successive plans carried
"deprecate the old corpus" as pending work against a verb that did not exist.

The author holds it because deprecation is a statement about the object's own
future rather than about its acceptability — moderation is closed to staff by
`SPEC-026` `REQ-2617` — and because the evidence that motivates it reaches the
author as a proposal (`SPEC-044`).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.session import issue_session
from ai_stp_api.settings import Settings
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account, CatalogMetadata

pytestmark = pytest.mark.platform

KEY = "idempotency-key-0123456789"


async def _account(sessionmaker: async_sessionmaker[AsyncSession]) -> tuple[str, str]:
    async with sessionmaker() as db:
        account = Account(id=new_id("account"))
        db.add(account)
        await db.flush()
        issued = await issue_session(db, account_id=account.id, device_id=None, ttl_seconds=3600)
        await db.commit()
        return account.id, issued.raw_token


async def _version(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    owner_id: str,
    lifecycle: str = "active",
) -> str:
    stable_id = new_id("component")
    async with sessionmaker() as db:
        db.add(
            CatalogMetadata(
                owner_account_id=owner_id,
                object_kind="component",
                stable_id=stable_id,
                version="1.0",
                current_revision_id="revision_" + "0" * 64,
                visibility="public",
                lifecycle_state=lifecycle,
                name="component-fixture",
                passport_document={"description": "Passport description"},
            )
        )
        await db.commit()
    return stable_id


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _body(action: str) -> dict[str, object]:
    return {"schema_version": 1, "action": action, "reason": "superseded", "idempotency_key": KEY}


async def _state(sessionmaker: async_sessionmaker[AsyncSession], stable_id: str) -> str:
    async with sessionmaker() as db:
        row = await db.scalar(select(CatalogMetadata).where(CatalogMetadata.stable_id == stable_id))
        assert row is not None
        return str(row.lifecycle_state)


@pytest.mark.asyncio
async def test_an_author_deprecates_their_own_version_and_takes_it_back(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    owner_id, token = await _account(sessionmaker)
    stable_id = await _version(sessionmaker, owner_id=owner_id)
    path = f"/v1/owner/objects/component/{stable_id}/versions/1.0/lifecycle"

    answer = await client.post(path, json=_body("deprecate"), headers=_auth(token))
    assert answer.status_code == 200, answer.text
    assert answer.json()["lifecycle"] == "deprecated"
    assert answer.json()["applied"] is True
    assert await _state(sessionmaker, stable_id) == "deprecated"

    back = await client.post(path, json=_body("undeprecate"), headers=_auth(token))
    assert back.status_code == 200, back.text
    assert back.json()["lifecycle"] == "active"
    assert await _state(sessionmaker, stable_id) == "active"


@pytest.mark.asyncio
async def test_repeating_the_transition_is_a_replay_not_a_conflict(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    """The idempotency key exists to make this safe, so it must be."""
    client, sessionmaker, _settings = db_api_client
    owner_id, token = await _account(sessionmaker)
    stable_id = await _version(sessionmaker, owner_id=owner_id)
    path = f"/v1/owner/objects/component/{stable_id}/versions/1.0/lifecycle"

    first = await client.post(path, json=_body("deprecate"), headers=_auth(token))
    second = await client.post(path, json=_body("deprecate"), headers=_auth(token))
    assert first.json()["applied"] is True
    assert second.status_code == 200
    assert second.json()["applied"] is False
    assert second.json()["lifecycle"] == "deprecated"


@pytest.mark.asyncio
@pytest.mark.parametrize("moderated", ["blocked", "hidden"])
async def test_an_author_cannot_leave_a_moderation_state(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
    moderated: str,
) -> None:
    """Undoing a staff decision is a different authority, and it is refused."""
    client, sessionmaker, _settings = db_api_client
    owner_id, token = await _account(sessionmaker)
    stable_id = await _version(sessionmaker, owner_id=owner_id, lifecycle=moderated)
    path = f"/v1/owner/objects/component/{stable_id}/versions/1.0/lifecycle"

    answer = await client.post(path, json=_body("undeprecate"), headers=_auth(token))
    assert answer.status_code == 409, answer.text
    assert await _state(sessionmaker, stable_id) == moderated


@pytest.mark.asyncio
async def test_another_account_cannot_deprecate_somebody_elses_version(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    owner_id, _owner_token = await _account(sessionmaker)
    _stranger_id, stranger_token = await _account(sessionmaker)
    stable_id = await _version(sessionmaker, owner_id=owner_id)

    answer = await client.post(
        f"/v1/owner/objects/component/{stable_id}/versions/1.0/lifecycle",
        json=_body("deprecate"),
        headers=_auth(stranger_token),
    )
    assert answer.status_code == 404, answer.text
    assert await _state(sessionmaker, stable_id) == "active"


@pytest.mark.asyncio
async def test_a_deprecated_version_is_still_readable(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    """The clause that makes this a signal rather than a restriction.

    A published `X.Y` is immutable, so a lifecycle mark that changed what
    somebody already depends on would be an edit by another name. Anyone who
    pinned this version keeps it working.
    """
    client, sessionmaker, _settings = db_api_client
    owner_id, token = await _account(sessionmaker)
    stable_id = await _version(sessionmaker, owner_id=owner_id)
    await client.post(
        f"/v1/owner/objects/component/{stable_id}/versions/1.0/lifecycle",
        json=_body("deprecate"),
        headers=_auth(token),
    )

    public = await client.get(f"/v1/catalog/components/{stable_id}/versions/1.0")

    # The control: the same fixture while still `active`. Without it a 404 here
    # cannot tell "deprecated hides it" from "this fixture was never readable".
    control_id = await _version(sessionmaker, owner_id=owner_id)
    control = await client.get(f"/v1/catalog/components/{control_id}/versions/1.0")

    assert control.status_code == public.status_code, (
        f"active={control.status_code} deprecated={public.status_code}: "
        "deprecating changed public readability"
    )
