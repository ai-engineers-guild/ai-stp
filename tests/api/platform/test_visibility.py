"""Owner visibility changes preserve exact published identities in PostgreSQL."""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.support.catalog_seed import (
    FIXTURE_COMPONENT_ID,
    SEED_OWNER_ACCOUNT_ID,
    load_fixture_seed,
)

from ai_stp_api.errors import CATEGORY_CODE, CATEGORY_STATUS, ErrorCategory
from ai_stp_api.session import issue_session
from ai_stp_api.settings import Settings
from ai_stp_contracts.private_access import CliPrivateVersionResponse, VisibilityPlanResponse
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account, CatalogMetadata, Device

pytestmark = pytest.mark.platform
BASE = "/v1/access/visibility/plans"


async def test_owner_closes_and_reopens_exact_version_without_resealing(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessions, _settings = db_api_client
    async with sessions() as db:
        await load_fixture_seed(db)
        target = await db.scalar(
            select(CatalogMetadata)
            .where(
                CatalogMetadata.stable_id == FIXTURE_COMPONENT_ID,
                CatalogMetadata.published_at.is_not(None),
            )
            .order_by(CatalogMetadata.version.desc())
        )
        assert target is not None
        original = dict(target.passport_document or {})
        digest = target.passport_digest
        owner_device = Device(
            id=new_id("device"),
            account_id=SEED_OWNER_ACCOUNT_ID,
            public_key="dGVzdC1wdWJsaWMta2V5LXB1Ymxpc2g=",
            state="active",
        )
        stranger = Account(id=new_id("account"))
        db.add_all([owner_device, stranger])
        await db.flush()
        issued = await issue_session(
            db, account_id=SEED_OWNER_ACCOUNT_ID, device_id=owner_device.id, ttl_seconds=3600
        )
        outsider = await issue_session(db, account_id=stranger.id, device_id=None, ttl_seconds=3600)
        await db.commit()
    headers = {"Authorization": f"Bearer {issued.raw_token}"}
    outsider_headers = {"Authorization": f"Bearer {outsider.raw_token}"}
    coordinates: dict[str, Any] = {
        "object_kind": target.object_kind,
        "stable_id": target.stable_id,
        "version": target.version,
        "device_id": owner_device.id,
    }
    version_path = f"/v1/catalog/components/{target.stable_id}/versions/{target.version}"
    for visibility in ("private", "public"):
        body = {**coordinates, "visibility": visibility, "idempotency_key": new_id("operation")}
        created = await client.post(BASE, headers=headers, json=body)
        assert created.status_code == 201, created.text
        planned = VisibilityPlanResponse.model_validate(created.json())
        repeated = await client.post(BASE, headers=headers, json=body)
        assert repeated.json() == created.json()
        conflict = await client.post(
            BASE,
            headers=headers,
            json={**body, "visibility": "public" if visibility == "private" else "private"},
        )
        assert conflict.status_code == CATEGORY_STATUS[ErrorCategory.CONFLICT]
        hidden = await client.get(f"{BASE}/{planned.plan_id}", headers=outsider_headers)
        assert hidden.status_code == CATEGORY_STATUS[ErrorCategory.NOT_FOUND]
        assert hidden.json()["error"]["code"] == CATEGORY_CODE[ErrorCategory.NOT_FOUND]
        confirmation = {
            "plan_hash": planned.plan_hash,
            "confirmed": True,
            "idempotency_key": new_id("operation"),
        }
        wrong_hash = await client.post(
            f"{BASE}/{planned.plan_id}/confirm",
            headers=headers,
            json={**confirmation, "plan_hash": "sha256:" + "0" * 64},
        )
        assert wrong_hash.status_code == CATEGORY_STATUS[ErrorCategory.CONFLICT]
        before = await client.get(f"{BASE}/{planned.plan_id}", headers=headers)
        assert before.json()["state"] == "planned"
        changed = await client.post(
            f"{BASE}/{planned.plan_id}/confirm", headers=headers, json=confirmation
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["state"] == "applied"
        replay = await client.post(
            f"{BASE}/{planned.plan_id}/confirm", headers=headers, json=confirmation
        )
        assert replay.json() == changed.json()
        async with sessions() as db:
            observed = await db.get(CatalogMetadata, target.id)
            assert observed is not None
            assert observed.passport_document == original
            assert observed.passport_digest == digest
            assert observed.visibility == visibility
        public = await client.get(version_path)
        if visibility == "private":
            assert public.status_code == CATEGORY_STATUS[ErrorCategory.NOT_FOUND]
            private = await client.get(f"{version_path}/private", headers=headers)
            assert private.status_code == 200, private.text
            response = CliPrivateVersionResponse.model_validate(private.json())
            assert response.passport == original
            assert response.passport_digest == digest
        else:
            assert public.status_code == 200, public.text
            assert public.json()["passport_digest"] == digest

    # Two reviewed plans for the same old visibility cannot silently overwrite
    # an intervening decision; the stale result is durable and effect-free.
    pending: list[VisibilityPlanResponse] = []
    for _ in range(2):
        planned_response = await client.post(
            BASE,
            headers=headers,
            json={
                **coordinates,
                "visibility": "private",
                "idempotency_key": new_id("operation"),
            },
        )
        assert planned_response.status_code == 201
        pending.append(VisibilityPlanResponse.model_validate(planned_response.json()))
    for index, planned in enumerate(pending):
        result = await client.post(
            f"{BASE}/{planned.plan_id}/confirm",
            headers=headers,
            json={
                "plan_hash": planned.plan_hash,
                "confirmed": True,
                "idempotency_key": new_id("operation"),
            },
        )
        assert result.status_code == 200
        assert result.json()["state"] == ("applied" if index == 0 else "refused")
    async with sessions() as db:
        observed = await db.get(CatalogMetadata, target.id)
        assert observed is not None
        assert observed.passport_document == original
        assert observed.passport_digest == digest
