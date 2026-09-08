"""Setup family mutations and recast publication effects (SPEC-065)."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.support.catalog_seed import seed_corpus

from ai_stp_api.session import issue_session
from ai_stp_api.settings import Settings
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import new_id
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_passports.versions import SetupVersionPassport
from ai_stp_platform.catalog_families import apply_recast_family_effect, family_for_setup
from ai_stp_platform.catalog_projection import PASSPORT_DIGEST_DOMAIN
from ai_stp_platform.models import Account, AuditEvent, CatalogMetadata, SetupFamilyRevision

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


async def _own_setup(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    owner_id: str,
    harness_id: str,
    stable_id: str | None = None,
    ported_from: dict[str, str] | None = None,
    related_setup_ids: list[str] | None = None,
) -> tuple[str, str]:
    stable_id = stable_id or new_id("setup")
    document = deepcopy(next(passport for kind, passport, *_ in seed_corpus() if kind == "setup"))
    document.update(
        stable_id=stable_id,
        version="1.0",
        owner_id=owner_id,
        name=f"{harness_id}-setup",
        harness_id=harness_id,
        ported_from=ported_from,
        related_setup_ids=list(related_setup_ids or []),
    )
    document.pop("revision_id", None)
    document["revision_id"] = derive_revision_id(document)
    document = SetupVersionPassport.model_validate(document).model_dump(mode="json")
    digest = digest_canonical(PASSPORT_DIGEST_DOMAIN, document)  # type: ignore[arg-type]
    async with sessionmaker() as db:
        db.add(
            CatalogMetadata(
                owner_account_id=owner_id,
                object_kind="setup",
                stable_id=stable_id,
                version="1.0",
                current_revision_id=str(document["revision_id"]),
                visibility="public",
                lifecycle_state="active",
                name=f"{harness_id}-setup",
                published_at=datetime(2026, 9, 6, tzinfo=UTC),
                trust_lane="experimental",
                passport_digest=digest,
                passport_document=document,
            )
        )
        await db.commit()
    return stable_id, digest


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_owner_family_create_keeps_setup_identity(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    owner_id, token = await _account_with_session(sessionmaker)
    claude_id, claude_digest = await _own_setup(
        sessionmaker, owner_id=owner_id, harness_id="claude-code"
    )
    codex_id, _codex_digest = await _own_setup(sessionmaker, owner_id=owner_id, harness_id="codex")

    created = await client.post(
        "/v1/owner/setup-families",
        headers=_auth(token),
        json={
            "schema_version": 1,
            "name": "pair",
            "baseline": {
                "stable_id": claude_id,
                "version": "1.0",
                "passport_digest": claude_digest,
            },
            "members": [claude_id, codex_id],
            "expected_revision": 0,
            "idempotency_key": "owner-create-family-01",
            "reason": "owner_create",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["created_from"] == "owner"
    assert {item["stable_id"] for item in body["members"]} == {claude_id, codex_id}
    assert {item["name"] for item in body["members"]} == {"claude-code-setup", "codex-setup"}
    assert "install" not in created.text.lower()

    async with sessionmaker() as db:
        claude = (
            await db.execute(
                select(CatalogMetadata).where(
                    CatalogMetadata.stable_id == claude_id, CatalogMetadata.version == "1.0"
                )
            )
        ).scalar_one()
        assert claude.lifecycle_state == "active"
        assert claude.version == "1.0"
        assert claude.likes_count == 0
        audits = list(
            (
                await db.execute(
                    select(AuditEvent).where(AuditEvent.action == "owner.family_created")
                )
            )
            .scalars()
            .all()
        )
        assert audits


@pytest.mark.asyncio
async def test_recast_publication_creates_one_family_for_the_pair(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    owner_id, token = await _account_with_session(sessionmaker)
    source_id, source_digest = await _own_setup(
        sessionmaker, owner_id=owner_id, harness_id="claude-code"
    )
    target_id, _target_digest = await _own_setup(
        sessionmaker,
        owner_id=owner_id,
        harness_id="codex",
        ported_from={
            "stable_id": source_id,
            "version": "1.0",
            "passport_digest": source_digest,
        },
        related_setup_ids=[source_id],
    )

    async with sessionmaker() as db:
        target = (
            await db.execute(
                select(CatalogMetadata).where(
                    CatalogMetadata.stable_id == target_id, CatalogMetadata.version == "1.0"
                )
            )
        ).scalar_one()
        first = await apply_recast_family_effect(db, target)
        second = await apply_recast_family_effect(db, target)
        await db.commit()
        assert first is not None
        assert second is not None
        assert first.family_id == second.family_id
        assert first.created_from == "recast"
        assert first.baseline_stable_id == source_id
        revisions = list(
            (
                await db.execute(
                    select(SetupFamilyRevision).where(
                        SetupFamilyRevision.family_id == first.family_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(revisions) == 1
        source_family = await family_for_setup(db, source_id)
        target_family = await family_for_setup(db, target_id)
        assert source_family is not None and target_family is not None
        assert source_family.family_id == target_family.family_id

    detail = await client.get(
        f"/v1/owner/objects/setup/{target_id}/versions/1.0", headers=_auth(token)
    )
    assert detail.status_code == 200
    assert detail.json()["ported_from"]["stable_id"] == source_id
    assert detail.json()["family"]["family_id"] == first.family_id


@pytest.mark.asyncio
async def test_recast_does_not_join_a_cross_owner_source(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    _client, sessionmaker, _settings = db_api_client
    owner_id, _token = await _account_with_session(sessionmaker)
    other_id, _other_token = await _account_with_session(sessionmaker)
    source_id, source_digest = await _own_setup(
        sessionmaker, owner_id=other_id, harness_id="claude-code"
    )
    target_id, _target_digest = await _own_setup(
        sessionmaker,
        owner_id=owner_id,
        harness_id="codex",
        ported_from={
            "stable_id": source_id,
            "version": "1.0",
            "passport_digest": source_digest,
        },
    )

    async with sessionmaker() as db:
        target = (
            await db.execute(
                select(CatalogMetadata).where(
                    CatalogMetadata.stable_id == target_id, CatalogMetadata.version == "1.0"
                )
            )
        ).scalar_one()
        family = await apply_recast_family_effect(db, target)
        await db.commit()
        assert family is None
        assert await family_for_setup(db, target_id) is None
        stored = (
            await db.execute(select(CatalogMetadata).where(CatalogMetadata.stable_id == target_id))
        ).scalar_one()
        assert stored.passport_document is not None
        ported = stored.passport_document.get("ported_from")
        assert isinstance(ported, dict)
        assert ported["stable_id"] == source_id


@pytest.mark.asyncio
async def test_recast_joins_the_source_family_when_it_already_exists(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    owner_id, token = await _account_with_session(sessionmaker)
    source_id, source_digest = await _own_setup(
        sessionmaker, owner_id=owner_id, harness_id="claude-code"
    )
    pi_id, _pi_digest = await _own_setup(sessionmaker, owner_id=owner_id, harness_id="pi")
    created = await client.post(
        "/v1/owner/setup-families",
        headers=_auth(token),
        json={
            "schema_version": 1,
            "name": "existing",
            "baseline": {
                "stable_id": source_id,
                "version": "1.0",
                "passport_digest": source_digest,
            },
            "members": [source_id, pi_id],
            "expected_revision": 0,
            "idempotency_key": "owner-create-family-02",
            "reason": "owner_create",
        },
    )
    assert created.status_code == 201, created.text
    family_id = created.json()["family_id"]
    target_id, _target_digest = await _own_setup(
        sessionmaker,
        owner_id=owner_id,
        harness_id="codex",
        ported_from={
            "stable_id": source_id,
            "version": "1.0",
            "passport_digest": source_digest,
        },
    )
    async with sessionmaker() as db:
        target = (
            await db.execute(
                select(CatalogMetadata).where(
                    CatalogMetadata.stable_id == target_id, CatalogMetadata.version == "1.0"
                )
            )
        ).scalar_one()
        family = await apply_recast_family_effect(db, target)
        await db.commit()
        assert family is not None
        assert family.family_id == family_id
        assert await family_for_setup(db, target_id) is not None


@pytest.mark.asyncio
async def test_member_harness_filter_matches_family_siblings(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings],
) -> None:
    client, sessionmaker, _settings = db_api_client
    owner_id, token = await _account_with_session(sessionmaker)
    claude_id, claude_digest = await _own_setup(
        sessionmaker, owner_id=owner_id, harness_id="claude-code"
    )
    codex_id, _codex_digest = await _own_setup(sessionmaker, owner_id=owner_id, harness_id="codex")
    created = await client.post(
        "/v1/owner/setup-families",
        headers=_auth(token),
        json={
            "schema_version": 1,
            "name": "search-pair",
            "baseline": {
                "stable_id": claude_id,
                "version": "1.0",
                "passport_digest": claude_digest,
            },
            "members": [claude_id, codex_id],
            "expected_revision": 0,
            "idempotency_key": "owner-create-family-03",
            "reason": "owner_create",
        },
    )
    assert created.status_code == 201, created.text
    family_id = created.json()["family_id"]
    matched = await client.get(
        "/v1/catalog/setups",
        params={
            "include_experimental": "true",
            "family_id": family_id,
            "member_harness_id": "codex",
            "page_size": "20",
        },
    )
    assert matched.status_code == 200, matched.text
    ids = {item["stable_id"] for item in matched.json()["experimental"]}
    ids.update(item["stable_id"] for item in matched.json()["items"])
    assert claude_id in ids
    assert codex_id in ids
    harness_only = await client.get(
        "/v1/catalog/setups",
        params={
            "include_experimental": "true",
            "harness_id": "codex",
            "family_id": family_id,
            "page_size": "20",
        },
    )
    harness_ids = {item["stable_id"] for item in harness_only.json()["experimental"]}
    harness_ids.update(item["stable_id"] for item in harness_only.json()["items"])
    assert harness_ids == {codex_id}
