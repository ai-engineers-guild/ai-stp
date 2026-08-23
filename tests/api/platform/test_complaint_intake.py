"""Public complaint intake stores fields and honours configured limits."""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.errors import CATEGORY_CODE, ErrorCategory
from ai_stp_api.session import issue_session
from ai_stp_api.settings import Settings
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account, ComplaintIntake

pytestmark = pytest.mark.platform

_MESSAGE = "The published skill fails its documented install path."


def _body(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "target_kind": "component",
        "target": "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z@1.2",
        "sender_name": "Ada",
        "reply_email": "reporter@example.com",
        "subject": "broken-skill",
        "message": _MESSAGE,
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_complaint_persists_anonymous_and_signed_in_fields(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    anonymous = await client.post("/v1/complaints", json=_body())
    assert anonymous.status_code == 201
    payload = anonymous.json()
    assert payload["accepted"] is True
    complaint_id = payload["complaint_id"]
    assert complaint_id.startswith("complaint_")

    async with sessionmaker() as db:
        row = await db.get(ComplaintIntake, complaint_id)
        assert row is not None
        assert row.submitter_account_id is None
        assert row.submitter_key == "email:reporter@example.com"
        assert row.target_kind == "component"
        assert row.target == "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z@1.2"
        assert row.subject == "broken-skill"
        assert row.message == _MESSAGE
        assert row.reply_email == "reporter@example.com"
        assert row.sender_name == "Ada"
        account = Account(id=new_id("account"))
        db.add(account)
        await db.flush()
        session = await issue_session(db, account_id=account.id, device_id=None, ttl_seconds=3600)
        account_id = account.id
        await db.commit()

    signed = await client.post(
        "/v1/complaints",
        json=_body(
            target_kind="author",
            target=account_id,
            reply_email="owner@example.com",
            subject="author-conduct",
        ),
        headers={"Authorization": f"Bearer {session.raw_token}"},
    )
    assert signed.status_code == 201
    async with sessionmaker() as db:
        signed_row = await db.get(ComplaintIntake, signed.json()["complaint_id"])
        assert signed_row is not None
        assert signed_row.submitter_account_id == account_id
        assert signed_row.submitter_key == account_id
        assert signed_row.target_kind == "author"
        assert signed_row.target == account_id

    other = await client.post(
        "/v1/complaints",
        json=_body(
            target_kind="other",
            target="site",
            reply_email="third@example.com",
            subject="general-question",
        ),
    )
    assert other.status_code == 201


@pytest.mark.asyncio
async def test_complaint_limits_come_from_handler_settings(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, settings = db_api_client
    limits = settings.complaint
    rate_code = CATEGORY_CODE[ErrorCategory.RATE_LIMITED]
    first = await client.post("/v1/complaints", json=_body())
    assert first.status_code == 201
    extras = 0
    for index in range(limits.submitter_limit):
        extra = await client.post("/v1/complaints", json=_body(subject=f"repeat-{index}"))
        extras += 1
        if extra.status_code != 201:
            assert extra.status_code == 429
            assert extra.json()["error"]["code"] == rate_code
            break
    else:
        blocked = await client.post("/v1/complaints", json=_body(subject="over-submitter"))
        assert blocked.status_code == 429
        assert blocked.json()["error"]["code"] == rate_code
        extras += 1
    assert extras >= 1

    accepted_targets = 0
    for index in range(limits.target_limit + 1):
        response = await client.post(
            "/v1/complaints",
            json=_body(
                target="component_target_one",
                reply_email=f"user{index}@example.com",
                subject=f"target-{index}",
            ),
        )
        if response.status_code == 201:
            accepted_targets += 1
            continue
        assert response.status_code == 429
        assert response.json()["error"]["code"] == rate_code
        break
    else:
        raise AssertionError("target limit did not reject the extra complaint")
    assert accepted_targets == limits.target_limit
    async with sessionmaker() as db:
        stored = await db.scalar(select(ComplaintIntake.id).limit(1))
        assert stored is not None


@pytest.mark.asyncio
async def test_complaint_submitter_limit_is_atomic_for_concurrent_requests(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, _sessionmaker, settings = db_api_client
    limit = settings.complaint.submitter_limit
    responses = await asyncio.gather(
        *(
            client.post("/v1/complaints", json=_body(subject=f"parallel-{index}"))
            for index in range(limit + 1)
        )
    )

    assert sum(response.status_code == 201 for response in responses) == limit
    assert sum(response.status_code == 429 for response in responses) == 1
    rejected = next(response for response in responses if response.status_code == 429)
    assert rejected.json()["error"]["code"] == CATEGORY_CODE[ErrorCategory.RATE_LIMITED]
