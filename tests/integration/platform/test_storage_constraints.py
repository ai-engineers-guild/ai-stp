"""PostgreSQL constraint checks for Sprint-1 storage models."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.models import Account, AuditEvent, CatalogMetadata, Device, ObjectLocation

pytestmark = pytest.mark.platform


async def _seed_account(session: AsyncSession, account_id: str = "account_constraints") -> None:
    session.add(Account(id=account_id))
    await session.flush()


async def _seed_catalog(session: AsyncSession, account_id: str = "account_constraints") -> int:
    metadata = CatalogMetadata(
        owner_account_id=account_id,
        object_kind="component",
        stable_id="component_constraints",
        version="1.0",
        current_revision_id="revision_" + "a" * 64,
        visibility="private",
        lifecycle_state="draft",
    )
    session.add(metadata)
    await session.flush()
    return metadata.id


@pytest.mark.asyncio
async def test_device_unique_key_and_foreign_key_constraints_reject_invalid_rows(
    db_session: AsyncSession,
) -> None:
    """Dropping FK or unique constraints would allow duplicate or orphan devices."""
    await _seed_account(db_session)
    db_session.add(Device(id="device_1", account_id="account_constraints", public_key="public-key"))
    await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                Device(id="device_2", account_id="account_constraints", public_key="public-key")
            )
            await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(Device(id="device_3", account_id="missing_account", public_key="other"))
            await db_session.flush()


@pytest.mark.asyncio
async def test_required_columns_and_object_location_constraints_reject_invalid_rows(
    db_session: AsyncSession,
) -> None:
    """Dropping NOT NULL, CHECK, FK or unique constraints would admit corrupt object rows."""
    await _seed_account(db_session)
    catalog_id = await _seed_catalog(db_session)
    db_session.add(
        ObjectLocation(
            catalog_metadata_id=catalog_id,
            purpose="artifact",
            object_key="objects/sha256/a",
            digest="sha256:" + "a" * 64,
            content_id="sha256:" + "a" * 64,
            size_bytes=1,
        )
    )
    await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    """
                    INSERT INTO catalog_metadata (
                        owner_account_id,
                        object_kind,
                        stable_id,
                        version,
                        current_revision_id,
                        visibility,
                        lifecycle_state
                    ) VALUES (
                        :owner_account_id,
                        :object_kind,
                        :stable_id,
                        :version,
                        NULL,
                        :visibility,
                        :lifecycle_state
                    )
                    """
                ),
                {
                    "owner_account_id": "account_constraints",
                    "object_kind": "component",
                    "stable_id": "component_missing_revision",
                    "version": "1.1",
                    "visibility": "private",
                    "lifecycle_state": "draft",
                },
            )

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                ObjectLocation(
                    catalog_metadata_id=catalog_id,
                    purpose="artifact",
                    object_key="objects/sha256/b",
                    digest="sha256:" + "b" * 64,
                    content_id="sha256:" + "b" * 64,
                    size_bytes=2,
                )
            )
            await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                ObjectLocation(
                    catalog_metadata_id=999_999,
                    purpose="artifact",
                    object_key="objects/sha256/c",
                    digest="sha256:" + "c" * 64,
                    content_id="sha256:" + "c" * 64,
                    size_bytes=3,
                )
            )
            await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                ObjectLocation(
                    catalog_metadata_id=catalog_id,
                    purpose="manifest",
                    object_key="objects/sha256/d",
                    digest="sha256:" + "d" * 64,
                    content_id="sha256:" + "d" * 64,
                    size_bytes=-1,
                )
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_two_catalog_versions_may_share_one_content_addressed_object_key(
    db_session: AsyncSession,
) -> None:
    """A unique object_key would refuse a new X.Y that keeps the same artifact bytes."""
    await _seed_account(db_session)
    first_id = await _seed_catalog(db_session)
    second = CatalogMetadata(
        owner_account_id="account_constraints",
        object_kind="component",
        stable_id="component_constraints",
        version="1.1",
        current_revision_id="revision_" + "b" * 64,
        visibility="private",
        lifecycle_state="draft",
    )
    db_session.add(second)
    await db_session.flush()
    key = "objects/sha256/" + "a" * 64
    digest = "sha256:" + "a" * 64
    db_session.add(
        ObjectLocation(
            catalog_metadata_id=first_id,
            purpose="artifact",
            object_key=key,
            digest=digest,
            content_id=digest,
            size_bytes=1,
        )
    )
    db_session.add(
        ObjectLocation(
            catalog_metadata_id=second.id,
            purpose="artifact",
            object_key=key,
            digest=digest,
            content_id=digest,
            size_bytes=1,
        )
    )
    await db_session.flush()


@pytest.mark.asyncio
async def test_audit_event_trigger_rejects_update_and_delete(db_session: AsyncSession) -> None:
    """Removing the append-only trigger would let audit rows be changed or deleted."""
    await _seed_account(db_session)
    event = AuditEvent(
        actor_account_id="account_constraints",
        action="catalog.create",
        target_table="catalog_metadata",
        target_id="catalog_1",
        reason="integration test",
        payload={"trace": "audit-append-only"},
    )
    db_session.add(event)
    await db_session.flush()

    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE audit_event SET reason = :reason WHERE id = :event_id"),
                {"reason": "mutated", "event_id": event.id},
            )

    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await db_session.execute(
                text("DELETE FROM audit_event WHERE id = :event_id"),
                {"event_id": event.id},
            )


@pytest.mark.asyncio
async def test_account_session_foreign_key_requires_account(db_session: AsyncSession) -> None:
    """Dropping the account session FK would create server sessions for no account."""
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    """
                    INSERT INTO account_session (id, account_id, expires_at)
                    VALUES (:id, :account_id, :expires_at)
                    """
                ),
                {
                    "id": "session_missing_account",
                    "account_id": "missing_account",
                    "expires_at": datetime.now(UTC) + timedelta(hours=1),
                },
            )
